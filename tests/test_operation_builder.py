from pathlib import Path

from src.engine.checker.operation_builder import build_operations
from src.engine.checker.style_checker import check_styles
from src.engine.model.document_model import DocumentModel, ParagraphInfo, TableCellInfo, TableInfo
from src.engine.model.operation_model import (
    SAFE_OPERATION_ACTIONS,
    StyleCheckReport,
    StyleIssue,
    is_safe_operation,
)


FORBIDDEN_ACTIONS = {"delete_paragraph", "replace_text", "modify_table_cell_text"}


def test_build_operations_uses_only_whitelisted_actions():
    issues = [
        StyleIssue(
            issue_id="issue-0001",
            issue_type="font_name",
            target_type="paragraph",
            target_index=1,
            role="body",
            current="Arial",
            expected="SimSun",
            message="paragraph font mismatch",
        ),
        StyleIssue(
            issue_id="issue-0002",
            issue_type="alignment",
            target_type="table",
            target_index=1,
            role="table",
            current="left",
            expected="center",
            message="table alignment mismatch",
        ),
        StyleIssue(
            issue_id="issue-0003",
            issue_type="bold",
            target_type="table_header",
            target_index=1,
            role="table_header",
            current=False,
            expected=True,
            message="table header bold mismatch",
        ),
    ]

    operations = build_operations(issues)

    assert operations
    assert {operation.action for operation in operations} <= SAFE_OPERATION_ACTIONS
    assert not ({operation.action for operation in operations} & FORBIDDEN_ACTIONS)
    assert all(is_safe_operation(operation) for operation in operations)


def test_build_operations_preserves_first_line_indent_chars():
    issues = [
        StyleIssue(
            issue_id="issue-0001",
            issue_type="first_line_indent_chars",
            target_type="paragraph",
            target_index=1,
            role="body",
            current=0,
            expected=2,
            message="body first-line indent mismatch",
        ),
    ]

    operations = build_operations(issues)

    assert len(operations) == 1
    assert operations[0].role == "body"
    assert operations[0].properties["first_line_indent_chars"] == 2


def test_check_styles_generates_style_check_report_and_safe_operations():
    template = {
        "template_id": "test",
        "rules": {
            "body": {
                "font_name": "SimSun",
                "font_size": 12,
                "bold": False,
                "alignment": "justify",
                "line_spacing": 1.5,
                "space_before": 0,
                "space_after": 0,
                "first_line_indent_chars": 2,
            },
            "table": {
                "font_name": "SimSun",
                "font_size": 10.5,
                "bold": False,
                "alignment": "center",
            },
        },
        "safety": {},
    }
    document = DocumentModel(
        filepath=Path("sample.docx"),
        paragraphs=[
            ParagraphInfo(
                index=1,
                text="body",
                role="body",
                alignment="left",
                font_names=["Arial"],
                font_sizes=[10],
                bold_values=[True],
                line_spacing=1.0,
                space_before=6,
                space_after=6,
                first_line_indent=0,
            )
        ],
        tables=[
            TableInfo(
                index=1,
                rows=1,
                cols=1,
                cells=[
                    TableCellInfo(
                        row_index=1,
                        col_index=1,
                        text="cell text must stay unchanged",
                        alignment="left",
                        font_names=["Arial"],
                        font_sizes=[9],
                        bold_values=[True],
                    )
                ],
            )
        ],
    )

    report = check_styles(document, template)

    assert isinstance(report, StyleCheckReport)
    assert report.issue_count > 0
    assert report.operation_count > 0
    assert {operation.action for operation in report.operations} <= SAFE_OPERATION_ACTIONS
    assert not ({operation.action for operation in report.operations} & FORBIDDEN_ACTIONS)
    assert all(is_safe_operation(operation) for operation in report.operations)


def test_check_styles_rejects_pt_indent_as_character_indent():
    template = {
        "template_id": "test",
        "rules": {
            "body": {
                "font_size": 10.5,
                "first_line_indent_chars": 2,
            },
        },
        "safety": {},
    }
    document = DocumentModel(
        filepath=Path("sample.docx"),
        paragraphs=[
            ParagraphInfo(
                index=1,
                text="body",
                role="body",
                font_sizes=[10.5],
                first_line_indent=21,
                first_line_indent_chars=None,
            )
        ],
    )

    report = check_styles(document, template)

    assert any(issue.issue_type == "first_line_indent_chars" for issue in report.issues)
    assert any(
        operation.properties.get("first_line_indent_chars") == 2
        for operation in report.operations
    )
