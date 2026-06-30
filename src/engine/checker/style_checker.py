"""Check analyzed document styles against a safe formatting template."""

from __future__ import annotations

from math import isclose
from typing import Any

from src.engine.checker.operation_builder import build_operations
from src.engine.model.document_model import DocumentModel, ParagraphInfo, TableInfo
from src.engine.model.operation_model import StyleCheckReport, StyleIssue


FORMAT_FIELDS = (
    "font_name",
    "font_size",
    "bold",
    "alignment",
    "line_spacing",
    "space_before",
    "space_after",
    "first_line_indent_chars",
)
TABLE_FIELDS = ("font_name", "font_size", "bold", "alignment")


def _present_values(values: list[Any]) -> list[Any]:
    return [value for value in values if value is not None]


def _display_value(values: list[Any]) -> Any:
    present = _present_values(values)
    if not present:
        return None
    unique: list[Any] = []
    for value in present:
        if value not in unique:
            unique.append(value)
    return unique[0] if len(unique) == 1 else unique


def _numbers_match(current: Any, expected: Any, tolerance: float = 0.25) -> bool:
    if current is None or expected is None:
        return current == expected
    try:
        return isclose(float(current), float(expected), abs_tol=tolerance)
    except (TypeError, ValueError):
        return False


def _scalar_matches(current: Any, expected: Any) -> bool:
    if isinstance(expected, float | int):
        return _numbers_match(current, expected)
    if isinstance(expected, str):
        return str(current or "").strip().lower() == expected.strip().lower()
    return current == expected


def _list_matches(values: list[Any], expected: Any) -> bool:
    present = _present_values(values)
    if not present:
        return expected is None
    return all(_scalar_matches(value, expected) for value in present)


def _current_paragraph_value(paragraph: ParagraphInfo, field: str) -> Any:
    if field == "font_name":
        return _display_value(paragraph.font_names)
    if field == "font_size":
        return _display_value(paragraph.font_sizes)
    if field == "bold":
        return _display_value(paragraph.bold_values)
    if field == "first_line_indent_chars":
        return paragraph.first_line_indent_chars
    return getattr(paragraph, field)


def _paragraph_matches(paragraph: ParagraphInfo, field: str, expected: Any) -> bool:
    if field == "font_name":
        return _list_matches(paragraph.font_names, expected)
    if field == "font_size":
        return _list_matches(paragraph.font_sizes, expected)
    if field == "bold":
        return _list_matches(paragraph.bold_values, expected)
    return _scalar_matches(_current_paragraph_value(paragraph, field), expected)


def _issue(
    issue_id: str,
    issue_type: str,
    target_type: str,
    target_index: int,
    role: str | None,
    current: Any,
    expected: Any,
) -> StyleIssue:
    return StyleIssue(
        issue_id=issue_id,
        issue_type=issue_type,
        target_type=target_type,  # type: ignore[arg-type]
        target_index=target_index,
        role=role,
        current=current,
        expected=expected,
        message=f"{target_type} {target_index} {issue_type} mismatch: current={current!r}, expected={expected!r}",
    )


def _check_paragraph(
    paragraph: ParagraphInfo,
    rule: dict[str, Any],
    next_issue_id: int,
) -> tuple[list[StyleIssue], int]:
    issues: list[StyleIssue] = []
    for field in FORMAT_FIELDS:
        if field not in rule:
            continue
        expected = rule[field]
        if _paragraph_matches(paragraph, field, expected):
            continue
        issues.append(
            _issue(
                f"issue-{next_issue_id:04d}",
                field,
                "paragraph",
                paragraph.index,
                paragraph.role,
                _current_paragraph_value(paragraph, field),
                expected,
            )
        )
        next_issue_id += 1
    return issues, next_issue_id


def _table_cells(table: TableInfo, header_only: bool = False) -> list[Any]:
    if header_only:
        return [cell for cell in table.cells if cell.row_index == 1]
    return table.cells


def _current_table_value(table: TableInfo, field: str, header_only: bool = False) -> Any:
    values: list[Any] = []
    for cell in _table_cells(table, header_only=header_only):
        if field == "font_name":
            values.extend(cell.font_names)
        elif field == "font_size":
            values.extend(cell.font_sizes)
        elif field == "bold":
            values.extend(cell.bold_values)
        elif field == "alignment":
            values.append(cell.alignment)
    return _display_value(values)


def _table_matches(table: TableInfo, field: str, expected: Any, header_only: bool = False) -> bool:
    values: list[Any] = []
    for cell in _table_cells(table, header_only=header_only):
        if field == "font_name":
            values.extend(cell.font_names)
        elif field == "font_size":
            values.extend(cell.font_sizes)
        elif field == "bold":
            values.extend(cell.bold_values)
        elif field == "alignment":
            values.append(cell.alignment)
    return _list_matches(values, expected)


def _check_table(
    table: TableInfo,
    rule: dict[str, Any],
    role: str,
    target_type: str,
    next_issue_id: int,
    header_only: bool = False,
) -> tuple[list[StyleIssue], int]:
    issues: list[StyleIssue] = []
    for field in TABLE_FIELDS:
        if field not in rule:
            continue
        expected = rule[field]
        if _table_matches(table, field, expected, header_only=header_only):
            continue
        issues.append(
            _issue(
                f"issue-{next_issue_id:04d}",
                field,
                target_type,
                table.index,
                role,
                _current_table_value(table, field, header_only=header_only),
                expected,
            )
        )
        next_issue_id += 1
    return issues, next_issue_id


def check_styles(document: DocumentModel, template: dict[str, Any]) -> StyleCheckReport:
    rules = template.get("rules", {})
    if not isinstance(rules, dict):
        raise ValueError("template rules must be a mapping")

    issues: list[StyleIssue] = []
    next_issue_id = 1

    for paragraph in document.paragraphs:
        if paragraph.role == "empty":
            continue
        rule = rules.get(paragraph.role)
        if not isinstance(rule, dict):
            continue
        paragraph_issues, next_issue_id = _check_paragraph(paragraph, rule, next_issue_id)
        issues.extend(paragraph_issues)

    table_rule = rules.get("table")
    table_header_rule = rules.get("table_header")
    for table in document.tables:
        if isinstance(table_rule, dict):
            table_issues, next_issue_id = _check_table(
                table,
                table_rule,
                "table",
                "table",
                next_issue_id,
            )
            issues.extend(table_issues)
        if isinstance(table_header_rule, dict):
            header_issues, next_issue_id = _check_table(
                table,
                table_header_rule,
                "table_header",
                "table_header",
                next_issue_id,
                header_only=True,
            )
            issues.extend(header_issues)

    operations = build_operations(issues)
    return StyleCheckReport(
        template_id=str(template.get("template_id", "")),
        issues=issues,
        operations=operations,
    )
