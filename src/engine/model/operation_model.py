"""Operation models and whitelist validation primitives."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


TargetType = Literal["paragraph", "table", "table_header"]
OperationAction = Literal[
    "apply_paragraph_style",
    "apply_table_style",
    "apply_table_header_style",
]

SAFE_OPERATION_ACTIONS: set[str] = {
    "apply_paragraph_style",
    "apply_table_style",
    "apply_table_header_style",
}

DANGEROUS_OPERATION_ACTIONS: set[str] = {
    "replace_text",
    "delete_paragraph",
    "delete_table",
    "delete_table_row",
    "delete_table_column",
    "set_table_cell_text",
    "merge_paragraph",
    "split_paragraph",
    "run_macro",
    "execute_com",
    "open_wps_client",
}


class StyleIssue(BaseModel):
    issue_id: str
    issue_type: str
    target_type: TargetType
    target_index: int
    role: str | None = None
    current: Any = None
    expected: Any = None
    message: str

    model_config = {"extra": "forbid"}


class FormatOperation(BaseModel):
    operation_id: str
    action: OperationAction
    target_type: TargetType
    target_indices: list[int] = Field(default_factory=list)
    role: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_operation_shape(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        converted = dict(data)
        if "operation_id" not in converted and "id" in converted:
            converted["operation_id"] = converted["id"]
            converted.pop("id", None)
        if "action" not in converted and "type" in converted:
            converted["action"] = converted["type"]
            converted.pop("type", None)
        if "properties" not in converted and "params" in converted:
            converted["properties"] = converted["params"]
            converted.pop("params", None)
        return converted

    @property
    def id(self) -> str:
        return self.operation_id

    @property
    def type(self) -> str:
        return self.action

    model_config = {"extra": "forbid"}


class StyleCheckReport(BaseModel):
    template_id: str
    issue_count: int = 0
    operation_count: int = 0
    issues: list[StyleIssue] = Field(default_factory=list)
    operations: list[FormatOperation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _infer_counts(self) -> "StyleCheckReport":
        self.issue_count = len(self.issues)
        self.operation_count = len(self.operations)
        return self

    model_config = {"extra": "forbid"}


class OperationResult(BaseModel):
    operation_id: str
    status: Literal["success", "skipped", "failed"]
    message: str

    model_config = {"extra": "forbid"}


ExecutionStatus = Literal[
    "success",
    "partial_success",
    "validation_failed",
    "execution_failed",
    "content_integrity_failed",
    "fatal",
]


class ExecutionReport(BaseModel):
    status: ExecutionStatus
    output_path: str | None = None
    expected_output_path: str | None = None
    temp_output_path: str | None = None
    temp_file_retained: bool = False
    output_existed_before: bool = False
    output_overwritten: bool = False
    issues_before: int = 0
    issues_after: int | None = None
    operations_before: int = 0
    operations_after: int | None = None
    validation_errors: list[str] = Field(default_factory=list)
    execution_results: list[dict[str, Any]] = Field(default_factory=list)
    integrity_before: dict[str, Any] = Field(default_factory=dict)
    integrity_after: dict[str, Any] = Field(default_factory=dict)
    integrity_errors: list[str] = Field(default_factory=list)
    recheck_errors: list[str] = Field(default_factory=list)

    model_config = {"extra": "forbid"}


def is_safe_operation(operation: FormatOperation) -> bool:
    action = operation.action
    return action in SAFE_OPERATION_ACTIONS and action not in DANGEROUS_OPERATION_ACTIONS


# Compatibility aliases for the current engine skeleton. New code should use
# FormatOperation directly and must still pass the action whitelist above.
Operation = FormatOperation
