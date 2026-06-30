"""Apply whitelisted formatting operations to a new docx file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from src.engine.formatter.font_utils import first_line_indent_chars_value, set_run_font
from src.engine.model.operation_model import Operation, OperationResult, is_safe_operation


ALIGNMENT_MAP = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
    "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
}

HEADING_ROLES = {"title", "heading_1", "heading_2", "heading_3"}
FIRST_LINE_INDENT_ATTRS = ("w:firstLineChars", "w:firstLine", "w:hanging")


def _resolve_output_path(input_path: Path, output_path: str | Path) -> Path:
    target = Path(output_path)
    if target.suffix.lower() == ".docx":
        resolved = target.resolve()
    else:
        resolved = (target / f"{input_path.stem}_formatted.docx").resolve()

    if resolved == input_path.resolve():
        raise ValueError("output path cannot overwrite the source docx")
    return resolved


def _paragraph_by_index(document: Any, index: int) -> Any:
    if index < 1 or index > len(document.paragraphs):
        raise IndexError(f"paragraph index out of range: {index}")
    return document.paragraphs[index - 1]


def _table_by_index(document: Any, index: int) -> Any:
    if index < 1 or index > len(document.tables):
        raise IndexError(f"table index out of range: {index}")
    return document.tables[index - 1]


def _set_alignment(paragraph: Any, alignment: str | None) -> None:
    if alignment is None:
        return
    key = str(alignment).strip().lower()
    if key not in ALIGNMENT_MAP:
        raise ValueError(f"unsupported paragraph alignment: {alignment}")
    paragraph.alignment = ALIGNMENT_MAP[key]


def _get_or_add_indent(paragraph: Any) -> Any:
    p_pr = paragraph._p.get_or_add_pPr()
    ind = p_pr.ind
    if ind is None:
        ind = OxmlElement("w:ind")
        p_pr.append(ind)
    return ind


def _clear_indent_attrs(paragraph: Any, attrs: tuple[str, ...] = FIRST_LINE_INDENT_ATTRS) -> None:
    p_pr = paragraph._p.pPr
    if p_pr is None or p_pr.ind is None:
        return
    ind = p_pr.ind
    for attr in attrs:
        ind.attrib.pop(qn(attr), None)


def _set_left_indent_zero(paragraph: Any) -> None:
    ind = _get_or_add_indent(paragraph)
    ind.set(qn("w:left"), "0")


def _set_first_line_indent_chars(paragraph: Any, properties: dict[str, Any]) -> None:
    value = first_line_indent_chars_value(properties)
    if value is None:
        return

    ind = _get_or_add_indent(paragraph)
    for attr in ("w:firstLine", "w:hanging"):
        ind.attrib.pop(qn(attr), None)
    ind.set(qn("w:firstLineChars"), str(value))
    ind.set(qn("w:left"), "0")


def _set_paragraph_format(paragraph: Any, properties: dict[str, Any], role: str | None) -> None:
    paragraph_format = paragraph.paragraph_format
    _set_alignment(paragraph, properties.get("alignment"))

    if "line_spacing" in properties and properties["line_spacing"] is not None:
        paragraph_format.line_spacing = float(properties["line_spacing"])
    if "space_before" in properties and properties["space_before"] is not None:
        paragraph_format.space_before = Pt(float(properties["space_before"]))
    if "space_after" in properties and properties["space_after"] is not None:
        paragraph_format.space_after = Pt(float(properties["space_after"]))

    if role == "body":
        _set_first_line_indent_chars(paragraph, properties)
    elif role in HEADING_ROLES:
        _clear_indent_attrs(paragraph)
        _set_left_indent_zero(paragraph)


def _format_runs(paragraphs: list[Any], properties: dict[str, Any]) -> None:
    for paragraph in paragraphs:
        for run in paragraph.runs:
            set_run_font(run, properties)


def _apply_paragraph_style(document: Any, operation: Operation) -> None:
    for index in operation.target_indices:
        paragraph = _paragraph_by_index(document, index)
        _format_runs([paragraph], operation.properties)
        _set_paragraph_format(paragraph, operation.properties, operation.role)


def _apply_table_style(document: Any, operation: Operation) -> None:
    for index in operation.target_indices:
        table = _table_by_index(document, index)
        for row in table.rows:
            for cell in row.cells:
                _format_runs(list(cell.paragraphs), operation.properties)
                for paragraph in cell.paragraphs:
                    _set_alignment(paragraph, operation.properties.get("alignment"))
                    _clear_indent_attrs(paragraph)


def _apply_table_header_style(document: Any, operation: Operation) -> None:
    for index in operation.target_indices:
        table = _table_by_index(document, index)
        if not table.rows:
            continue
        for cell in table.rows[0].cells:
            _format_runs(list(cell.paragraphs), operation.properties)
            for paragraph in cell.paragraphs:
                _set_alignment(paragraph, operation.properties.get("alignment"))
                _clear_indent_attrs(paragraph)


def _apply_operation(document: Any, operation: Operation) -> None:
    if operation.action == "apply_paragraph_style":
        _apply_paragraph_style(document, operation)
    elif operation.action == "apply_table_style":
        _apply_table_style(document, operation)
    elif operation.action == "apply_table_header_style":
        _apply_table_header_style(document, operation)
    else:
        raise ValueError(f"unsupported operation action: {operation.action}")


def apply_operations(
    input_path: str | Path,
    output_path: str | Path,
    operations: list[Operation],
) -> list[dict[str, str]]:
    source = Path(input_path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"input docx not found: {source}")
    if source.suffix.lower() != ".docx":
        raise ValueError(f"input must be a .docx file: {source}")

    target = _resolve_output_path(source, output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    document = Document(str(source))
    results: list[OperationResult] = []

    for operation in operations:
        if not is_safe_operation(operation):
            results.append(
                OperationResult(
                    operation_id=operation.operation_id,
                    status="failed",
                    message=f"operation rejected by whitelist: {operation.action}",
                )
            )
            continue

        try:
            _apply_operation(document, operation)
        except Exception as exc:
            results.append(
                OperationResult(
                    operation_id=operation.operation_id,
                    status="failed",
                    message=f"operation failed: {exc}",
                )
            )
            continue

        results.append(
            OperationResult(
                operation_id=operation.operation_id,
                status="success",
                message=f"operation applied: {operation.action}",
            )
        )

    try:
        document.save(str(target))
    except Exception as exc:
        raise RuntimeError(f"failed to save formatted docx: {target}") from exc

    return [result.model_dump() for result in results]
