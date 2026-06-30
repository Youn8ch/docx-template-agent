"""Build safe operation plans from style issues."""

from __future__ import annotations

from collections import OrderedDict

from src.engine.model.operation_model import FormatOperation, StyleIssue, is_safe_operation


ACTION_BY_TARGET_TYPE = {
    "paragraph": "apply_paragraph_style",
    "table": "apply_table_style",
    "table_header": "apply_table_header_style",
}


def build_operations(issues: list[StyleIssue]) -> list[FormatOperation]:
    grouped: OrderedDict[tuple[str, int, str | None], dict[str, object]] = OrderedDict()

    for issue in issues:
        key = (issue.target_type, issue.target_index, issue.role)
        if key not in grouped:
            grouped[key] = {
                "target_type": issue.target_type,
                "target_index": issue.target_index,
                "role": issue.role,
                "properties": {},
            }
        properties = grouped[key]["properties"]
        assert isinstance(properties, dict)
        properties[issue.issue_type] = issue.expected

    operations: list[FormatOperation] = []
    for index, item in enumerate(grouped.values(), start=1):
        action = ACTION_BY_TARGET_TYPE[str(item["target_type"])]
        operation = FormatOperation(
            operation_id=f"op-{index:04d}",
            action=action,
            target_type=item["target_type"],  # type: ignore[arg-type]
            target_indices=[int(item["target_index"])],
            role=item["role"] if item["role"] is None else str(item["role"]),
            properties=item["properties"],  # type: ignore[arg-type]
        )
        if is_safe_operation(operation):
            operations.append(operation)

    return operations
