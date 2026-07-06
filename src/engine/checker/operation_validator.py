"""Central validation for executable formatting operations."""

from __future__ import annotations

import math
from typing import Any

from src.engine.model.document_model import DocumentModel
from src.engine.model.operation_model import FormatOperation, is_safe_operation


PARAGRAPH_PROPERTIES = {
    "font_name",
    "font_size",
    "bold",
    "alignment",
    "line_spacing",
    "space_before",
    "space_after",
    "first_line_indent_chars",
}
TABLE_PROPERTIES = {"font_name", "font_size", "bold", "alignment"}
TEXT_MUTATION_FIELDS = {
    "text",
    "content",
    "replacement",
    "replace",
    "delete",
    "insert",
    "append",
    "prepend",
    "path",
    "command",
    "macro",
    "script",
}
ACTION_TARGET_TYPE = {
    "apply_paragraph_style": "paragraph",
    "apply_table_style": "table",
    "apply_table_header_style": "table_header",
}
ALIGNMENTS = {"left", "center", "right", "justify"}
MIN_FONT_SIZE = 1
MAX_FONT_SIZE = 200
MIN_LINE_SPACING = 0.5
MAX_LINE_SPACING = 5
MIN_SPACE_PT = 0
MAX_SPACE_PT = 200
MIN_FIRST_LINE_CHARS = 0
MAX_FIRST_LINE_CHARS = 10


def _template_roles(template: dict[str, Any]) -> set[str]:
    rules = template.get("rules", {})
    if not isinstance(rules, dict):
        return set()
    return {str(role) for role, rule in rules.items() if isinstance(rule, dict)}


def _allowed_properties(operation: FormatOperation) -> set[str]:
    if operation.target_type == "paragraph":
        return PARAGRAPH_PROPERTIES
    return TABLE_PROPERTIES


def _check_number(
    errors: list[str],
    operation: FormatOperation,
    key: str,
    value: Any,
    minimum: float,
    maximum: float,
) -> None:
    if isinstance(value, bool):
        errors.append(f"{operation.operation_id}: property {key} rejected: boolean is not numeric")
        return
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors.append(f"{operation.operation_id}: property {key} rejected: value is not numeric")
        return
    if not math.isfinite(number):
        errors.append(f"{operation.operation_id}: property {key} rejected: value must be finite")
        return
    if number < minimum or number > maximum:
        errors.append(
            f"{operation.operation_id}: property {key} out of range "
            f"({minimum}..{maximum}): {value!r}"
        )


def _validate_properties(operation: FormatOperation) -> list[str]:
    errors: list[str] = []
    allowed = _allowed_properties(operation)
    for key, value in operation.properties.items():
        if key in TEXT_MUTATION_FIELDS:
            errors.append(f"{operation.operation_id}: forbidden mutation field: {key}")
            continue
        if key not in allowed:
            errors.append(f"{operation.operation_id}: unsupported property: {key}")
            continue
        if key == "font_name":
            if value is not None and (not isinstance(value, str) or not value.strip()):
                errors.append(f"{operation.operation_id}: font_name must be non-empty text")
        elif key == "font_size":
            _check_number(errors, operation, key, value, MIN_FONT_SIZE, MAX_FONT_SIZE)
        elif key == "bold":
            if value is not None and not isinstance(value, bool):
                errors.append(f"{operation.operation_id}: bold must be boolean")
        elif key == "alignment":
            if value is not None and str(value).strip().lower() not in ALIGNMENTS:
                errors.append(f"{operation.operation_id}: unsupported alignment: {value!r}")
        elif key == "line_spacing":
            _check_number(errors, operation, key, value, MIN_LINE_SPACING, MAX_LINE_SPACING)
        elif key in {"space_before", "space_after"}:
            _check_number(errors, operation, key, value, MIN_SPACE_PT, MAX_SPACE_PT)
        elif key == "first_line_indent_chars":
            _check_number(
                errors,
                operation,
                key,
                value,
                MIN_FIRST_LINE_CHARS,
                MAX_FIRST_LINE_CHARS,
            )
    return errors


def validate_operations(
    operations: list[FormatOperation],
    document: DocumentModel,
    template: dict[str, Any],
) -> list[str]:
    """Return validation errors for operations that must not execute."""

    errors: list[str] = []
    roles = _template_roles(template)
    paragraph_count = document.paragraph_count
    table_count = document.table_count

    for operation in operations:
        if not is_safe_operation(operation):
            errors.append(f"{operation.operation_id}: action rejected by whitelist: {operation.action}")
        expected_target = ACTION_TARGET_TYPE.get(operation.action)
        if expected_target != operation.target_type:
            errors.append(
                f"{operation.operation_id}: action {operation.action} does not match "
                f"target_type {operation.target_type}"
            )
        if not operation.target_indices:
            errors.append(f"{operation.operation_id}: target_indices must not be empty")
        for index in operation.target_indices:
            if operation.target_type == "paragraph":
                if index < 1 or index > paragraph_count:
                    errors.append(f"{operation.operation_id}: paragraph target out of range: {index}")
            else:
                if index < 1 or index > table_count:
                    errors.append(f"{operation.operation_id}: table target out of range: {index}")
        if operation.role is not None and operation.role not in roles:
            errors.append(f"{operation.operation_id}: role not defined by template: {operation.role}")
        errors.extend(_validate_properties(operation))

    return errors
