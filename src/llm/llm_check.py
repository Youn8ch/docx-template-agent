"""LLM self-check entrypoint.

Run with:

    python -m src.llm.llm_check
"""

from __future__ import annotations

import json
import sys
from typing import Any

from src.llm.client import (
    LLMConfigError,
    build_llm_client,
    call_chat_completion,
    load_llm_config,
)


SYSTEM_PROMPT = "你只能输出合法 JSON，不要输出 Markdown，不要解释，不要使用 ``` 包裹。"
USER_PROMPT = "请输出一个 JSON，字段包括 passed、summary。"


def run_check() -> dict[str, Any]:
    llm_config = load_llm_config()
    if llm_config.get("enabled") is not True:
        raise LLMConfigError("llm.enabled must be true for the LLM self-check")

    client = build_llm_client(llm_config)
    content = call_chat_completion(
        client,
        model=str(llm_config.get("model") or ""),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        temperature=float(llm_config.get("temperature", 0)),
    )
    parsed = json.loads(content)
    return {
        "passed": True,
        "provider": llm_config.get("provider", "openai_compatible"),
        "base_url": llm_config.get("base_url"),
        "model": llm_config.get("model"),
        "response": parsed,
    }


def main() -> None:
    try:
        result = run_check()
    except Exception as exc:
        print(f"[docx-template-agent] LLM self-check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("[docx-template-agent] LLM self-check passed")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
