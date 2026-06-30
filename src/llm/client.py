"""OpenAI-compatible LLM client boundary.

Business code should build SDK clients through this module instead of
instantiating ``OpenAI(...)`` directly.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
DEFAULT_TIMEOUT_SECONDS = 60


class LLMConfigError(ValueError):
    """Raised when LLM configuration is missing or unsafe."""


class LLMCallError(RuntimeError):
    """Raised when an LLM request fails."""


def load_llm_config(config_path: str | Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load the ``llm`` section from the project YAML config."""

    path = Path(config_path)
    if not path.exists():
        raise LLMConfigError(f"LLM config file not found: {path}")

    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise LLMConfigError(f"config yaml root must be a mapping: {path}")

    llm_config = loaded.get("llm")
    if not isinstance(llm_config, dict):
        raise LLMConfigError(f"missing llm config section in: {path}")
    return llm_config


def _require_text_config(llm_config: dict[str, Any], key: str) -> str:
    value = llm_config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LLMConfigError(f"llm.{key} must be configured")
    return value.strip()


def build_openai_compatible_client(
    *,
    base_url: str,
    api_key: str,
    timeout: float,
) -> "OpenAI":
    """Build an OpenAI-compatible SDK client from resolved settings."""

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LLMConfigError(
            "openai package is required for OpenAI-compatible LLM support"
        ) from exc

    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)


def build_llm_client(llm_config: dict[str, Any]) -> "OpenAI":
    """Build an OpenAI-compatible client from config and environment.

    ``llm_config["api_key_env"]`` must contain the environment variable name,
    not the API key itself.
    """

    base_url = _require_text_config(llm_config, "base_url")
    api_key_env = _require_text_config(llm_config, "api_key_env")
    api_key = os.getenv(api_key_env)
    if not api_key:
        raise LLMConfigError(
            f"environment variable {api_key_env!r} is required for llm.api_key_env"
        )

    try:
        timeout = float(llm_config.get("timeout", DEFAULT_TIMEOUT_SECONDS))
    except (TypeError, ValueError) as exc:
        raise LLMConfigError("llm.timeout must be a number") from exc

    return build_openai_compatible_client(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
    )


def call_chat_completion(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0,
    response_format: dict[str, Any] | None = None,
) -> str:
    """Call chat completions and return the first message content."""

    if not model or not model.strip():
        raise LLMConfigError("model must be configured")

    try:
        request: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            request["response_format"] = response_format
        response = client.chat.completions.create(
            **request,
        )
        content = response.choices[0].message.content
    except Exception as exc:
        raise LLMCallError(f"LLM chat completion failed: {exc}") from exc

    if not isinstance(content, str) or not content.strip():
        raise LLMCallError("LLM chat completion returned empty content")
    return content
