"""JSON report writer for operation plans."""

from __future__ import annotations

import json
from pathlib import Path

from src.engine.model.operation_model import StyleCheckReport


def operations_path_for_output_docx(output_docx_path: str | Path) -> Path:
    output_path = Path(output_docx_path)
    return output_path.with_name(f"{output_path.stem}_operations.json")


def write_json_report(report: StyleCheckReport, output_docx_path: str | Path) -> Path:
    report_path = operations_path_for_output_docx(output_docx_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report_path
