"""Markdown report writer for style check results."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from src.engine.model.operation_model import StyleCheckReport


def report_path_for_output_docx(output_docx_path: str | Path) -> Path:
    output_path = Path(output_docx_path)
    return output_path.with_name(f"{output_path.stem}_check_report.md")


def _format_value(value: object) -> str:
    if value is None:
        return "-"
    return str(value)


def _issue_stats(report: StyleCheckReport) -> list[str]:
    counter = Counter(issue.issue_type for issue in report.issues)
    if not counter:
        return ["- 未发现格式问题。"]
    return [f"- `{issue_type}`: {count}" for issue_type, count in sorted(counter.items())]


def _issue_details(report: StyleCheckReport) -> list[str]:
    if not report.issues:
        return ["未发现需要处理的格式问题。"]

    lines = [
        "| ID | 类型 | 目标 | 角色 | 当前值 | 期望值 | 说明 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for issue in report.issues:
        target = f"{issue.target_type}#{issue.target_index}"
        lines.append(
            "| "
            f"{issue.issue_id} | "
            f"{issue.issue_type} | "
            f"{target} | "
            f"{_format_value(issue.role)} | "
            f"{_format_value(issue.current)} | "
            f"{_format_value(issue.expected)} | "
            f"{issue.message} |"
        )
    return lines


def _review_suggestions(report: StyleCheckReport) -> list[str]:
    suggestions = [
        "- 请重点复核自动生成的 operations 是否只涉及格式属性，不涉及正文文本修改。",
        "- 请抽查标题、正文、表格和表头的实际显示效果，特别是中文字体是否符合内网模板要求。",
    ]
    if report.issue_count == 0:
        suggestions.append("- 当前未发现格式差异，可按需进行人工抽样确认。")
    else:
        suggestions.append("- 对问题较多的段落或表格，建议先人工确认模板规则是否适用于该文档。")
    return suggestions


def _compact_json_value(value: Any) -> str:
    if isinstance(value, dict):
        result = value.get("result")
        if result is not None:
            return _compact_json_value(result)
        simple_items = []
        for key, item in value.items():
            if isinstance(item, (str, int, float, bool)) or item is None:
                simple_items.append(f"{key}: {item}")
        return "; ".join(simple_items) if simple_items else str(value)
    if isinstance(value, list):
        return f"{len(value)} item(s)"
    if value is None:
        return "-"
    return str(value)


def _llm_assistance_lines(llm_assistance: dict[str, Any] | None) -> list[str]:
    if llm_assistance is None:
        return []

    mode = llm_assistance.get("mode", "rule_only_fallback")
    status = llm_assistance.get("status")
    if status is None:
        status = "ok" if llm_assistance.get("available") is True else "fallback"

    lines = [
        "## LLM 辅助分析",
        "",
        "- LLM 分析仅供参考，不参与格式化操作生成。",
        "- 推荐模板仅供参考，不会覆盖本次实际使用模板。",
        f"- mode: `{mode}`",
        f"- status: `{status}`",
        f"- operations_source: `{llm_assistance.get('operations_source', 'rule_engine_only')}`",
        f"- operations_generated: `{llm_assistance.get('operations_generated', False)}`",
    ]

    reason = llm_assistance.get("reason") or llm_assistance.get("error")
    if reason:
        lines.append(f"- fallback_reason: `{reason}`")

    for label, key in (
        ("document_type", "document_type"),
        ("heading_levels", "heading_levels"),
        ("summary", "summary"),
        ("report_summary", "report_summary"),
        ("template_recommendation", "template_recommendation"),
        ("recommended_template", "recommended_template"),
    ):
        if key in llm_assistance:
            lines.append(f"- {label}: {_compact_json_value(llm_assistance[key])}")

    lines.append("")
    return lines


def write_markdown_report(
    report: StyleCheckReport,
    output_docx_path: str | Path,
    original_file: str | Path,
    template_id: str,
    paragraph_count: int,
    table_count: int,
    checked_at: datetime | None = None,
    llm_assistance: dict[str, Any] | None = None,
) -> Path:
    report_path = report_path_for_output_docx(output_docx_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    checked_time = (checked_at or datetime.now()).isoformat(timespec="seconds")

    lines = [
        "# DOCX 格式检查报告",
        "",
        "## 基本信息",
        "",
        f"- 原始文件: `{original_file}`",
        f"- 使用模板: `{template_id}`",
        f"- 检查时间: `{checked_time}`",
        f"- 段落数: `{paragraph_count}`",
        f"- 表格数: `{table_count}`",
        f"- 问题总数: `{report.issue_count}`",
        f"- 操作总数: `{report.operation_count}`",
        "",
        "## 问题分类统计",
        "",
        *_issue_stats(report),
        "",
        "## 问题明细",
        "",
        *_issue_details(report),
        "",
        "## 人工复核建议",
        "",
        *_review_suggestions(report),
        "",
        *_llm_assistance_lines(llm_assistance),
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
