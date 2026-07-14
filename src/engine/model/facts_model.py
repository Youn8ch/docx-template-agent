"""Read-only internal document fact models for stage 2 analysis.

These models describe extracted facts and candidates only. They must not be
used as executable mutations and they do not change the default role pipeline.
DocumentFacts is an internal analysis model and must not be sent directly as an
LLM payload. Stage 3 should build an explicit redacted snapshot from it.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ContainerType = Literal["body", "table_cell"]
ValueSource = Literal[
    "run_direct",
    "character_style",
    "paragraph_direct",
    "paragraph_style",
    "base_style",
    "document_defaults",
    "missing",
    "unreadable",
]
INTERNAL_FACTS_ONLY = True
PREVIEW_CHARS = 120
JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class InheritanceStep(BaseModel):
    style_id: str | None = None
    style_name: str | None = None
    style_type: str | None = None


class FormatValue(BaseModel):
    raw_value: Any = None
    resolved_value: Any = None
    source: ValueSource = "missing"
    explicit: bool = False
    readable: bool = True
    error: str | None = None
    source_style_id: str | None = None
    source_style_name: str | None = None
    inheritance_path: list[InheritanceStep] = Field(default_factory=list)
    inherited_path_warnings: list[str] = Field(default_factory=list)

    @field_validator("raw_value", "resolved_value")
    @classmethod
    def _json_stable_value(cls, value: Any) -> Any:
        _ensure_json_stable(value)
        return value


class RunFormatFacts(BaseModel):
    run_index: int
    text_length: int = 0
    non_empty: bool = False
    style_id: str | None = None
    style_name: str | None = None
    font_name: FormatValue = Field(default_factory=FormatValue)
    font_size: FormatValue = Field(default_factory=FormatValue)
    bold: FormatValue = Field(default_factory=FormatValue)
    italic: FormatValue = Field(default_factory=FormatValue)


class RunFormatSummary(BaseModel):
    font_names: list[Any] = Field(default_factory=list)
    dominant_font_name: Any = None
    mixed_font: bool = False
    font_sizes: list[Any] = Field(default_factory=list)
    dominant_font_size: Any = None
    mixed_font_size: bool = False
    east_asia_font_names: list[str] = Field(default_factory=list)
    ascii_font_names: list[str] = Field(default_factory=list)
    hansi_font_names: list[str] = Field(default_factory=list)
    cs_font_names: list[str] = Field(default_factory=list)
    dominant_east_asia_font: str | None = None
    dominant_ascii_font: str | None = None
    dominant_tie_break: Literal["first_seen"] = "first_seen"
    any_bold: bool = False
    all_bold: bool = False
    any_italic: bool = False
    all_italic: bool = False
    run_count: int = 0
    non_empty_run_count: int = 0
    whitespace_run_count: int = 0


class ParagraphFormatFacts(BaseModel):
    font_name: FormatValue = Field(default_factory=FormatValue)
    font_size: FormatValue = Field(default_factory=FormatValue)
    bold: FormatValue = Field(default_factory=FormatValue)
    italic: FormatValue = Field(default_factory=FormatValue)
    alignment: FormatValue = Field(default_factory=FormatValue)
    line_spacing: FormatValue = Field(default_factory=FormatValue)
    space_before: FormatValue = Field(default_factory=FormatValue)
    space_after: FormatValue = Field(default_factory=FormatValue)
    first_line_indent: FormatValue = Field(default_factory=FormatValue)
    first_line_indent_chars: FormatValue = Field(default_factory=FormatValue)
    hanging: FormatValue = Field(default_factory=FormatValue)
    hanging_chars: FormatValue = Field(default_factory=FormatValue)
    outline_level: FormatValue = Field(default_factory=FormatValue)


class TextFeatures(BaseModel):
    raw_text_length: int = 0
    normalized_text_length: int = 0
    is_empty: bool = False
    starts_with_numbering_pattern: bool = False
    short_text: bool = False


class NumberingFacts(BaseModel):
    direct_numbering_present: bool = False
    style_numbering_supported: bool = False
    numbering_resolution_scope: Literal["paragraph_direct_only"] = "paragraph_direct_only"
    unsupported_reason: str | None = None
    num_id: str | None = None
    ilvl: int | None = None
    abstract_num_id: str | None = None
    level_start: str | None = None
    num_format: str | None = None
    level_text: str | None = None
    p_style: str | None = None
    suffix: str | None = None
    level_justification: str | None = None
    readable: bool = True
    error: str | None = None


class WordFeatures(BaseModel):
    style_name: str | None = None
    style_id: str | None = None
    outline_level_raw: Any = None
    heading_level: int | None = None
    numbering: NumberingFacts = Field(default_factory=NumberingFacts)
    trusted_heading_style: bool = False
    trusted_builtin_heading: bool = False
    inherited_trusted_heading_style: bool = False
    inherited_heading_evidence: bool = False
    explicit_outline_level: bool = False
    style_own_outline_level: bool = False
    inherited_outline_level: bool = False
    outline_conflict: bool = False
    outline_conflict_reason: str | None = None


class PositionFeatures(BaseModel):
    container_type: ContainerType
    paragraph_index: int | None = None
    table_index: int | None = None
    row_index: int | None = None
    cell_index: int | None = None
    cell_paragraph_index: int | None = None
    section_index: int | None = None
    is_first_non_empty: bool = False
    previous_paragraph_index: int | None = None
    next_paragraph_index: int | None = None
    top_level_document_flow: bool = False


class RegionFlags(BaseModel):
    empty: bool = False
    top_level_document_flow: bool = False
    table_region: bool = False
    table_header_candidate: bool = False
    toc_region: bool = False
    toc_region_candidate: bool = False
    confirmed_toc_region: bool = False
    toc_heading_candidate: bool = False
    toc_entry_candidate: bool = False


class RuleHint(BaseModel):
    hint_type: str
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class HardRoleResult(BaseModel):
    role_type: str
    confidence: float = 1.0
    evidence: list[str] = Field(default_factory=list)


class FallbackCandidate(BaseModel):
    candidate_type: str
    score: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class ParagraphFacts(BaseModel):
    container_type: ContainerType
    paragraph_index: int | None = None
    table_index: int | None = None
    row_index: int | None = None
    cell_index: int | None = None
    cell_paragraph_index: int | None = None
    text_preview: str = ""
    raw_text_length: int = 0
    normalized_text_length: int = 0
    text_features: TextFeatures = Field(default_factory=TextFeatures)
    word_features: WordFeatures = Field(default_factory=WordFeatures)
    format_features: ParagraphFormatFacts = Field(default_factory=ParagraphFormatFacts)
    run_format_summary: RunFormatSummary = Field(default_factory=RunFormatSummary)
    run_facts: list[RunFormatFacts] = Field(default_factory=list)
    position_features: PositionFeatures
    context: dict[str, Any] = Field(default_factory=dict)
    region_flags: RegionFlags = Field(default_factory=RegionFlags)
    rule_hints: list[RuleHint] = Field(default_factory=list)
    hard_role_result: HardRoleResult | None = None
    fallback_candidate: FallbackCandidate | None = None


class TableHeaderCandidate(BaseModel):
    is_candidate: bool = False
    score: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class TableCellParagraphFacts(ParagraphFacts):
    container_type: Literal["table_cell"] = "table_cell"
    paragraph_index: None = None


class CellFacts(BaseModel):
    table_index: int
    row_index: int
    cell_index: int
    physical_cell_index: int
    logical_grid_start: int
    grid_span: int = 1
    v_merge: str | None = None
    is_merged: bool = False
    merged_anchor: str | None = None
    anchor_resolved: bool = True
    merge_kind: Literal["none", "grid_span", "v_merge_restart", "v_merge_continue", "mixed"] = "none"
    repeated_mapping: str | None = None
    contains_nested_table: bool = False
    nested_table_count: int = 0
    nested_tables_extracted: bool = False
    unsupported_features: list[str] = Field(default_factory=list)
    text_preview: str = ""
    paragraphs: list[TableCellParagraphFacts] = Field(default_factory=list)


class TableFacts(BaseModel):
    table_index: int
    rows: int = 0
    cols: int = 0
    exposure_model: Literal["physical_w_tc"] = "physical_w_tc"
    legacy_cell_index_compatible: bool = False
    contains_merged_cells: bool = False
    contains_nested_tables: bool = False
    nested_tables_extracted: bool = False
    unsupported_features: list[str] = Field(default_factory=list)
    cells: list[CellFacts] = Field(default_factory=list)
    header_candidate: TableHeaderCandidate = Field(default_factory=TableHeaderCandidate)


class DocumentRegion(BaseModel):
    type: Literal["toc"]
    start_paragraph_index: int
    end_paragraph_index: int
    confidence: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class StyleRegistrySummary(BaseModel):
    style_count: int = 0
    paragraph_style_count: int = 0
    character_style_count: int = 0
    unresolved_based_on: list[str] = Field(default_factory=list)
    cyclic_based_on: list[str] = Field(default_factory=list)


class NumberingRegistrySummary(BaseModel):
    numbering_count: int = 0
    abstract_numbering_count: int = 0
    unresolved_num_ids: list[str] = Field(default_factory=list)


class DocumentFacts(BaseModel):
    body_paragraphs: list[ParagraphFacts] = Field(default_factory=list)
    tables: list[TableFacts] = Field(default_factory=list)
    regions: list[DocumentRegion] = Field(default_factory=list)
    style_registry_summary: StyleRegistrySummary = Field(default_factory=StyleRegistrySummary)
    numbering_registry_summary: NumberingRegistrySummary = Field(default_factory=NumberingRegistrySummary)
    internal_only: bool = INTERNAL_FACTS_ONLY
    preview_max_chars: int = PREVIEW_CHARS
    llm_payload_safe: bool = False
    snapshot_required: bool = True


def _ensure_json_stable(value: Any) -> None:
    if value is None or type(value) in {str, bool, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("FormatValue only accepts finite floats")
        return
    if isinstance(value, list):
        for item in value:
            _ensure_json_stable(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("FormatValue dict keys must be strings")
            _ensure_json_stable(item)
        return
    raise ValueError(f"FormatValue only accepts JSON-stable primitive values, got {type(value).__name__}")
