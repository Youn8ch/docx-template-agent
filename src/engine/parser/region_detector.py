"""Conservative fact-level region detection for document flow candidates."""

from __future__ import annotations

import re

from src.engine.model.facts_model import DocumentFacts, DocumentRegion, HardRoleResult, ParagraphFacts


TOC_HEADING_TEXTS = {"目录", "目 录", "table of contents"}
TOC_ENTRY_LEADER_RE = re.compile(r".+(?:\.{2,}|…+|\t).*\d+\s*$")
TOC_ENTRY_STATIC_RE = re.compile(
    r"^\s*(?:第.+[章节]|[一二三四五六七八九十]+[、.．]|[0-9]+(?:\.[0-9]+)*\s+).+\s+\d+\s*$"
)
MAX_TOC_EMPTY_GAP = 2


def is_toc_heading_candidate(facts: ParagraphFacts) -> tuple[bool, list[str]]:
    text = facts.text_preview.strip()
    evidence: list[str] = []
    if text.lower() in TOC_HEADING_TEXTS:
        evidence.append("toc_heading_text")
    style_id = (facts.word_features.style_id or "").lower().replace(" ", "")
    style_name = (facts.word_features.style_name or "").lower()
    if style_id == "tocheading" or style_name in {"toc heading", "目录标题"}:
        evidence.append("toc_heading_style")
    return bool(evidence), evidence


def is_toc_entry_candidate(facts: ParagraphFacts) -> tuple[bool, list[str]]:
    text = facts.text_preview
    evidence: list[str] = []
    style_id = (facts.word_features.style_id or "").lower().replace(" ", "")
    style_name = (facts.word_features.style_name or "").lower()
    if style_id.startswith("toc") and style_id != "tocheading":
        evidence.append("toc_entry_style")
    if style_name.startswith("toc "):
        evidence.append("toc_entry_style")
    if facts.context.get("has_toc_field"):
        evidence.append("toc_field")
    if "\n" in text:
        evidence.append("toc_multiline_candidate")
    if TOC_ENTRY_LEADER_RE.match(text):
        evidence.append("toc_entry_leader_or_tab")
    elif TOC_ENTRY_STATIC_RE.match(text):
        evidence.append("toc_entry_static_page_number")
    return bool(evidence), evidence


def _entry_evidence(facts: ParagraphFacts) -> list[str]:
    return list(facts.context.get("toc_entry_evidence", []))


def _is_high_confidence_entry(facts: ParagraphFacts) -> bool:
    evidence = set(_entry_evidence(facts))
    return bool(evidence & {"toc_entry_style", "toc_field", "toc_entry_leader_or_tab", "toc_entry_static_page_number"})


def _is_style_entry(facts: ParagraphFacts) -> bool:
    return "toc_entry_style" in set(_entry_evidence(facts))


def _is_leader_or_tab_entry(facts: ParagraphFacts) -> bool:
    return "toc_entry_leader_or_tab" in set(_entry_evidence(facts))


def _mark_candidate(items: list[ParagraphFacts]) -> None:
    for item in items:
        item.region_flags.toc_region_candidate = True


def _toc_hard_role(item: ParagraphFacts, evidence: list[str]) -> HardRoleResult:
    role_type = "toc_heading" if item.region_flags.toc_heading_candidate else "toc_entry"
    return HardRoleResult(
        role_type=role_type,
        confidence=1.0,
        evidence=sorted(set(["confirmed_toc_region", *evidence])),
    )


def _confirm_region(
    body: list[ParagraphFacts],
    regions: list[DocumentRegion],
    items: list[ParagraphFacts],
    confidence: float,
    evidence: list[str],
) -> None:
    indexed = [item for item in items if item.paragraph_index is not None]
    if not indexed:
        return
    start = indexed[0].paragraph_index
    end = indexed[-1].paragraph_index
    if start is None or end is None:
        return
    regions.append(
        DocumentRegion(
            type="toc",
            start_paragraph_index=start,
            end_paragraph_index=end,
            confidence=confidence,
            evidence=sorted(set(evidence)),
        )
    )
    for item in items:
        item.region_flags.toc_region = True
        item.region_flags.confirmed_toc_region = True
        if item.hard_role_result is None or item.hard_role_result.role_type == "empty":
            item.hard_role_result = _toc_hard_role(item, evidence)


def _collect_after_heading(body: list[ParagraphFacts], index: int) -> tuple[list[ParagraphFacts], list[str], int]:
    items = [body[index]]
    evidence = list(body[index].context.get("toc_heading_evidence", []))
    cursor = index + 1
    empty_gap = 0
    while cursor < len(body):
        current = body[cursor]
        if current.region_flags.toc_entry_candidate:
            empty_gap = 0
            items.append(current)
            evidence.extend(_entry_evidence(current))
            cursor += 1
            continue
        if current.region_flags.empty and empty_gap < MAX_TOC_EMPTY_GAP:
            empty_gap += 1
            cursor += 1
            continue
        break
    return items, evidence, cursor


def _collect_entry_run(body: list[ParagraphFacts], index: int) -> tuple[list[ParagraphFacts], list[str]]:
    items: list[ParagraphFacts] = []
    evidence: list[str] = []
    cursor = index
    while cursor < len(body) and body[cursor].region_flags.toc_entry_candidate:
        items.append(body[cursor])
        evidence.extend(_entry_evidence(body[cursor]))
        cursor += 1
    return items, evidence


def apply_region_detection(document_facts: DocumentFacts) -> DocumentFacts:
    body = [item.model_copy(deep=True) for item in document_facts.body_paragraphs]
    regions: list[DocumentRegion] = []

    for facts in body:
        is_heading, heading_evidence = is_toc_heading_candidate(facts)
        is_entry, entry_evidence = is_toc_entry_candidate(facts)
        facts.region_flags.toc_heading_candidate = is_heading
        facts.region_flags.toc_entry_candidate = is_entry
        if is_heading:
            facts.context["toc_heading_evidence"] = heading_evidence
        if is_entry:
            facts.context["toc_entry_evidence"] = entry_evidence

    index = 0
    while index < len(body):
        current = body[index]
        if current.region_flags.toc_heading_candidate:
            items, evidence, next_index = _collect_after_heading(body, index)
            entries = [item for item in items if item.region_flags.toc_entry_candidate]
            _mark_candidate(items)
            if len(entries) >= 2 and all(_is_high_confidence_entry(item) for item in entries):
                _confirm_region(body, regions, items, 0.9, evidence)
            index = max(next_index, index + 1)
            continue

        if current.region_flags.toc_entry_candidate:
            if "toc_field" in set(_entry_evidence(current)):
                _mark_candidate([current])
                _confirm_region(body, regions, [current], 0.95, _entry_evidence(current))
                index += 1
                continue

            items, evidence = _collect_entry_run(body, index)
            _mark_candidate(items)
            if len(items) >= 2 and all(_is_style_entry(item) for item in items):
                _confirm_region(body, regions, items, 0.9, evidence)
            elif len(items) >= 2 and all(_is_leader_or_tab_entry(item) for item in items):
                _confirm_region(body, regions, items, 0.8, evidence)
            index += max(len(items), 1)
            continue

        index += 1

    return document_facts.model_copy(update={"body_paragraphs": body, "regions": regions}, deep=True)
