"""Private LLM assistance boundary.

The LLM package is intentionally outside ``src.engine``. It may summarize or
classify read-only analysis data, but it must not create or execute operations.
"""

