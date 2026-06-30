"""Private OpenAI-compatible LLM client for read-only assistance.

This module only sends compact document metadata to a private model endpoint.
It never sends full document text by default and never returns executable docx
operations.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from src.engine.model.document_model import DocumentModel, ParagraphInfo
from src.engine.model.operation_model import StyleCheckReport
from src.llm.client import LLMCallError, build_openai_compatible_client, call_chat_completion


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
DEFAULT_TIMEOUT_SECONDS = 8.0
DEFAULT_MAX_RETRIES = 0
DEFAULT_PREVIEW_CHARS = 80
DEFAULT_MAX_PARAGRAPHS = 80
DEFAULT_ERROR_BODY_CHARS = 1000
DEFAULT_USER_AGENT = "docx-template-agent/0.1 OpenAI-compatible-client"
DEFAULT_AVAILABLE_TEMPLATES = ("report",)
ADVISORY_ONLY_INSTRUCTION = (
    "Only output advisory JSON for human review. Do not generate FormatOperation. "
    "Do not generate apply_paragraph_style, apply_table_style, or apply_table_header_style. "
    "Do not generate replace_text, delete_paragraph, delete_table, or any document mutation. "
    "LLM recommendations must not be used as the final formatting basis."
)
SENSITIVE_PATTERNS = (
    (re.compile(r"https?://[^\s<>()]+|www\.[^\s<>()]+", re.IGNORECASE), "<URL>"),
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE), "<EMAIL>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<IP>"),
    (re.compile(r"(?<!\d)(?:\+?\d{1,3}[-\s]?)?(?:1[3-9]\d{9}|\d{3}[-\s]?\d{3,4}[-\s]?\d{4})(?!\d)"), "<PHONE>"),
)


Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


@dataclass(frozen=True)
class PrivateLLMConfig:
    enabled: bool = False
    endpoint: str = ""
    model: str = ""
    api_key: str = ""
    api_key_env: str = "PRIVATE_LLM_API_KEY"
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_MAX_RETRIES

    @property
    def is_usable(self) -> bool:
        return self.enabled and bool(self.endpoint.strip()) and bool(self.model.strip())


def _env_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_private_llm_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> PrivateLLMConfig:
    """Load private LLM settings from config.yaml with environment overrides."""

    path = Path(config_path)
    raw: dict[str, Any] = {}
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            raw = loaded

    llm = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
    assert isinstance(llm, dict)

    api_key_env = str(llm.get("api_key_env") or "PRIVATE_LLM_API_KEY")
    enabled = bool(llm.get("enabled", False))
    env_enabled = _env_bool(os.getenv("DOCX_TEMPLATE_AGENT_LLM_ENABLED"))
    if env_enabled is not None:
        enabled = env_enabled

    endpoint = str(
        os.getenv("DOCX_TEMPLATE_AGENT_LLM_ENDPOINT")
        or os.getenv("DOCX_TEMPLATE_AGENT_LLM_BASE_URL")
        or llm.get("endpoint")
        or llm.get("base_url")
        or ""
    )
    model = str(os.getenv("DOCX_TEMPLATE_AGENT_LLM_MODEL") or llm.get("model") or "")
    api_key = str(os.getenv(api_key_env) or os.getenv("DOCX_TEMPLATE_AGENT_LLM_API_KEY") or "")

    try:
        timeout = float(os.getenv("DOCX_TEMPLATE_AGENT_LLM_TIMEOUT") or llm.get("timeout") or DEFAULT_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SECONDS
    try:
        max_retries = int(
            os.getenv("DOCX_TEMPLATE_AGENT_LLM_MAX_RETRIES")
            or llm.get("max_retries")
            or DEFAULT_MAX_RETRIES
        )
    except (TypeError, ValueError):
        max_retries = DEFAULT_MAX_RETRIES
    max_retries = max(0, max_retries)

    return PrivateLLMConfig(
        enabled=enabled,
        endpoint=endpoint,
        model=model,
        api_key=api_key,
        api_key_env=api_key_env,
        timeout=timeout,
        max_retries=max_retries,
    )


def _chat_completions_url(endpoint: str) -> str:
    clean = endpoint.rstrip("/")
    if clean.endswith("/chat/completions"):
        return clean
    if clean.endswith("/v1"):
        return f"{clean}/chat/completions"
    return f"{clean}/v1/chat/completions"


def _urllib_transport(
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        _chat_completions_url(endpoint),
        data=data,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _default_transport(
    endpoint: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    api_key = ""
    authorization = headers.get("Authorization") or headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        api_key = authorization[7:].strip()

    client = build_openai_compatible_client(
        base_url=endpoint.rstrip("/"),
        api_key=api_key or "not-used",
        timeout=timeout,
    )
    content = call_chat_completion(
        client,
        model=str(payload.get("model") or ""),
        messages=payload.get("messages") or [],
        temperature=float(payload.get("temperature", 0)),
        response_format=payload.get("response_format"),
    )
    return {"choices": [{"message": {"content": content}}]}


def _http_error_message(exc: urllib.error.HTTPError) -> str:
    body = exc.read().decode("utf-8", errors="replace").strip()
    body_snippet = _truncate(body, DEFAULT_ERROR_BODY_CHARS) if body else "(empty)"
    return (
        f"HTTPError {exc.code} {exc.reason}; "
        f"url={exc.url}; "
        f"body={body_snippet}"
    )


def _truncate(text: str, limit: int = DEFAULT_PREVIEW_CHARS) -> str:
    normalized = " ".join((text or "").split())
    return normalized[:limit]


def _redact_sensitive_text(text: str) -> str:
    redacted = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _safe_preview(text: str, limit: int = DEFAULT_PREVIEW_CHARS) -> str:
    return _truncate(_redact_sensitive_text(text), limit)


def _style_summary(paragraph: ParagraphInfo) -> dict[str, Any]:
    return {
        "role": paragraph.role,
        "style_name": paragraph.style_name,
        "alignment": paragraph.alignment,
        "font_names": sorted({value for value in paragraph.font_names if value}),
        "font_sizes": sorted({value for value in paragraph.font_sizes if value is not None}),
        "bold_values": sorted({value for value in paragraph.bold_values if value is not None}),
        "line_spacing": paragraph.line_spacing,
        "space_before": paragraph.space_before,
        "space_after": paragraph.space_after,
    }


def build_llm_document_snapshot(
    document: DocumentModel,
    *,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
    max_paragraphs: int = DEFAULT_MAX_PARAGRAPHS,
) -> dict[str, Any]:
    """Build a compact read-only snapshot safe to send to the private model."""

    paragraphs = [
        {
            "index": paragraph.index,
            "text_preview": _safe_preview(paragraph.text, preview_chars),
            "style_summary": _style_summary(paragraph),
        }
        for paragraph in document.paragraphs[:max_paragraphs]
    ]
    return {
        "full_text_sent": False,
        "paragraph_text_is_preview_only": True,
        "paragraph_count": document.paragraph_count,
        "table_count": document.table_count,
        "styles": document.styles[:100],
        "paragraphs": paragraphs,
        "truncated": len(document.paragraphs) > max_paragraphs,
    }


class PrivateLLMClient:
    """Read-only private LLM helper.

    The client is deliberately narrow: it can classify, suggest heading roles,
    and summarize reports. It cannot produce operations and failures are
    represented as disabled/unavailable results for rule-only fallback.
    """

    def __init__(
        self,
        config: PrivateLLMConfig | None = None,
        *,
        transport: Transport | None = None,
    ) -> None:
        self.config = config or load_private_llm_config()
        self._transport = transport or _default_transport

    @classmethod
    def from_config_file(cls, config_path: str | Path = DEFAULT_CONFIG_PATH) -> "PrivateLLMClient":
        return cls(load_private_llm_config(config_path))

    def is_enabled(self) -> bool:
        return self.config.is_usable

    def health_check(self) -> dict[str, Any]:
        if not self.is_enabled():
            return self._fallback("llm_disabled_or_not_configured", task="health_check")

        request_payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a private LLM health check endpoint. Reply with only: ok",
                },
                {
                    "role": "user",
                    "content": "health_check: reply with only ok",
                },
            ],
            "temperature": 0,
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        try:
            response = self._request_with_retries(headers, request_payload)
            content = self._extract_content(response)
            parsed = self._parse_health_check_content(content)
            return {
                "available": True,
                "mode": "private_llm",
                "task": "health_check",
                "result": parsed,
                "operations_generated": False,
                "operations_source": "rule_engine_only",
            }
        except (OSError, TimeoutError, urllib.error.URLError, LLMCallError, ValueError, KeyError, json.JSONDecodeError) as exc:
            return self._fallback(f"{exc.__class__.__name__}: {exc}", task="health_check")

    def assist_document_type(self, document: DocumentModel) -> dict[str, Any]:
        return self._safe_chat(
            "document_type",
            document,
            (
                "Identify the likely document type from paragraph indexes, short previews, "
                "and style summaries only. Return confidence, reason, and warnings when useful."
            ),
        )

    def assist_heading_levels(self, document: DocumentModel) -> dict[str, Any]:
        return self._safe_chat(
            "heading_levels",
            document,
            (
                "Suggest likely heading levels by paragraph index. Return advisory labels only. "
                "Do not generate formatting operations, FormatOperation, or document mutations."
            ),
        )

    def suggest_template(
        self,
        document: DocumentModel,
        available_templates: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        templates = list(available_templates or DEFAULT_AVAILABLE_TEMPLATES)
        return self._safe_chat(
            "template_recommendation",
            document,
            (
                "Recommend the most likely template id for this document as advisory metadata only. "
                "Return JSON with recommended_template, confidence, reason, and warnings. "
                "The recommendation must not override the CLI --template value and must not drive formatting."
            ),
            extra={
                "available_templates": templates,
                "recommendation_scope": "advisory_only",
                "may_override_cli_template": False,
                "may_drive_formatting": False,
            },
        )

    def summarize_check_report(
        self,
        document: DocumentModel,
        report: StyleCheckReport,
    ) -> dict[str, Any]:
        issue_stats: dict[str, int] = {}
        for issue in report.issues:
            issue_stats[issue.issue_type] = issue_stats.get(issue.issue_type, 0) + 1
        return self._safe_chat(
            "check_report_summary",
            document,
            "Summarize the style check result for human review. Do not generate operations or FormatOperation.",
            extra={
                "issue_count": report.issue_count,
                "operation_count_from_rule_engine": report.operation_count,
                "issue_stats": issue_stats,
            },
        )

    def build_assistance(
        self,
        document: DocumentModel,
        report: StyleCheckReport,
    ) -> dict[str, Any]:
        if not self.is_enabled():
            return self._fallback("llm_disabled_or_not_configured")

        document_type = self.assist_document_type(document)
        if document_type.get("available") is not True:
            fallback = self._fallback(str(document_type.get("reason") or "llm_unavailable"))
            fallback["document_type"] = document_type
            return fallback

        heading_levels = self.assist_heading_levels(document)
        if heading_levels.get("available") is not True:
            fallback = self._fallback(str(heading_levels.get("reason") or "llm_unavailable"))
            fallback["document_type"] = document_type
            fallback["heading_levels"] = heading_levels
            return fallback

        report_summary = self.summarize_check_report(document, report)
        if report_summary.get("available") is not True:
            fallback = self._fallback(str(report_summary.get("reason") or "llm_unavailable"))
            fallback["document_type"] = document_type
            fallback["heading_levels"] = heading_levels
            fallback["report_summary"] = report_summary
            return fallback

        template_recommendation = self.suggest_template(document)
        if template_recommendation.get("available") is not True:
            fallback = self._fallback(str(template_recommendation.get("reason") or "llm_unavailable"))
            fallback["document_type"] = document_type
            fallback["heading_levels"] = heading_levels
            fallback["report_summary"] = report_summary
            fallback["template_recommendation"] = template_recommendation
            return fallback

        return {
            "available": True,
            "mode": "private_llm",
            "document_type": document_type,
            "heading_levels": heading_levels,
            "report_summary": report_summary,
            "template_recommendation": template_recommendation,
            "operations_generated": False,
            "operations_source": "rule_engine_only",
        }

    def _safe_chat(
        self,
        task: str,
        document: DocumentModel,
        instruction: str,
        *,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.is_enabled():
            return self._fallback("llm_disabled_or_not_configured", task=task)

        payload_data = build_llm_document_snapshot(document)
        if extra:
            payload_data["report"] = extra

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a private docx analysis assistant. You only provide advisory "
                    "classification and summaries. You must not create, modify, or execute "
                    f"docx operations. {ADVISORY_ONLY_INSTRUCTION} Return concise JSON."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": task,
                        "instruction": instruction,
                        "input_limits": {
                            "full_text_sent": False,
                            "paragraph_text_is_preview_only": True,
                        },
                        "document_snapshot": payload_data,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        request_payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": DEFAULT_USER_AGENT,
        }
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        try:
            response = self._request_with_retries(headers, request_payload)
            content = self._extract_content(response)
            parsed = self._parse_json_content(content)
            return {
                "available": True,
                "task": task,
                "result": parsed,
                "operations_generated": False,
            }
        except (OSError, TimeoutError, urllib.error.URLError, LLMCallError, ValueError, KeyError, json.JSONDecodeError) as exc:
            return self._fallback(f"{exc.__class__.__name__}: {exc}", task=task)

    def _request_with_retries(
        self,
        headers: dict[str, str],
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for _ in range(self.config.max_retries + 1):
            try:
                return self._transport(
                    self.config.endpoint,
                    headers,
                    request_payload,
                    self.config.timeout,
                )
            except urllib.error.HTTPError as exc:
                last_exc = OSError(_http_error_message(exc))
            except LLMCallError as exc:
                last_exc = exc
            except (OSError, TimeoutError, urllib.error.URLError) as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("LLM request did not run")

    @staticmethod
    def _extract_content(response: dict[str, Any]) -> str:
        choices = response["choices"]
        if not choices:
            raise ValueError("LLM response has no choices")
        message = choices[0]["message"]
        content = message["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("LLM response content is empty")
        return content

    @staticmethod
    def _parse_json_content(content: str) -> Any:
        return json.loads(content)

    @staticmethod
    def _parse_health_check_content(content: str) -> dict[str, Any]:
        text = content.strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"status": text}
        if isinstance(parsed, dict):
            return parsed
        return {"status": parsed}

    @staticmethod
    def _fallback(reason: str, *, task: str | None = None) -> dict[str, Any]:
        result = {
            "available": False,
            "mode": "rule_only_fallback",
            "reason": reason,
            "operations_generated": False,
            "operations_source": "rule_engine_only",
        }
        if task:
            result["task"] = task
        return result
