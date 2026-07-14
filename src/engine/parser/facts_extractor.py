"""Extract stage 2 document facts without changing existing role decisions."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from lxml import etree

from src.engine.model.document_model import DocumentModel
from src.engine.model.facts_model import (
    CellFacts,
    DocumentFacts,
    FallbackCandidate,
    HardRoleResult,
    ParagraphFacts,
    ParagraphFormatFacts,
    PositionFeatures,
    PREVIEW_CHARS,
    RegionFlags,
    RuleHint,
    RunFormatFacts,
    RunFormatSummary,
    TableCellParagraphFacts,
    TableFacts,
    TableHeaderCandidate,
    TextFeatures,
    WordFeatures,
)
from src.engine.parser.docx_package_reader import NSMAP, read_docx_package, w_tag, w_val
from src.engine.parser.numbering_parser import paragraph_numbering, parse_numbering_registry
from src.engine.parser.region_detector import apply_region_detection
from src.engine.parser.style_resolver import (
    paragraph_style_id,
    parse_style_registry,
    resolve_paragraph_property,
    resolve_run_property,
    run_style_id,
    is_trusted_heading_style,
)


NUMBERING_HINT_RE = re.compile(r"^\s*(?:[一二三四五六七八九十]+、|（[一二三四五六七八九十]+）|\d+[.)、]|\d+(?:\.\d+)+)\s*\S+")
HEADING_LEVEL_RE = re.compile(r"^heading ?([1-9])$", re.IGNORECASE)
CN_HEADING_LEVEL_RE = re.compile(r"^标题 ?([1-9])$")


def _normalized_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _text(element: etree._Element) -> str:
    parts: list[str] = []
    for node in element.iter():
        local = etree.QName(node).localname
        if local == "t":
            parts.append(node.text or "")
        elif local == "tab":
            parts.append("\t")
        elif local == "br":
            parts.append("\n")
    return "".join(parts)


def _style_name(registry: Any, style_id: str | None) -> str | None:
    if not style_id:
        return None
    style = registry.styles.get(style_id)
    return style.style_name if style is not None else None


def _style_has_numbering(registry: Any, style_id: str | None) -> bool:
    seen: set[str] = set()
    current_id = style_id
    while current_id and current_id not in seen:
        seen.add(current_id)
        style = registry.styles.get(current_id)
        if style is None:
            return False
        if style.element is not None and style.element.find("w:pPr/w:numPr", namespaces=NSMAP) is not None:
            return True
        current_id = style.based_on
    return False


def _heading_level_from_outline(raw: Any) -> int | None:
    if isinstance(raw, int) and 0 <= raw <= 8:
        return raw + 1
    return None


def _heading_level_from_style(style_id: str | None, style_name: str | None) -> int | None:
    for value in (style_id, style_name):
        if not value:
            continue
        normalized = value.strip()
        if normalized.startswith("Heading") and normalized[7:].isdigit():
            level = int(normalized[7:])
            if 1 <= level <= 9:
                return level
        match = HEADING_LEVEL_RE.fullmatch(normalized)
        if match:
            return int(match.group(1))
        match = CN_HEADING_LEVEL_RE.fullmatch(normalized)
        if match:
            return int(match.group(1))
    return None


def _format_features(registry: Any, paragraph_element: etree._Element, style_id: str | None) -> ParagraphFormatFacts:
    return ParagraphFormatFacts(
        font_name=resolve_run_property(registry, None, style_id, "font_name"),
        font_size=resolve_run_property(registry, None, style_id, "font_size"),
        bold=resolve_run_property(registry, None, style_id, "bold"),
        italic=resolve_run_property(registry, None, style_id, "italic"),
        alignment=resolve_paragraph_property(registry, paragraph_element, style_id, "alignment"),
        line_spacing=resolve_paragraph_property(registry, paragraph_element, style_id, "line_spacing"),
        space_before=resolve_paragraph_property(registry, paragraph_element, style_id, "space_before"),
        space_after=resolve_paragraph_property(registry, paragraph_element, style_id, "space_after"),
        first_line_indent=resolve_paragraph_property(registry, paragraph_element, style_id, "first_line_indent"),
        first_line_indent_chars=resolve_paragraph_property(registry, paragraph_element, style_id, "first_line_indent_chars"),
        hanging=resolve_paragraph_property(registry, paragraph_element, style_id, "hanging"),
        hanging_chars=resolve_paragraph_property(registry, paragraph_element, style_id, "hanging_chars"),
        outline_level=resolve_paragraph_property(registry, paragraph_element, style_id, "outline_level"),
    )


def _run_facts(registry: Any, paragraph_element: etree._Element, style_id: str | None) -> list[RunFormatFacts]:
    facts: list[RunFormatFacts] = []
    for index, run in enumerate(paragraph_element.findall("w:r", namespaces=NSMAP), start=1):
        text = _text(run)
        r_style_id = run_style_id(run)
        facts.append(
            RunFormatFacts(
                run_index=index,
                text_length=len(text),
                non_empty=bool(text.strip()),
                style_id=r_style_id,
                style_name=_style_name(registry, r_style_id),
                font_name=resolve_run_property(registry, run, style_id, "font_name"),
                font_size=resolve_run_property(registry, run, style_id, "font_size"),
                bold=resolve_run_property(registry, run, style_id, "bold"),
                italic=resolve_run_property(registry, run, style_id, "italic"),
            )
        )
    return facts


def _unique(values: list[Any]) -> list[Any]:
    unique: list[Any] = []
    for value in values:
        if value is None or value in unique:
            continue
        unique.append(value)
    return unique


def _dominant_weighted(values: list[tuple[Any, int]]) -> Any:
    weights: dict[Any, int] = {}
    first_seen: list[Any] = []
    for value, weight in values:
        if value is None or weight <= 0:
            continue
        if value not in weights:
            first_seen.append(value)
            weights[value] = 0
        weights[value] += weight
    if not weights:
        return None
    max_weight = max(weights.values())
    for value in first_seen:
        if weights[value] == max_weight:
            return value
    return None


def _mixed(values: list[Any]) -> bool:
    present = [value for value in values if value is not None]
    return len(set(present)) > 1


def _run_summary(run_facts: list[RunFormatFacts]) -> RunFormatSummary:
    non_empty = [run for run in run_facts if run.non_empty]
    whitespace_run_count = sum(1 for run in run_facts if run.text_length > 0 and not run.non_empty)
    font_name_values = [run.font_name.resolved_value for run in non_empty]
    font_size_values = [run.font_size.resolved_value for run in non_empty]
    font_names = _unique(font_name_values)
    font_sizes = _unique(font_size_values)
    raw_font_values = [run.font_name.raw_value if isinstance(run.font_name.raw_value, dict) else {} for run in non_empty]
    east_asia_values = [value.get("eastAsia") for value in raw_font_values]
    ascii_values = [value.get("ascii") for value in raw_font_values]
    hansi_values = [value.get("hAnsi") for value in raw_font_values]
    cs_values = [value.get("cs") for value in raw_font_values]
    bolds = [bool(run.bold.resolved_value) for run in non_empty if run.bold.resolved_value is not None]
    italics = [bool(run.italic.resolved_value) for run in non_empty if run.italic.resolved_value is not None]
    return RunFormatSummary(
        font_names=font_names,
        dominant_font_name=_dominant_weighted([(run.font_name.resolved_value, run.text_length) for run in non_empty]),
        mixed_font=_mixed(font_name_values),
        font_sizes=font_sizes,
        dominant_font_size=_dominant_weighted([(run.font_size.resolved_value, run.text_length) for run in non_empty]),
        mixed_font_size=_mixed(font_size_values),
        east_asia_font_names=_unique(east_asia_values),
        ascii_font_names=_unique(ascii_values),
        hansi_font_names=_unique(hansi_values),
        cs_font_names=_unique(cs_values),
        dominant_east_asia_font=_dominant_weighted([(value.get("eastAsia"), run.text_length) for value, run in zip(raw_font_values, non_empty, strict=False)]),
        dominant_ascii_font=_dominant_weighted([(value.get("ascii"), run.text_length) for value, run in zip(raw_font_values, non_empty, strict=False)]),
        any_bold=any(bolds),
        all_bold=bool(non_empty) and len(bolds) == len(non_empty) and all(bolds),
        any_italic=any(italics),
        all_italic=bool(non_empty) and len(italics) == len(non_empty) and all(italics),
        run_count=len(run_facts),
        non_empty_run_count=len(non_empty),
        whitespace_run_count=whitespace_run_count,
    )


def _has_toc_field(paragraph_element: etree._Element) -> bool:
    text = " ".join(node.text or "" for node in paragraph_element.findall(".//w:instrText", namespaces=NSMAP))
    return "TOC" in text.upper()


def _rule_hints(text: str, format_features: ParagraphFormatFacts, summary: RunFormatSummary) -> list[RuleHint]:
    hints: list[RuleHint] = []
    if NUMBERING_HINT_RE.match(text):
        hints.append(RuleHint(hint_type="numbering_pattern", confidence=0.6, evidence=["text_prefix"]))
    if 0 < len(text.strip()) <= 30:
        hints.append(RuleHint(hint_type="short_text", confidence=0.35, evidence=["text_length"]))
    font_size = summary.dominant_font_size if summary.dominant_font_size is not None else format_features.font_size.resolved_value
    if isinstance(font_size, int | float) and font_size >= 15:
        hints.append(RuleHint(hint_type="large_font", confidence=0.45, evidence=[f"font_size={font_size}"]))
    if summary.any_bold or format_features.bold.resolved_value is True:
        hints.append(RuleHint(hint_type="bold", confidence=0.35, evidence=["run_or_paragraph_format"]))
    if format_features.alignment.resolved_value == "center":
        hints.append(RuleHint(hint_type="centered", confidence=0.3, evidence=["paragraph_alignment"]))
    return hints


def _outline_state(format_features: ParagraphFormatFacts) -> tuple[bool, bool, bool, bool, str | None]:
    value = format_features.outline_level.resolved_value
    source = format_features.outline_level.source
    explicit = source == "paragraph_direct"
    style_own = source == "paragraph_style"
    inherited = source == "base_style"
    valid = isinstance(value, int) and 0 <= value <= 8
    conflict_reason = None
    if explicit and not valid and value is not None:
        conflict_reason = f"explicit outline_level is not a heading level: {value}"
    return explicit and valid, style_own and valid, inherited and valid, explicit and not valid and value is not None, conflict_reason


def _hard_role(
    text: str,
    word_features: WordFeatures,
    region_flags: RegionFlags,
    format_features: ParagraphFormatFacts,
) -> HardRoleResult | None:
    if not text.strip():
        return HardRoleResult(role_type="empty", confidence=1.0, evidence=["empty_text"])
    if region_flags.toc_region and region_flags.toc_entry_candidate:
        return HardRoleResult(role_type="toc_entry", confidence=1.0, evidence=["toc_region"])
    if region_flags.toc_region and region_flags.toc_heading_candidate:
        return HardRoleResult(role_type="toc_heading", confidence=1.0, evidence=["toc_region"])
    if word_features.explicit_outline_level:
        return HardRoleResult(role_type="outline_heading", confidence=1.0, evidence=["explicit_outline_level"])
    if word_features.outline_conflict:
        return None
    if word_features.trusted_builtin_heading and word_features.style_own_outline_level:
        return HardRoleResult(role_type="outline_heading", confidence=1.0, evidence=["trusted_heading_style_own_outline_level"])
    if word_features.trusted_builtin_heading:
        return HardRoleResult(role_type="trusted_heading_style", confidence=1.0, evidence=["trusted_heading_style"])
    return None


def _fallback_candidate(hints: list[RuleHint]) -> FallbackCandidate | None:
    if not hints:
        return None
    score = min(sum(hint.confidence for hint in hints), 1.0)
    if score < 0.5:
        return None
    return FallbackCandidate(
        candidate_type="heading_like",
        score=score,
        evidence=[evidence for hint in hints for evidence in hint.evidence],
    )


def _paragraph_facts(
    registry: Any,
    numbering_registry: Any,
    paragraph_element: etree._Element,
    position: PositionFeatures,
) -> ParagraphFacts:
    raw_text = _text(paragraph_element)
    normalized = _normalized_text(raw_text)
    style_id = paragraph_style_id(paragraph_element)
    style_name = _style_name(registry, style_id)
    format_features = _format_features(registry, paragraph_element, style_id)
    runs = _run_facts(registry, paragraph_element, style_id)
    summary = _run_summary(runs)
    trusted, inherited = is_trusted_heading_style(registry, style_id)
    explicit_outline, style_own_outline, inherited_outline, outline_conflict, outline_conflict_reason = _outline_state(format_features)
    numbering = paragraph_numbering(paragraph_element, numbering_registry, style_has_numbering=_style_has_numbering(registry, style_id))
    outline_heading_level = _heading_level_from_outline(format_features.outline_level.resolved_value)
    style_heading_level = _heading_level_from_style(style_id, style_name) if trusted else None
    heading_conflicts: list[dict[str, int | str]] = []
    if explicit_outline and trusted and style_heading_level is not None and outline_heading_level != style_heading_level:
        heading_conflicts.append(
            {
                "type": "heading_style_outline_conflict",
                "style_heading_level": style_heading_level,
                "explicit_outline_level": outline_heading_level or -1,
            }
        )
    word_features = WordFeatures(
        style_name=style_name,
        style_id=style_id,
        outline_level_raw=format_features.outline_level.raw_value,
        heading_level=outline_heading_level,
        numbering=numbering,
        trusted_heading_style=trusted,
        trusted_builtin_heading=trusted,
        inherited_trusted_heading_style=inherited,
        inherited_heading_evidence=inherited,
        explicit_outline_level=explicit_outline,
        style_own_outline_level=style_own_outline,
        inherited_outline_level=inherited_outline,
        outline_conflict=outline_conflict and (trusted or inherited),
        outline_conflict_reason=outline_conflict_reason if outline_conflict and (trusted or inherited) else None,
    )
    region_flags = RegionFlags(
        empty=not normalized.strip(),
        top_level_document_flow=position.top_level_document_flow,
        table_region=position.container_type == "table_cell",
    )
    text_features = TextFeatures(
        raw_text_length=len(raw_text),
        normalized_text_length=len(normalized),
        is_empty=not normalized.strip(),
        starts_with_numbering_pattern=bool(NUMBERING_HINT_RE.match(normalized)),
        short_text=0 < len(normalized.strip()) <= 30,
    )
    hints = _rule_hints(normalized, format_features, summary)
    if inherited:
        evidence = ["inherits_trusted_heading_style"]
        if word_features.outline_conflict_reason:
            evidence.append(word_features.outline_conflict_reason)
        hints.append(
            RuleHint(
                hint_type="inherited_heading_evidence",
                confidence=0.75 if inherited_outline else 0.55,
                evidence=evidence,
            )
        )
    if word_features.outline_conflict_reason:
        hints.append(
            RuleHint(
                hint_type="outline_conflict",
                confidence=0.0,
                evidence=[word_features.outline_conflict_reason],
            )
        )
    for conflict in heading_conflicts:
        hints.append(
            RuleHint(
                hint_type="heading_style_outline_conflict",
                confidence=0.0,
                evidence=[
                    f"style_heading_level={conflict['style_heading_level']}",
                    f"explicit_outline_level={conflict['explicit_outline_level']}",
                ],
            )
        )
    facts_class = TableCellParagraphFacts if position.container_type == "table_cell" else ParagraphFacts
    facts = facts_class(
        container_type=position.container_type,
        paragraph_index=position.paragraph_index,
        table_index=position.table_index,
        row_index=position.row_index,
        cell_index=position.cell_index,
        cell_paragraph_index=position.cell_paragraph_index,
        text_preview=normalized[:PREVIEW_CHARS],
        raw_text_length=len(raw_text),
        normalized_text_length=len(normalized),
        text_features=text_features,
        word_features=word_features,
        format_features=format_features,
        run_format_summary=summary,
        run_facts=runs,
        position_features=position,
        context={"has_toc_field": _has_toc_field(paragraph_element), "heading_conflicts": heading_conflicts},
        region_flags=region_flags,
        rule_hints=hints,
        fallback_candidate=_fallback_candidate(hints),
    )
    facts.hard_role_result = _hard_role(normalized, word_features, region_flags, format_features)
    return facts


def _body_paragraph_elements(document_xml: etree._Element) -> list[etree._Element]:
    body = document_xml.find("w:body", namespaces=NSMAP)
    if body is None:
        return []
    return list(body.findall("w:p", namespaces=NSMAP))


def _table_elements(document_xml: etree._Element) -> list[etree._Element]:
    body = document_xml.find("w:body", namespaces=NSMAP)
    if body is None:
        return []
    return list(body.findall("w:tbl", namespaces=NSMAP))


def _body_positions(paragraphs: list[etree._Element]) -> list[PositionFeatures]:
    non_empty_indices = [index for index, paragraph in enumerate(paragraphs, start=1) if _normalized_text(_text(paragraph)).strip()]
    first_non_empty = non_empty_indices[0] if non_empty_indices else None
    positions: list[PositionFeatures] = []
    section_index = 1
    for index, paragraph in enumerate(paragraphs, start=1):
        positions.append(
            PositionFeatures(
                container_type="body",
                paragraph_index=index,
                section_index=section_index,
                is_first_non_empty=index == first_non_empty,
                previous_paragraph_index=index - 1 if index > 1 else None,
                next_paragraph_index=index + 1 if index < len(paragraphs) else None,
                top_level_document_flow=True,
            )
        )
        if paragraph.find("w:pPr/w:sectPr", namespaces=NSMAP) is not None:
            section_index += 1
    return positions


def _cell_text(cell: etree._Element) -> str:
    return "\n".join(_text(paragraph) for paragraph in cell.findall("w:p", namespaces=NSMAP))


def _grid_span(cell: etree._Element) -> int:
    value = w_val(cell.find("w:tcPr/w:gridSpan", namespaces=NSMAP))
    if value is None:
        return 1
    try:
        return max(int(value), 1)
    except ValueError:
        return 1


def _v_merge(cell: etree._Element) -> str | None:
    element = cell.find("w:tcPr/w:vMerge", namespaces=NSMAP)
    if element is None:
        return None
    return w_val(element) or "continue"


def _merge_kind(grid_span: int, v_merge: str | None) -> str:
    if grid_span > 1 and v_merge is not None:
        return "mixed"
    if grid_span > 1:
        return "grid_span"
    if v_merge == "restart":
        return "v_merge_restart"
    if v_merge == "continue":
        return "v_merge_continue"
    return "none"


def _merge_anchor(
    row_index: int,
    logical_grid: int,
    grid_span: int,
    v_merge: str | None,
    active_vmerge_anchors: dict[int, str],
    unsupported_features: list[str],
) -> tuple[str | None, bool]:
    is_merged = grid_span > 1 or v_merge is not None
    own_anchor = f"r{row_index}c{logical_grid}"
    if v_merge == "restart":
        for logical_column in range(logical_grid, logical_grid + grid_span):
            active_vmerge_anchors[logical_column] = own_anchor
        return own_anchor, True
    if v_merge == "continue":
        anchors = {
            active_vmerge_anchors.get(logical_column)
            for logical_column in range(logical_grid, logical_grid + grid_span)
        }
        anchors.discard(None)
        if len(anchors) == 1:
            anchor = next(iter(anchors))
            return (None, False) if anchor == own_anchor else (anchor, True)
        unsupported_features.append("vmerge_anchor_unresolved")
        return None, False
    return own_anchor if is_merged else None, True


def _row_has_tbl_header(row: etree._Element) -> bool:
    return row.find("w:trPr/w:tblHeader", namespaces=NSMAP) is not None


def _cell_shading(cell: etree._Element) -> str | None:
    shd = cell.find("w:tcPr/w:shd", namespaces=NSMAP)
    return None if shd is None else shd.get(w_tag("fill"))


def _header_candidate(table: TableFacts, rows: list[etree._Element]) -> TableHeaderCandidate:
    if not rows:
        return TableHeaderCandidate()
    evidence = ["first_row"]
    score = 0.25
    if _row_has_tbl_header(rows[0]):
        evidence.append("tblHeader")
        score += 0.35
    first_row_cells = [cell for cell in table.cells if cell.row_index == 1]
    first_row_paragraphs = [paragraph for cell in first_row_cells for paragraph in cell.paragraphs]
    non_empty_first_row_paragraphs = [paragraph for paragraph in first_row_paragraphs if not paragraph.region_flags.empty]
    if non_empty_first_row_paragraphs and all(paragraph.run_format_summary.all_bold for paragraph in non_empty_first_row_paragraphs):
        evidence.append("all_cells_bold")
        score += 0.2
    first_shading = [_cell_shading(cell) for cell in rows[0].findall("w:tc", namespaces=NSMAP)]
    body_shading = [
        _cell_shading(cell)
        for row in rows[1:]
        for cell in row.findall("w:tc", namespaces=NSMAP)
    ]
    if any(first_shading) and set(first_shading) != set(body_shading):
        evidence.append("distinct_shading")
        score += 0.15
    first_lengths = [len(cell.text_preview) for cell in first_row_cells]
    body_lengths = [len(cell.text_preview) for cell in table.cells if cell.row_index != 1]
    if first_lengths and body_lengths and (sum(first_lengths) / len(first_lengths)) < (sum(body_lengths) / len(body_lengths)):
        evidence.append("shorter_text_than_body_rows")
        score += 0.05
    return TableHeaderCandidate(is_candidate=score > 0.25, score=min(score, 1.0), evidence=evidence)


def extract_document_facts(path: str | Path, document_model: DocumentModel | None = None) -> DocumentFacts:
    parts = read_docx_package(path)
    style_registry = parse_style_registry(parts.styles_xml)
    numbering_registry = parse_numbering_registry(parts.numbering_xml)

    body_elements = _body_paragraph_elements(parts.document_xml)
    body_positions = _body_positions(body_elements)
    body_facts = [
        _paragraph_facts(style_registry, numbering_registry, paragraph, position)
        for paragraph, position in zip(body_elements, body_positions, strict=False)
    ]

    tables: list[TableFacts] = []
    for table_index, table_element in enumerate(_table_elements(parts.document_xml), start=1):
        rows = table_element.findall("w:tr", namespaces=NSMAP)
        table_facts = TableFacts(
            table_index=table_index,
            rows=len(rows),
            cols=max((len(row.findall("w:tc", namespaces=NSMAP)) for row in rows), default=0),
        )
        active_vmerge_anchors: dict[int, str] = {}
        for row_index, row in enumerate(rows, start=1):
            logical_grid = 1
            for cell_index, cell in enumerate(row.findall("w:tc", namespaces=NSMAP), start=1):
                grid_span = _grid_span(cell)
                v_merge = _v_merge(cell)
                nested_table_count = len(cell.findall("w:tbl", namespaces=NSMAP))
                unsupported_features: list[str] = []
                if nested_table_count:
                    unsupported_features.append("nested_table")
                if grid_span > 1:
                    unsupported_features.append("grid_span")
                if v_merge is not None:
                    unsupported_features.append("v_merge")
                merged_anchor, anchor_resolved = _merge_anchor(
                    row_index,
                    logical_grid,
                    grid_span,
                    v_merge,
                    active_vmerge_anchors,
                    unsupported_features,
                )
                cell_facts = CellFacts(
                    table_index=table_index,
                    row_index=row_index,
                    cell_index=cell_index,
                    physical_cell_index=cell_index,
                    logical_grid_start=logical_grid,
                    grid_span=grid_span,
                    v_merge=v_merge,
                    is_merged=grid_span > 1 or v_merge is not None,
                    merged_anchor=merged_anchor,
                    anchor_resolved=anchor_resolved,
                    merge_kind=_merge_kind(grid_span, v_merge),
                    repeated_mapping="physical_w_tc_only; not expanded to python-docx row.cells logical repeats",
                    contains_nested_table=nested_table_count > 0,
                    nested_table_count=nested_table_count,
                    nested_tables_extracted=False,
                    unsupported_features=unsupported_features,
                    text_preview=_normalized_text(_cell_text(cell))[:PREVIEW_CHARS],
                )
                paragraphs = cell.findall("w:p", namespaces=NSMAP)
                for cell_paragraph_index, paragraph in enumerate(paragraphs, start=1):
                    position = PositionFeatures(
                        container_type="table_cell",
                        paragraph_index=None,
                        table_index=table_index,
                        row_index=row_index,
                        cell_index=cell_index,
                        cell_paragraph_index=cell_paragraph_index,
                        top_level_document_flow=False,
                    )
                    fact = _paragraph_facts(style_registry, numbering_registry, paragraph, position)
                    fact.region_flags.table_header_candidate = row_index == 1
                    if row_index == 1:
                        fact.hard_role_result = HardRoleResult(role_type="table", confidence=1.0, evidence=["table_cell_container"])
                    cell_facts.paragraphs.append(fact)
                table_facts.cells.append(cell_facts)
                logical_grid += grid_span
        table_facts.contains_merged_cells = any(cell.is_merged for cell in table_facts.cells)
        table_facts.contains_nested_tables = any(cell.contains_nested_table for cell in table_facts.cells)
        if table_facts.contains_merged_cells:
            table_facts.unsupported_features.append("merged_cell_logical_expansion")
        if table_facts.contains_nested_tables:
            table_facts.unsupported_features.append("nested_table_extraction")
        table_facts.header_candidate = _header_candidate(table_facts, rows)
        for cell in table_facts.cells:
            if cell.row_index == 1 and table_facts.header_candidate.is_candidate:
                for paragraph in cell.paragraphs:
                    paragraph.region_flags.table_header_candidate = True
                    paragraph.context["table_header_candidate"] = table_facts.header_candidate.model_dump()
        tables.append(table_facts)

    facts = DocumentFacts(
        body_paragraphs=body_facts,
        tables=tables,
        style_registry_summary=style_registry.summary,
        numbering_registry_summary=numbering_registry.summary,
    )
    facts = apply_region_detection(facts)
    return facts
