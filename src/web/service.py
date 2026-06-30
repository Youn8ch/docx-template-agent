"""Thin web-service adapters around the offline docx engine."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from src.engine.checker.style_checker import check_styles
from src.engine.formatter.apply_template import apply_operations
from src.engine.parser.docx_parser import parse_docx
from src.engine.parser.structure_detector import detect_structure
from src.engine.reporter.json_report import write_json_report
from src.engine.reporter.markdown_report import write_markdown_report
from src.engine.template.template_loader import list_templates as list_engine_templates
from src.engine.template.template_loader import load_template
from src.llm.assistance import build_llm_assistance, write_llm_analysis


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_DIR = PROJECT_ROOT / "templates"
DEFAULT_WEB_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "web"
DOWNLOAD_KEYS = {
    "docx": "formatted_docx",
    "markdown": "markdown_report",
    "json": "json_detail",
    "llm": "llm_analysis",
    "llm_analysis": "llm_analysis",
}


@dataclass(frozen=True)
class WebJobResult:
    job_id: str
    action: str
    template: str
    input_docx: Path
    formatted_docx: Path | None
    markdown_report: Path
    json_detail: Path
    paragraph_count: int
    table_count: int
    issue_count: int
    operation_count: int
    failed_operation_count: int = 0
    llm_analysis: Path | None = None


def list_templates(template_dir: Path = DEFAULT_TEMPLATE_DIR) -> list[dict[str, str]]:
    return list_engine_templates(template_dir)


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._")
    return value or "document"


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _job_dir(output_root: Path = DEFAULT_WEB_OUTPUT_DIR) -> tuple[str, Path]:
    job_id = uuid4().hex
    directory = (output_root / job_id).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    return job_id, directory


def _save_upload(stream: BinaryIO, filename: str, job_directory: Path) -> Path:
    if Path(filename).suffix.lower() != ".docx":
        raise ValueError("only .docx uploads are supported")

    input_docx = job_directory / f"{_safe_stem(filename)}_source_{_timestamp()}.docx"
    with input_docx.open("wb") as file:
        shutil.copyfileobj(stream, file)
    return input_docx


def _check(input_docx: Path, template_id: str):
    template = load_template(template_id, DEFAULT_TEMPLATE_DIR)
    document = detect_structure(parse_docx(input_docx))
    report = check_styles(document, template)
    return template, document, report


def run_check(
    upload: BinaryIO,
    filename: str,
    template_id: str,
    use_llm: bool = False,
) -> WebJobResult:
    job_id, directory = _job_dir()
    input_docx = _save_upload(upload, filename, directory)
    template, document, report = _check(input_docx, template_id)
    report_base = directory / f"{_safe_stem(filename)}_check_{_timestamp()}.docx"
    llm_assistance = None
    llm_analysis = None
    if use_llm:
        llm_assistance = build_llm_assistance(document, report)
        llm_analysis = write_llm_analysis(llm_assistance, report_base)
    markdown_report = write_markdown_report(
        report,
        report_base,
        input_docx,
        str(template["template_id"]),
        document.paragraph_count,
        document.table_count,
        llm_assistance=llm_assistance,
    )
    json_detail = write_json_report(report, report_base)
    return WebJobResult(
        job_id=job_id,
        action="check",
        template=str(template["template_id"]),
        input_docx=input_docx,
        formatted_docx=None,
        markdown_report=markdown_report,
        json_detail=json_detail,
        llm_analysis=llm_analysis,
        paragraph_count=document.paragraph_count,
        table_count=document.table_count,
        issue_count=report.issue_count,
        operation_count=report.operation_count,
    )


def run_format(
    upload: BinaryIO,
    filename: str,
    template_id: str,
    use_llm: bool = False,
) -> WebJobResult:
    job_id, directory = _job_dir()
    input_docx = _save_upload(upload, filename, directory)
    output_docx = directory / f"{_safe_stem(filename)}_formatted_{_timestamp()}.docx"
    template, document, report = _check(input_docx, template_id)
    results = apply_operations(input_docx, output_docx, report.operations)
    llm_assistance = None
    llm_analysis = None
    if use_llm:
        llm_assistance = build_llm_assistance(document, report)
        llm_analysis = write_llm_analysis(llm_assistance, output_docx)
    markdown_report = write_markdown_report(
        report,
        output_docx,
        input_docx,
        str(template["template_id"]),
        document.paragraph_count,
        document.table_count,
        llm_assistance=llm_assistance,
    )
    json_detail = write_json_report(report, output_docx)
    failed_results = [result for result in results if result.get("status") == "failed"]
    return WebJobResult(
        job_id=job_id,
        action="format",
        template=str(template["template_id"]),
        input_docx=input_docx,
        formatted_docx=output_docx,
        markdown_report=markdown_report,
        json_detail=json_detail,
        llm_analysis=llm_analysis,
        paragraph_count=document.paragraph_count,
        table_count=document.table_count,
        issue_count=report.issue_count,
        operation_count=report.operation_count,
        failed_operation_count=len(failed_results),
    )


def resolve_download(job_id: str, artifact: str) -> Path:
    if artifact not in DOWNLOAD_KEYS:
        raise ValueError("unknown download artifact")
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("invalid job id")

    job_directory = (DEFAULT_WEB_OUTPUT_DIR / job_id).resolve()
    output_root = DEFAULT_WEB_OUTPUT_DIR.resolve()
    if output_root not in (job_directory, *job_directory.parents):
        raise ValueError("invalid job path")
    if not job_directory.exists():
        raise FileNotFoundError("job not found")

    patterns = {
        "docx": "*_formatted_*.docx",
        "markdown": "*_check_report.md",
        "json": "*_operations.json",
        "llm": "llm_analysis.json",
        "llm_analysis": "llm_analysis.json",
    }
    matches = sorted(job_directory.glob(patterns[artifact]))
    if not matches:
        raise FileNotFoundError("download artifact not found")
    return matches[-1]
