"""Content integrity snapshots for conservative docx formatting."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.engine.model.document_model import DocumentModel


def normalize_docx_text(text: str | None) -> str:
    """Normalize parser-only line ending differences without hiding text edits."""

    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


PROTECTION_SCOPE = {
    "body_paragraphs": True,
    "tables_and_cell_paragraphs": True,
    "headers_footers_protected": False,
    "textboxes_protected": False,
}


def _fingerprint(values: Any) -> str:
    payload = json.dumps(
        values,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def content_snapshot(document: DocumentModel) -> dict[str, Any]:
    paragraph_payload = [
        {
            "paragraph_index": paragraph.index,
            "text": normalize_docx_text(paragraph.text),
        }
        for paragraph in sorted(document.paragraphs, key=lambda item: item.index)
    ]
    table_payload = []
    for table in sorted(document.tables, key=lambda item: item.index):
        cells = []
        for cell in sorted(table.cells, key=lambda item: (item.row_index, item.col_index)):
            paragraph_texts = cell.paragraph_texts or [cell.text]
            cells.append(
                {
                    "row_index": cell.row_index,
                    "cell_index": cell.col_index,
                    "paragraphs": [
                        {
                            "paragraph_index": index,
                            "text": normalize_docx_text(text),
                        }
                        for index, text in enumerate(paragraph_texts, start=1)
                    ],
                }
            )
        table_payload.append(
            {
                "table_index": table.index,
                "rows": table.rows,
                "cols": table.cols,
                "cells": cells,
            }
        )
    return {
        "protection_scope": dict(PROTECTION_SCOPE),
        "paragraph_count": document.paragraph_count,
        "table_count": document.table_count,
        "paragraph_payload_fingerprint": _fingerprint(paragraph_payload),
        "table_payload_fingerprint": _fingerprint(table_payload),
    }


def compare_content_snapshots(
    before: dict[str, Any],
    after: dict[str, Any],
) -> list[str]:
    checks = (
        ("paragraph_count", "paragraph count changed"),
        ("table_count", "table count changed"),
        ("paragraph_payload_fingerprint", "paragraph text changed"),
        ("table_payload_fingerprint", "table cell text changed"),
    )
    errors: list[str] = []
    for key, message in checks:
        if before.get(key) != after.get(key):
            errors.append(message)
    return errors
