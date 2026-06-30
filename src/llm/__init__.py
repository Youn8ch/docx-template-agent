"""Private LLM assistance boundary.

The LLM package is intentionally outside ``src.engine``. It may summarize or
classify read-only analysis data, but it must not create or execute operations.
"""

from src.llm.client import build_llm_client, call_chat_completion, load_llm_config

__all__ = ["build_llm_client", "call_chat_completion", "load_llm_config"]
