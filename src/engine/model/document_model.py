"""Read-only document analysis models.

These models describe observed docx structure and formatting. They must not
represent requested mutations; executable changes belong in operation models.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


ParagraphRole = Literal["empty", "title", "heading_1", "heading_2", "heading_3", "body", "unknown"]


class RunInfo(BaseModel):
    index: int = 0
    text: str = ""
    font_name: str | None = None
    font_size: float | None = None
    bold: bool | None = None


class ParagraphInfo(BaseModel):
    index: int
    text: str = ""
    role: ParagraphRole = "unknown"
    style_name: str | None = None
    alignment: str | None = None
    font_names: list[str | None] = Field(default_factory=list)
    font_sizes: list[float | None] = Field(default_factory=list)
    bold_values: list[bool | None] = Field(default_factory=list)
    line_spacing: float | None = None
    space_before: float | None = None
    space_after: float | None = None
    first_line_indent: float | None = None
    first_line_indent_chars: float | None = None
    runs: list[RunInfo] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_preview(cls, data: Any) -> Any:
        if isinstance(data, dict) and "text" not in data and "text_preview" in data:
            data = {**data, "text": data["text_preview"]}
        return data

    @property
    def id(self) -> str:
        return f"p-{self.index:04d}"

    @property
    def text_preview(self) -> str:
        return self.text


class TableCellInfo(BaseModel):
    row_index: int
    col_index: int
    text: str = ""
    style_name: str | None = None
    alignment: str | None = None
    font_names: list[str | None] = Field(default_factory=list)
    font_sizes: list[float | None] = Field(default_factory=list)
    bold_values: list[bool | None] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_preview(cls, data: Any) -> Any:
        if isinstance(data, dict) and "text" not in data and "text_preview" in data:
            data = {**data, "text": data["text_preview"]}
        return data

    @property
    def id(self) -> str:
        return f"r-{self.row_index:04d}-c-{self.col_index:04d}"

    @property
    def text_preview(self) -> str:
        return self.text


class TableInfo(BaseModel):
    index: int
    rows: int = 0
    cols: int = 0
    cells: list[TableCellInfo] = Field(default_factory=list)

    @model_validator(mode="after")
    def _infer_dimensions(self) -> "TableInfo":
        if not self.cells:
            return self

        inferred_rows = max(cell.row_index for cell in self.cells) + 1
        inferred_cols = max(cell.col_index for cell in self.cells) + 1
        if self.rows == 0:
            self.rows = inferred_rows
        if self.cols == 0:
            self.cols = inferred_cols
        return self

    @property
    def id(self) -> str:
        return f"t-{self.index:04d}"


class DocumentModel(BaseModel):
    filepath: Path
    paragraph_count: int = 0
    table_count: int = 0
    paragraphs: list[ParagraphInfo] = Field(default_factory=list)
    tables: list[TableInfo] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_path(cls, data: Any) -> Any:
        if isinstance(data, dict) and "filepath" not in data and "path" in data:
            data = {**data, "filepath": data["path"]}
        return data

    @model_validator(mode="after")
    def _infer_counts(self) -> "DocumentModel":
        if self.paragraph_count == 0:
            self.paragraph_count = len(self.paragraphs)
        if self.table_count == 0:
            self.table_count = len(self.tables)
        return self

    @property
    def path(self) -> Path:
        return self.filepath


# Compatibility names for the current engine skeleton. New code should import
# the *Info models above.
ParagraphModel = ParagraphInfo
TableCellModel = TableCellInfo
TableModel = TableInfo
