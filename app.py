"""CLI entrypoint for the offline docx template formatter."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from src.engine.checker.style_checker import check_styles
from src.engine.formatter.apply_template import apply_operations
from src.engine.parser.docx_parser import parse_docx
from src.engine.parser.structure_detector import detect_structure
from src.engine.reporter.json_report import write_json_report
from src.engine.reporter.markdown_report import write_markdown_report
from src.engine.template.template_loader import load_template
from src.llm.assistance import build_llm_assistance, write_llm_analysis
from src.llm.private_llm_client import PrivateLLMClient


def log_step(message: str) -> None:
    print(f"[docx-template-agent] {message}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline docx template formatting CLI.")
    parser.add_argument("--input", required=True, help="Input .docx file path.")
    parser.add_argument("--template", default="report", help="Template id such as 'report', or YAML path.")
    parser.add_argument("--output", required=True, help="Output .docx file path or output directory.")
    return parser


def build_llm_test_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test private LLM connectivity.")
    parser.add_argument("command", choices=["llm-test"], help="Run private LLM health check.")
    return parser


def _output_docx_path(input_file: Path, output_path: Path) -> Path:
    if output_path.suffix.lower() == ".docx":
        return output_path
    return output_path / f"{input_file.stem}_formatted.docx"


def _validate_paths(input_path: str | Path, output_path: str | Path) -> tuple[Path, Path]:
    input_file = Path(input_path).resolve()
    raw_output = Path(output_path)
    output_docx = _output_docx_path(input_file, raw_output).resolve()

    if not input_file.exists():
        raise FileNotFoundError(f"input file not found: {input_file}")
    if not input_file.is_file():
        raise ValueError(f"input path is not a file: {input_file}")
    if input_file.suffix.lower() != ".docx":
        raise ValueError(f"input file must be a .docx file: {input_file}")
    if output_docx == input_file:
        raise ValueError(f"output file cannot overwrite input file: {output_docx}")
    if output_docx.suffix.lower() != ".docx":
        raise ValueError(f"output must resolve to a .docx file: {output_docx}")

    return input_file, output_docx


def run(input_path: str, template_id_or_path: str, output_path: str) -> dict[str, Any]:
    log_step("1/11 validate input path")
    input_file, output_docx = _validate_paths(input_path, output_path)
    log_step("2/11 validate output path")
    output_docx.parent.mkdir(parents=True, exist_ok=True)

    log_step(f"3/11 load template: {template_id_or_path}")
    template = load_template(template_id_or_path)

    log_step(f"4/11 parse docx: {input_file}")
    document = parse_docx(input_file)

    log_step("5/11 detect paragraph roles")
    detected = detect_structure(document)

    log_step("6/11 check styles")
    style_report = check_styles(detected, template)

    llm_assistance = build_llm_assistance(
        detected,
        style_report,
        client_factory=PrivateLLMClient,
    )

    log_step(f"7/11 generated operations: {style_report.operation_count}")

    log_step(f"8/11 apply formatting to new file: {output_docx}")
    results = apply_operations(input_file, output_docx, style_report.operations)

    log_step("9/11 write markdown report")
    markdown_report = write_markdown_report(
        style_report,
        output_docx,
        input_file,
        template["template_id"],
        detected.paragraph_count,
        detected.table_count,
        llm_assistance=llm_assistance,
    )

    log_step("10/11 write json report")
    json_report = write_json_report(style_report, output_docx)
    llm_analysis = write_llm_analysis(llm_assistance, output_docx)

    failed_results = [result for result in results if result.get("status") == "failed"]
    payload = {
        "input": str(input_file),
        "output": str(output_docx),
        "template": template["template_id"],
        "paragraph_count": detected.paragraph_count,
        "table_count": detected.table_count,
        "issue_count": style_report.issue_count,
        "operation_count": style_report.operation_count,
        "result_count": len(results),
        "failed_operation_count": len(failed_results),
        "markdown_report": str(markdown_report),
        "json_report": str(json_report),
        "llm_analysis": str(llm_analysis),
        "llm_assistance": llm_assistance,
        "results": results,
    }

    log_step("11/11 print summary")
    print_summary(payload)
    return payload


def print_summary(payload: dict[str, Any]) -> None:
    print("")
    print("Processing summary")
    print(f"- Input file: {payload['input']}")
    print(f"- Output file: {payload['output']}")
    print(f"- Template: {payload['template']}")
    print(f"- Paragraph count: {payload['paragraph_count']}")
    print(f"- Table count: {payload['table_count']}")
    print(f"- Issue count: {payload['issue_count']}")
    print(f"- Operation count: {payload['operation_count']}")
    print(f"- Failed operations: {payload['failed_operation_count']}")
    print(f"- Markdown report: {payload['markdown_report']}")
    print(f"- JSON report: {payload['json_report']}")
    print(f"- LLM analysis: {payload['llm_analysis']}")
    llm = payload.get("llm_assistance") or {}
    print(f"- LLM mode: {llm.get('mode', 'rule_only_fallback')}")


def run_llm_test() -> dict[str, Any]:
    client = PrivateLLMClient()
    result = client.health_check()

    print("[docx-template-agent] LLM health check")
    print(f"- enabled: {client.config.enabled}")
    print(f"- endpoint: {client.config.endpoint or '(empty)'}")
    print(f"- model: {client.config.model or '(empty)'}")
    print(f"- timeout: {client.config.timeout}")
    print(f"- max_retries: {client.config.max_retries}")
    print(f"- available: {result.get('available')}")
    print(f"- mode: {result.get('mode', 'rule_only_fallback')}")
    print(f"- operations_generated: {result.get('operations_generated', False)}")
    print(f"- operations_source: {result.get('operations_source', 'rule_engine_only')}")
    if result.get("available") is True:
        print("- status: ok")
    else:
        print("- status: fallback")
        print(f"- error: {result.get('reason', 'llm_unavailable')}")
        print("- fallback: rule_engine_only")
    return result


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "llm-test":
        build_llm_test_parser().parse_args()
        result = run_llm_test()
        raise SystemExit(0 if result.get("available") is True else 1)

    args = build_parser().parse_args()
    try:
        run(args.input, args.template, args.output)
    except Exception as exc:
        print(f"[docx-template-agent] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

