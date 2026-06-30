import sys
import types

import pytest

from src.llm.client import (
    LLMCallError,
    LLMConfigError,
    build_llm_client,
    call_chat_completion,
    load_llm_config,
)


def test_load_llm_config_reads_existing_llm_section(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "\n".join(
            [
                "llm:",
                "  enabled: true",
                "  provider: openai_compatible",
                "  base_url: http://model.local/v1",
                "  api_key_env: TEST_LLM_API_KEY",
                "  model: local-model",
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_llm_config(config)

    assert loaded["base_url"] == "http://model.local/v1"
    assert loaded["api_key_env"] == "TEST_LLM_API_KEY"
    assert loaded["model"] == "local-model"


def test_build_llm_client_requires_api_key_environment(monkeypatch):
    monkeypatch.delenv("MISSING_LLM_API_KEY", raising=False)

    with pytest.raises(LLMConfigError, match="MISSING_LLM_API_KEY"):
        build_llm_client(
            {
                "base_url": "http://model.local/v1",
                "api_key_env": "MISSING_LLM_API_KEY",
            }
        )


def test_build_llm_client_uses_configured_base_url_key_and_default_timeout(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, *, base_url, api_key, timeout):
            captured["base_url"] = base_url
            captured["api_key"] = api_key
            captured["timeout"] = timeout

    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("TEST_LLM_API_KEY", "secret")

    client = build_llm_client(
        {
            "base_url": "http://model.local/v1",
            "api_key_env": "TEST_LLM_API_KEY",
        }
    )

    assert isinstance(client, FakeOpenAI)
    assert captured == {
        "base_url": "http://model.local/v1",
        "api_key": "secret",
        "timeout": 60.0,
    }


def test_build_llm_client_uses_configured_timeout(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, *, base_url, api_key, timeout):
            captured["timeout"] = timeout

    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_openai)
    monkeypatch.setenv("TEST_LLM_API_KEY", "secret")

    build_llm_client(
        {
            "base_url": "http://model.local/v1",
            "api_key_env": "TEST_LLM_API_KEY",
            "timeout": 12,
        }
    )

    assert captured["timeout"] == 12.0


def test_call_chat_completion_returns_first_message_content():
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = types.SimpleNamespace(content='{"passed":true}')
            choice = types.SimpleNamespace(message=message)
            return types.SimpleNamespace(choices=[choice])

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=FakeCompletions())
    )

    content = call_chat_completion(
        client,
        model="local-model",
        messages=[{"role": "user", "content": "ping"}],
        temperature=0,
    )

    assert content == '{"passed":true}'
    assert captured["model"] == "local-model"
    assert captured["messages"] == [{"role": "user", "content": "ping"}]
    assert captured["temperature"] == 0


def test_call_chat_completion_passes_optional_response_format():
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = types.SimpleNamespace(content='{"passed":true}')
            choice = types.SimpleNamespace(message=message)
            return types.SimpleNamespace(choices=[choice])

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=FakeCompletions())
    )

    content = call_chat_completion(
        client,
        model="local-model",
        messages=[{"role": "user", "content": "ping"}],
        temperature=0,
        response_format={"type": "json_object"},
    )

    assert content == '{"passed":true}'
    assert captured["response_format"] == {"type": "json_object"}


def test_call_chat_completion_wraps_sdk_errors():
    class FakeCompletions:
        def create(self, **kwargs):
            raise RuntimeError("network down")

    client = types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=FakeCompletions())
    )

    with pytest.raises(LLMCallError, match="LLM chat completion failed"):
        call_chat_completion(
            client,
            model="local-model",
            messages=[{"role": "user", "content": "ping"}],
        )
