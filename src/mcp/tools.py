"""JSON MCP tool adapters for the offline docx engine.

This module intentionally stays at the boundary layer. It validates MCP
requests, prepares output paths, writes logs, and delegates document work to
``src.engine`` modules only.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from src.engine.checker.style_checker import check_styles
from src.engine.formatter.apply_template import apply_operations_transactional
from src.engine.parser.docx_parser import parse_docx
from src.engine.parser.structure_detector import detect_structure
from src.engine.reporter.json_report import write_json_report
from src.engine.reporter.markdown_report import write_markdown_report
from src.engine.template.template_loader import list_templates as list_engine_templates
from src.engine.template.template_loader import load_template
from src.llm.assistance import build_llm_assistance, write_llm_analysis


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_DIR = PROJECT_ROOT / "templates"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "samples" / "output"
ALLOWED_OUTPUT_DIRS = (
    DEFAULT_OUTPUT_DIR,
    PROJECT_ROOT / "outputs",
)
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "mcp_server.log"


def _logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("docx_template_agent.mcp")
    if not logger.handlers:
        handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


LOGGER = _logger()


def _json_error(tool_name: str, exc: Exception) -> dict[str, Any]:
    LOGGER.exception("%s failed: %s", tool_name, exc)
    return {
        "ok": False,
        "tool": tool_name,
        "error": {
            "type": exc.__class__.__name__,
            "message": str(exc),
        },
    }


def _normalize_request(request: dict[str, Any] | None) -> dict[str, Any]:
    if request is None:
        return {}
    if not isinstance(request, dict):
        raise TypeError("request must be a JSON object")
    return request


def _resolve_docx_input(value: Any) -> Path:
    if not value:
        raise ValueError("input_path is required")
    path = Path(str(value)).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"input docx not found: {path}")
    if not path.is_file():
        raise ValueError(f"input path is not a file: {path}")
    if path.suffix.lower() != ".docx":
        raise ValueError(f"input_path must point to a .docx file: {path}")
    return path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_output_dir(value: Any = None) -> Path:
    output_dir = Path(str(value)).expanduser() if value else DEFAULT_OUTPUT_DIR
    output_dir = output_dir.resolve()
    allowed = tuple(root.resolve() for root in ALLOWED_OUTPUT_DIRS)
    if not any(_is_relative_to(output_dir, root) for root in allowed):
        allowed_text = ", ".join(str(root) for root in allowed)
        raise ValueError(f"output_dir must be inside one of: {allowed_text}")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _safe_stem(path: Path) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", path.stem).strip("._")
    return stem or "document"


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _output_docx_path(input_file: Path, output_dir: Path) -> Path:
    candidate = output_dir / f"{_safe_stem(input_file)}_formatted_{_timestamp()}.docx"
    if candidate.resolve() == input_file.resolve():
        raise ValueError("output docx path cannot overwrite input_path")
    return candidate


def _report_base_path(input_file: Path, output_dir: Path) -> Path:
    return output_dir / f"{_safe_stem(input_file)}_review_{_timestamp()}.docx"


def _template_ref(request: dict[str, Any]) -> str:
    return str(request.get("template") or request.get("template_id") or "report")


def _load_template(request: dict[str, Any]) -> dict[str, Any]:
    template_dir = request.get("template_dir") or DEFAULT_TEMPLATE_DIR
    return load_template(_template_ref(request), template_dir)


def _analyze(input_file: Path):
    return detect_structure(parse_docx(input_file))


def _check(input_file: Path, request: dict[str, Any]):
    template = _load_template(request)
    document = _analyze(input_file)
    report = check_styles(document, template)
    return template, document, report


def _llm_fallback_from_exception(exc: Exception) -> dict[str, Any]:
    return {
        "available": False,
        "mode": "rule_only_fallback",
        "status": "fallback",
        "error": f"{exc.__class__.__name__}: {exc}",
        "operations_source": "rule_engine_only",
        "operations_generated": False,
    }


def _maybe_build_llm_assistance(
    request: dict[str, Any],
    document: Any,
    report: Any,
) -> dict[str, Any] | None:
    if not bool(request.get("use_llm", False)):
        return None
    try:
        return build_llm_assistance(document, report)
    except Exception as exc:  # Keep MCP formatting/reporting rule-engine-first.
        LOGGER.exception("LLM assistance failed; using rule-only fallback: %s", exc)
        return _llm_fallback_from_exception(exc)


def list_templates(request: dict[str, Any] | None = None) -> dict[str, Any]:
    """List available formatting templates as JSON."""

    tool_name = "list_templates"
    try:
        req = _normalize_request(request)
        template_dir = Path(str(req.get("template_dir") or DEFAULT_TEMPLATE_DIR)).resolve()
        templates = list_engine_templates(template_dir)
        LOGGER.info("%s ok template_dir=%s count=%s", tool_name, template_dir, len(templates))
        return {
            "ok": True,
            "tool": tool_name,
            "template_dir": str(template_dir),
            "templates": templates,
            "count": len(templates),
        }
    except Exception as exc:
        return _json_error(tool_name, exc)


def analyze_docx(request: dict[str, Any]) -> dict[str, Any]:
    """Analyze docx structure using the read-only engine parser."""

    tool_name = "analyze_docx"
    try:
        req = _normalize_request(request)
        input_file = _resolve_docx_input(req.get("input_path"))
        document = _analyze(input_file)

        include_paragraphs = bool(req.get("include_paragraphs", True))
        include_tables = bool(req.get("include_tables", True))
        preview_chars = int(req.get("preview_chars", 120))
        paragraphs = []
        tables = []
        if include_paragraphs:
            paragraphs = [
                {
                    "index": paragraph.index,
                    "role": paragraph.role,
                    "style_name": paragraph.style_name,
                    "text_preview": paragraph.text[:preview_chars],
                }
                for paragraph in document.paragraphs
            ]
        if include_tables:
            tables = [
                {
                    "index": table.index,
                    "rows": table.rows,
                    "cols": table.cols,
                    "cell_count": len(table.cells),
                }
                for table in document.tables
            ]

        LOGGER.info("%s ok input=%s", tool_name, input_file)
        return {
            "ok": True,
            "tool": tool_name,
            "input_path": str(input_file),
            "paragraph_count": document.paragraph_count,
            "table_count": document.table_count,
            "styles": document.styles,
            "paragraphs": paragraphs,
            "tables": tables,
        }
    except Exception as exc:
        return _json_error(tool_name, exc)


def check_docx_style(request: dict[str, Any]) -> dict[str, Any]:
    """Check docx style against a template and return issues and operations."""

    tool_name = "check_docx_style"
    try:
        req = _normalize_request(request)
        input_file = _resolve_docx_input(req.get("input_path"))
        template, document, report = _check(input_file, req)

        include_issues = bool(req.get("include_issues", True))
        include_operations = bool(req.get("include_operations", True))
        LOGGER.info(
            "%s ok input=%s template=%s issues=%s operations=%s",
            tool_name,
            input_file,
            template["template_id"],
            report.issue_count,
            report.operation_count,
        )
        return {
            "ok": True,
            "tool": tool_name,
            "input_path": str(input_file),
            "template": str(template["template_id"]),
            "paragraph_count": document.paragraph_count,
            "table_count": document.table_count,
            "issue_count": report.issue_count,
            "operation_count": report.operation_count,
            "issues": report.model_dump(mode="json")["issues"] if include_issues else [],
            "operations": report.model_dump(mode="json")["operations"]
            if include_operations
            else [],
        }
    except Exception as exc:
        return _json_error(tool_name, exc)


def apply_docx_template(request: dict[str, Any]) -> dict[str, Any]:
    """Apply safe formatting operations and write a new docx plus reports."""

    tool_name = "apply_docx_template"
    try:
        req = _normalize_request(request)
        input_file = _resolve_docx_input(req.get("input_path"))
        output_dir = _resolve_output_dir(req.get("output_dir"))
        output_docx = _output_docx_path(input_file, output_dir)

        template, document, report = _check(input_file, req)
        execution_report = apply_operations_transactional(
            input_file,
            output_docx,
            report.operations,
            template=template,
            document_before=document,
            report_before=report,
            retain_failed_temp=False,
        )
        llm_assistance = _maybe_build_llm_assistance(req, document, report)
        llm_analysis = write_llm_analysis(llm_assistance, output_docx) if llm_assistance else None
        markdown_report = write_markdown_report(
            report,
            output_docx,
            input_file,
            str(template["template_id"]),
            document.paragraph_count,
            document.table_count,
            llm_assistance=llm_assistance,
        )
        json_report = write_json_report(report, output_docx)
        failed_results = [
            result for result in execution_report.execution_results if result.get("status") == "failed"
        ]

        LOGGER.info(
            "%s ok input=%s output=%s template=%s issues=%s operations=%s failed=%s",
            tool_name,
            input_file,
            output_docx,
            template["template_id"],
            report.issue_count,
            report.operation_count,
            len(failed_results),
        )
        success = execution_report.status == "success"
        payload = {
            "ok": success,
            "tool": tool_name,
            "input_path": str(input_file),
            "template": str(template["template_id"]),
            "expected_output_docx_path": str(output_docx),
            "markdown_check_report_path": str(markdown_report),
            "markdown_report_path": str(markdown_report),
            "json_modification_detail_path": str(json_report),
            "json_detail_path": str(json_report),
            "issue_count": report.issue_count,
            "operation_count": report.operation_count,
            "result_count": len(execution_report.execution_results),
            "failed_operation_count": len(failed_results),
            "execution_status": execution_report.status,
            "issues_before": execution_report.issues_before,
            "issues_after": execution_report.issues_after,
            "operations_before": execution_report.operations_before,
            "operations_after": execution_report.operations_after,
            "validation_errors": execution_report.validation_errors,
            "integrity_errors": execution_report.integrity_errors,
            "recheck_errors": execution_report.recheck_errors,
            "temp_file_retained": execution_report.temp_file_retained,
            "results": execution_report.execution_results,
        }
        if success:
            payload["new_docx_path"] = str(output_docx)
            payload["output_docx_path"] = str(output_docx)
        if llm_analysis is not None:
            payload["llm_analysis_path"] = str(llm_analysis)
            payload["llm_status"] = str(llm_assistance.get("status", "fallback"))
            payload["llm_mode"] = str(llm_assistance.get("mode", "rule_only_fallback"))
        return payload
    except Exception as exc:
        return _json_error(tool_name, exc)


def generate_review_report(request: dict[str, Any]) -> dict[str, Any]:
    """Generate markdown and JSON review artifacts without writing a docx."""

    tool_name = "generate_review_report"
    try:
        req = _normalize_request(request)
        input_file = _resolve_docx_input(req.get("input_path"))
        output_dir = _resolve_output_dir(req.get("output_dir"))
        report_base = _report_base_path(input_file, output_dir)

        template, document, report = _check(input_file, req)
        llm_assistance = _maybe_build_llm_assistance(req, document, report)
        llm_analysis = write_llm_analysis(llm_assistance, report_base) if llm_assistance else None
        markdown_report = write_markdown_report(
            report,
            report_base,
            input_file,
            str(template["template_id"]),
            document.paragraph_count,
            document.table_count,
            llm_assistance=llm_assistance,
        )
        json_report = write_json_report(report, report_base)

        LOGGER.info(
            "%s ok input=%s template=%s issues=%s operations=%s",
            tool_name,
            input_file,
            template["template_id"],
            report.issue_count,
            report.operation_count,
        )
        payload = {
            "ok": True,
            "tool": tool_name,
            "input_path": str(input_file),
            "template": str(template["template_id"]),
            "markdown_report_path": str(markdown_report),
            "json_detail_path": str(json_report),
            "issue_count": report.issue_count,
            "operation_count": report.operation_count,
        }
        if llm_analysis is not None:
            payload["llm_analysis_path"] = str(llm_analysis)
            payload["llm_status"] = str(llm_assistance.get("status", "fallback"))
            payload["llm_mode"] = str(llm_assistance.get("mode", "rule_only_fallback"))
        return payload
    except Exception as exc:
        return _json_error(tool_name, exc)
