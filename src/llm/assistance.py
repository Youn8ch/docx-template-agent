"""Shared read-only LLM assistance helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from src.llm.private_llm_client import PrivateLLMClient


def llm_analysis_path(output_path: str | Path) -> Path:
    return Path(output_path).parent / "llm_analysis.json"


def _fallback_from_exception(exc: Exception) -> dict[str, Any]:
    return {
        "available": False,
        "mode": "rule_only_fallback",
        "status": "fallback",
        "error": f"{exc.__class__.__name__}: {exc}",
        "operations_source": "rule_engine_only",
        "operations_generated": False,
    }


def build_llm_assistance(
    document: Any,
    style_report: Any,
    *,
    client_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    try:
        factory = client_factory or PrivateLLMClient
        assistance = factory().build_assistance(document, style_report)
    except Exception as exc:  # LLM must never block rule-engine formatting.
        return _fallback_from_exception(exc)

    if not isinstance(assistance, dict):
        return {
            "available": False,
            "mode": "rule_only_fallback",
            "status": "fallback",
            "error": "PrivateLLMClient.build_assistance returned non-dict result",
            "operations_source": "rule_engine_only",
            "operations_generated": False,
        }

    assistance.setdefault("status", "ok" if assistance.get("available") is True else "fallback")
    assistance.setdefault("operations_source", "rule_engine_only")
    assistance.setdefault("operations_generated", False)
    return assistance


def write_llm_analysis(llm_assistance: dict[str, Any], output_path: str | Path) -> Path:
    analysis_path = llm_analysis_path(output_path)
    analysis_path.parent.mkdir(parents=True, exist_ok=True)
    analysis_path.write_text(
        json.dumps(llm_assistance, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return analysis_path
