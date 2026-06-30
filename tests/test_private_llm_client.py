import json
import urllib.error
import urllib.request
from pathlib import Path

import src.llm.private_llm_client as private_llm_client
from src.engine.model.document_model import DocumentModel, ParagraphInfo, TableCellInfo, TableInfo
from src.engine.model.operation_model import StyleCheckReport, StyleIssue
from src.llm.client import LLMCallError
from src.llm.private_llm_client import (
    PrivateLLMClient,
    PrivateLLMConfig,
    build_llm_document_snapshot,
    load_private_llm_config,
)


def _document() -> DocumentModel:
    return DocumentModel(
        filepath=Path("sample.docx"),
        paragraphs=[
            ParagraphInfo(
                index=1,
                text="A" * 200,
                role="title",
                style_name="Title",
                font_names=["SimSun"],
                font_sizes=[16],
                bold_values=[True],
            ),
            ParagraphInfo(index=2, text="Body paragraph", role="body", style_name="Normal"),
        ],
        styles=["Title", "Normal"],
    )


def test_load_private_llm_config_uses_yaml_and_environment(tmp_path, monkeypatch):
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "llm:",
                "  enabled: true",
                "  endpoint: http://private-model:8000/v1",
                "  model: local-docx-model",
                "  api_key_env: TEST_PRIVATE_LLM_KEY",
                "  timeout: 3",
                "  max_retries: 1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_PRIVATE_LLM_KEY", "secret")

    loaded = load_private_llm_config(config)

    assert loaded.enabled is True
    assert loaded.endpoint == "http://private-model:8000/v1"
    assert loaded.model == "local-docx-model"
    assert loaded.api_key == "secret"
    assert loaded.timeout == 3
    assert loaded.max_retries == 1


def test_load_private_llm_config_accepts_base_url_alias(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "llm:",
                "  enabled: true",
                "  base_url: http://private-model:8000/v1",
                "  model: local-docx-model",
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_private_llm_config(config)

    assert loaded.endpoint == "http://private-model:8000/v1"


def test_disabled_client_falls_back_to_rule_only_mode():
    client = PrivateLLMClient(PrivateLLMConfig(enabled=False))

    assistance = client.build_assistance(_document(), StyleCheckReport(template_id="report"))

    assert assistance["available"] is False
    assert assistance["mode"] == "rule_only_fallback"
    assert assistance["operations_generated"] is False
    assert assistance["operations_source"] == "rule_engine_only"


def test_document_snapshot_sends_only_preview_and_style_summary():
    snapshot = build_llm_document_snapshot(_document(), preview_chars=20)

    first = snapshot["paragraphs"][0]
    assert snapshot["full_text_sent"] is False
    assert snapshot["paragraph_text_is_preview_only"] is True
    assert first["index"] == 1
    assert first["text_preview"] == "A" * 20
    assert "text" not in first
    assert first["style_summary"]["style_name"] == "Title"
    assert first["style_summary"]["font_names"] == ["SimSun"]


def test_document_snapshot_redacts_sensitive_info_in_paragraph_preview():
    document = DocumentModel(
        filepath=Path("sample.docx"),
        paragraphs=[
            ParagraphInfo(
                index=1,
                text=(
                    "Contact admin@example.com from 192.168.1.10, "
                    "phone 13800138000, visit https://internal.example.com/path."
                ),
            )
        ],
    )

    snapshot = build_llm_document_snapshot(document, preview_chars=200)
    preview = snapshot["paragraphs"][0]["text_preview"]

    assert "<EMAIL>" in preview
    assert "<IP>" in preview
    assert "<PHONE>" in preview
    assert "<URL>" in preview
    assert "admin@example.com" not in preview
    assert "192.168.1.10" not in preview
    assert "13800138000" not in preview
    assert "https://internal.example.com/path" not in preview


def test_document_snapshot_keeps_preview_truncated_without_text_field():
    snapshot = build_llm_document_snapshot(_document(), preview_chars=12)
    first = snapshot["paragraphs"][0]

    assert first["text_preview"] == "A" * 12
    assert "text" not in first


def test_document_snapshot_does_not_send_table_content():
    document = DocumentModel(
        filepath=Path("sample.docx"),
        paragraphs=[ParagraphInfo(index=1, text="Body")],
        tables=[
            TableInfo(
                index=1,
                cells=[
                    TableCellInfo(
                        row_index=0,
                        col_index=0,
                        text="secret table value admin@example.com 192.168.1.10",
                    )
                ],
            )
        ],
    )

    snapshot = build_llm_document_snapshot(document)
    serialized = json.dumps(snapshot, ensure_ascii=False)

    assert snapshot["table_count"] == 1
    assert "tables" not in snapshot
    assert "secret table value" not in serialized
    assert "admin@example.com" not in serialized
    assert "192.168.1.10" not in serialized


def test_enabled_client_calls_openai_compatible_transport_without_operations():
    captured = {}

    def transport(endpoint, headers, payload, timeout):
        captured["endpoint"] = endpoint
        captured["headers"] = headers
        captured["payload"] = payload
        captured["timeout"] = timeout
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "document_type": "report",
                                "confidence": 0.8,
                            }
                        )
                    }
                }
            ]
        }

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="http://private-model:8000/v1",
            model="local-docx-model",
            api_key="secret",
            timeout=5,
        ),
        transport=transport,
    )

    result = client.assist_document_type(_document())
    sent = json.loads(captured["payload"]["messages"][1]["content"])
    first_paragraph = sent["document_snapshot"]["paragraphs"][0]

    assert result["available"] is True
    assert result["operations_generated"] is False
    assert result["result"]["document_type"] == "report"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert first_paragraph["text_preview"] == "A" * 80
    assert "text" not in first_paragraph


def test_report_summary_labels_operations_as_rule_engine_only():
    def transport(endpoint, headers, payload, timeout):
        sent = json.loads(payload["messages"][1]["content"])
        assert sent["document_snapshot"]["report"]["operation_count_from_rule_engine"] == 0
        return {"choices": [{"message": {"content": '{"summary":"ok"}'}}]}

    report = StyleCheckReport(
        template_id="report",
        issues=[
            StyleIssue(
                issue_id="issue-0001",
                issue_type="font_size",
                target_type="paragraph",
                target_index=1,
                message="size mismatch",
            )
        ],
    )
    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="http://private-model:8000/v1",
            model="local-docx-model",
        ),
        transport=transport,
    )

    result = client.summarize_check_report(_document(), report)

    assert result["available"] is True
    assert result["operations_generated"] is False


def test_assist_heading_levels_returns_advisory_without_operations():
    captured = {}

    def transport(endpoint, headers, payload, timeout):
        captured["payload"] = payload
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "heading_levels": {"1": "title", "2": "body"},
                                "confidence": 0.7,
                                "reason": "style summaries suggest a title followed by body text",
                            }
                        )
                    }
                }
            ]
        }

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="http://private-model:8000/v1",
            model="local-docx-model",
        ),
        transport=transport,
    )

    result = client.assist_heading_levels(_document())
    sent = json.loads(captured["payload"]["messages"][1]["content"])

    assert result["available"] is True
    assert result["task"] == "heading_levels"
    assert result["operations_generated"] is False
    assert sent["task"] == "heading_levels"
    assert "advisory labels only" in sent["instruction"]
    assert "FormatOperation" in sent["instruction"]


def test_suggest_template_returns_advisory_recommendation_without_operations():
    captured = {}

    def transport(endpoint, headers, payload, timeout):
        captured["payload"] = payload
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "recommended_template": "report",
                                "confidence": 0.82,
                                "reason": "document appears to be a short report",
                                "warnings": ["advisory only"],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="http://private-model:8000/v1",
            model="local-docx-model",
        ),
        transport=transport,
    )

    result = client.suggest_template(_document(), available_templates=["report", "memo"])
    sent = json.loads(captured["payload"]["messages"][1]["content"])

    assert result["available"] is True
    assert result["task"] == "template_recommendation"
    assert result["operations_generated"] is False
    assert result["result"]["recommended_template"] == "report"
    assert result["result"]["confidence"] == 0.82
    assert result["result"]["warnings"] == ["advisory only"]
    assert sent["document_snapshot"]["report"]["available_templates"] == ["report", "memo"]
    assert sent["document_snapshot"]["report"]["may_override_cli_template"] is False
    assert sent["document_snapshot"]["report"]["may_drive_formatting"] is False


def test_build_assistance_includes_template_recommendation():
    def transport(endpoint, headers, payload, timeout):
        sent = json.loads(payload["messages"][1]["content"])
        task = sent["task"]
        results = {
            "document_type": {"document_type": "report", "confidence": 0.8},
            "heading_levels": {"heading_levels": {"1": "title"}, "confidence": 0.7},
            "check_report_summary": {"summary": "ok", "confidence": 0.9},
            "template_recommendation": {
                "recommended_template": "report",
                "confidence": 0.85,
                "reason": "matches report-like headings",
                "warnings": ["does not override CLI template"],
            },
        }
        return {"choices": [{"message": {"content": json.dumps(results[task], ensure_ascii=False)}}]}

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="http://private-model:8000/v1",
            model="local-docx-model",
        ),
        transport=transport,
    )

    assistance = client.build_assistance(_document(), StyleCheckReport(template_id="report"))

    assert assistance["available"] is True
    assert assistance["operations_generated"] is False
    assert assistance["operations_source"] == "rule_engine_only"
    assert assistance["template_recommendation"]["result"]["recommended_template"] == "report"


def test_llm_prompts_explicitly_forbid_operation_generation():
    captured_payloads = []

    def transport(endpoint, headers, payload, timeout):
        captured_payloads.append(payload)
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="http://private-model:8000/v1",
            model="local-docx-model",
        ),
        transport=transport,
    )

    client.assist_document_type(_document())
    client.assist_heading_levels(_document())
    client.summarize_check_report(_document(), StyleCheckReport(template_id="report"))
    client.suggest_template(_document())

    prompts = "\n".join(
        "\n".join(message["content"] for message in payload["messages"])
        for payload in captured_payloads
    )
    for forbidden in (
        "FormatOperation",
        "apply_paragraph_style",
        "apply_table_style",
        "apply_table_header_style",
        "replace_text",
        "delete_paragraph",
        "delete_table",
    ):
        assert forbidden in prompts
    assert "Only output advisory JSON" in prompts
    assert "must not be used as the final formatting basis" in prompts


def test_health_check_disabled_client_returns_rule_only_fallback():
    client = PrivateLLMClient(PrivateLLMConfig(enabled=False))

    result = client.health_check()

    assert result["available"] is False
    assert result["task"] == "health_check"
    assert result["mode"] == "rule_only_fallback"
    assert result["operations_generated"] is False
    assert result["operations_source"] == "rule_engine_only"


def test_health_check_uses_minimal_payload_without_docx_data():
    captured = {}

    def transport(endpoint, headers, payload, timeout):
        captured["payload"] = payload
        return {"choices": [{"message": {"content": '{"status":"ok"}'}}]}

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="http://private-model:8000/v1",
            model="local-docx-model",
        ),
        transport=transport,
    )

    result = client.health_check()

    assert result["available"] is True
    assert result["mode"] == "private_llm"
    assert result["operations_generated"] is False
    assert result["operations_source"] == "rule_engine_only"
    assert result["result"]["status"] == "ok"
    assert set(captured["payload"]) == {"model", "messages", "temperature"}
    assert "response_format" not in captured["payload"]
    assert "tools" not in captured["payload"]
    assert "stream" not in captured["payload"]
    assert "json_schema" not in captured["payload"]
    assert captured["payload"]["messages"][1]["content"] == "health_check: reply with only ok"


def test_health_check_default_transport_uses_openai_sdk_client_not_urllib(monkeypatch):
    captured = {}

    def fail_urlopen(*args, **kwargs):
        raise AssertionError("urllib transport should not be used by default")

    def fake_build_client(*, base_url, api_key, timeout):
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        captured["timeout"] = timeout
        return object()

    def fake_call_chat_completion(client, model, messages, temperature=0, response_format=None):
        captured["model"] = model
        captured["messages"] = messages
        captured["temperature"] = temperature
        captured["response_format"] = response_format
        return "ok"

    monkeypatch.setattr(urllib.request, "urlopen", fail_urlopen)
    monkeypatch.setattr(private_llm_client, "build_openai_compatible_client", fake_build_client)
    monkeypatch.setattr(private_llm_client, "call_chat_completion", fake_call_chat_completion)

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile",
            api_key="secret",
            timeout=7,
        )
    )

    result = client.health_check()

    assert result["available"] is True
    assert captured["base_url"] == "https://api.groq.com/openai/v1"
    assert captured["api_key"] == "secret"
    assert captured["timeout"] == 7
    assert captured["model"] == "llama-3.3-70b-versatile"
    assert set(captured["messages"][0]) == {"role", "content"}
    assert captured["temperature"] == 0
    assert captured["response_format"] is None


def test_safe_chat_default_transport_preserves_json_response_format(monkeypatch):
    captured = {}

    def fake_build_client(*, base_url, api_key, timeout):
        captured["base_url"] = base_url
        captured["api_key"] = api_key
        captured["timeout"] = timeout
        return object()

    def fake_call_chat_completion(client, model, messages, temperature=0, response_format=None):
        captured["model"] = model
        captured["messages"] = messages
        captured["temperature"] = temperature
        captured["response_format"] = response_format
        return '{"document_type":"report"}'

    monkeypatch.setattr(private_llm_client, "build_openai_compatible_client", fake_build_client)
    monkeypatch.setattr(private_llm_client, "call_chat_completion", fake_call_chat_completion)

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile",
            api_key="secret",
            timeout=7,
        )
    )

    result = client.assist_document_type(_document())

    assert result["available"] is True
    assert result["operations_generated"] is False
    assert captured["base_url"] == "https://api.groq.com/openai/v1"
    assert captured["api_key"] == "secret"
    assert captured["response_format"] == {"type": "json_object"}


def test_default_transport_llm_call_error_falls_back(monkeypatch):
    def fake_build_client(*, base_url, api_key, timeout):
        return object()

    def fake_call_chat_completion(client, model, messages, temperature=0, response_format=None):
        raise LLMCallError("provider said no")

    monkeypatch.setattr(private_llm_client, "build_openai_compatible_client", fake_build_client)
    monkeypatch.setattr(private_llm_client, "call_chat_completion", fake_call_chat_completion)

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile",
            api_key="secret",
        )
    )

    result = client.health_check()

    assert result["available"] is False
    assert result["task"] == "health_check"
    assert "provider said no" in result["reason"]
    assert "secret" not in result["reason"]


def test_health_check_accepts_plain_ok_response():
    def transport(endpoint, headers, payload, timeout):
        return {"choices": [{"message": {"content": "ok"}}]}

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="http://private-model:8000/v1",
            model="local-docx-model",
        ),
        transport=transport,
    )

    result = client.health_check()

    assert result["available"] is True
    assert result["result"]["status"] == "ok"


def test_health_check_failure_reports_fallback():
    def transport(endpoint, headers, payload, timeout):
        raise OSError("network down")

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="http://private-model:8000/v1",
            model="local-docx-model",
        ),
        transport=transport,
    )

    result = client.health_check()

    assert result["available"] is False
    assert result["task"] == "health_check"
    assert result["mode"] == "rule_only_fallback"
    assert "network down" in result["reason"]


def test_health_check_http_error_reports_status_and_body():
    def transport(endpoint, headers, payload, timeout):
        raise urllib.error.HTTPError(
            url="https://api.groq.com/openai/v1/chat/completions",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile",
            api_key="secret",
        ),
        transport=transport,
    )

    result = client.health_check()

    assert result["available"] is False
    assert result["task"] == "health_check"
    assert "HTTPError 403 Forbidden" in result["reason"]
    assert "https://api.groq.com/openai/v1/chat/completions" in result["reason"]
    assert "body=(empty)" in result["reason"]
    assert "secret" not in result["reason"]


def test_health_check_http_error_reports_response_body_snippet():
    class BodyHTTPError(urllib.error.HTTPError):
        def read(self, amt=None):
            return b'{"error":{"message":"invalid request for provider"}}'

    def transport(endpoint, headers, payload, timeout):
        raise BodyHTTPError(
            url="https://api.groq.com/openai/v1/chat/completions",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="https://api.groq.com/openai/v1",
            model="llama-3.3-70b-versatile",
            api_key="secret",
        ),
        transport=transport,
    )

    result = client.health_check()

    assert result["available"] is False
    assert "HTTPError 403 Forbidden" in result["reason"]
    assert "invalid request for provider" in result["reason"]
    assert "secret" not in result["reason"]


def test_health_check_retries_transport_failures():
    attempts = {"count": 0}

    def transport(endpoint, headers, payload, timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise OSError("temporary network error")
        return {"choices": [{"message": {"content": '{"status":"ok"}'}}]}

    client = PrivateLLMClient(
        PrivateLLMConfig(
            enabled=True,
            endpoint="http://private-model:8000/v1",
            model="local-docx-model",
            max_retries=1,
        ),
        transport=transport,
    )

    result = client.health_check()

    assert result["available"] is True
    assert attempts["count"] == 2
