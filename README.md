# docx-template-agent

`docx-template-agent` 是一个轻量级内网 docx 离线模板化排版工具。

它按照 YAML 模板检查 `.docx` 文档格式，生成安全的 `FormatOperation` 操作计划，经白名单校验后只修改格式属性，并输出新的 `.docx` 文件。项目不覆盖原始文档，不修改正文业务内容，不删除段落，不修改表格单元格文本。

真正的排版依据始终是：

```text
YAML 模板规则 -> 规则引擎检查 -> FormatOperation 白名单 -> apply_operations()
```

LLM 只作为旁路辅助分析，不参与最终排版决策。

## 当前能力

- CLI：本地命令行处理 docx。
- Web：上传 docx、选择模板、执行检查或排版。
- MCP：提供 `list_templates`、`analyze_docx`、`check_docx_style`、`apply_docx_template`、`generate_review_report` 工具。
- LLM 辅助分析：支持私有 OpenAI-compatible `/v1/chat/completions` 服务，仅输出 advisory 结果。
- `formatted.docx`：格式化后的新文档。
- `*_check_report.md`：人工复核用 Markdown 报告。
- `*_operations.json`：规则引擎生成的 issues、operations、validation、results。
- `llm_analysis.json`：LLM 辅助分析结果。

## 核心安全边界

- 只处理 `.docx` 文件。
- 不使用 WPS COM。
- 不引入 `pywin32`。
- 不依赖 WPS 客户端。
- 不覆盖原始 docx。
- 不修改正文业务内容。
- 不删除段落。
- 不修改表格单元格文本。
- 所有格式修改必须先生成结构化 `FormatOperation`。
- 所有 `FormatOperation` 必须通过白名单校验。
- LLM 只做 advisory 辅助分析。
- LLM 不生成或采纳 `FormatOperation`。
- LLM 不影响 `build_operations()`。
- LLM 不影响 `apply_operations()`。
- LLM 不影响 `formatted.docx`。
- `operations.json` 只包含规则引擎结果。
- LLM 推荐模板仅供参考，不覆盖 CLI `--template` 或调用方指定模板。
- LLM 异常会 fallback 到规则引擎结果，不阻断主流程。

## LLM 隐私边界

发送给 LLM 的 snapshot 默认不包含全文：

- 顶层包含 `full_text_sent: false`。
- 顶层包含 `paragraph_text_is_preview_only: true`。
- 只发送段落 `text_preview` 和样式摘要。
- `text_preview` 会脱敏 IPv4、邮箱、手机号、URL。
- 段落 preview 默认最多 80 字符。
- 段落数量默认最多 80。
- 表格只发送 `table_count`，不发送单元格内容。

## 安装依赖

```bash
pip install -r requirements.txt
```

## CLI 使用

测试私有 LLM 连接：

```bash
python app.py llm-test
```

执行 docx 模板化排版：

```bash
python app.py --input samples/input/demo.docx --template templates/report.yaml --output samples/output
```

`--output` 可以是输出目录，也可以是 `.docx` 输出文件路径。输出目录模式下会生成类似：

```text
samples/output/demo_formatted.docx
samples/output/demo_formatted_check_report.md
samples/output/demo_formatted_operations.json
samples/output/llm_analysis.json
```

说明：当前 CLI 没有 `--use-llm` 参数。是否启用 LLM 由 `config.yaml` 的 `llm.enabled` 和环境变量决定；未启用或调用失败时自动使用 `rule_only_fallback`。

## LLM 配置

`config.yaml` 支持：

```yaml
llm:
  enabled: false
  endpoint: ""
  model: ""
  api_key_env: PRIVATE_LLM_API_KEY
  timeout: 8
  max_retries: 1
```

也可以使用环境变量覆盖：

- `DOCX_TEMPLATE_AGENT_LLM_ENABLED`
- `DOCX_TEMPLATE_AGENT_LLM_ENDPOINT`
- `DOCX_TEMPLATE_AGENT_LLM_BASE_URL`
- `DOCX_TEMPLATE_AGENT_LLM_MODEL`
- `DOCX_TEMPLATE_AGENT_LLM_API_KEY`
- `DOCX_TEMPLATE_AGENT_LLM_TIMEOUT`
- `DOCX_TEMPLATE_AGENT_LLM_MAX_RETRIES`
- `PRIVATE_LLM_API_KEY`，或 `api_key_env` 指定的变量名

`endpoint` 与 `base_url` 兼容，目标服务需提供 OpenAI-compatible `/v1/chat/completions` 接口。

## OpenAI-compatible LLM Client

统一的 OpenAI-compatible SDK client 位于 `src/llm/client.py`。业务代码不要直接初始化 `OpenAI(...)`，应使用 `build_llm_client()` 和 `call_chat_completion()`。

`config.yaml` 支持：
```yaml
llm:
  enabled: true
  provider: "openai_compatible"
  base_url: "https://api.groq.com/openai/v1"
  api_key_env: "PRIVATE_LLM_API_KEY"
  model: "llama-3.1-8b-instant"
  timeout: 60
  temperature: 0
```

`api_key_env` 必须是环境变量名，不能填写真实 API Key。切换 Groq、Ollama、vLLM 或内网 OpenAI-compatible 服务时，通常只需要修改 `base_url`、`api_key_env` 和 `model`。外网临时测试 Groq 时，可以把 `api_key_env` 改成 `GROQ_API_KEY`，但项目默认值保持通用。

TODO: 后续可评估是否把 `PrivateLLMClient` 的底层 transport 迁移到统一 client；本阶段不迁移 CLI/Web/MCP 主链路。

LLM JSON 自检：
```bash
python -m src.llm.llm_check
```

## Web 使用

启动 FastAPI Web 应用：

```bash
uvicorn src.web.app:app --reload
```

页面提供：

- DOCX 文件上传。
- 模板选择。
- “启用 LLM 辅助分析” checkbox。
- `/check`：执行格式检查。
- `/format`：执行模板排版并输出新 docx。

`use_llm=false` 默认不调用 LLM。`use_llm=true` 时会生成 `llm_analysis.json`，LLM 异常不会影响 `formatted.docx`。

## MCP 使用

MCP 工具：

- `list_templates`
- `analyze_docx`
- `check_docx_style`
- `apply_docx_template`
- `generate_review_report`

LLM 接入边界：

- 只有 `apply_docx_template` 和 `generate_review_report` 支持 `use_llm`。
- `list_templates`、`analyze_docx`、`check_docx_style` 不接 LLM，即使传入 `use_llm` 也不会调用 LLM。
- `use_llm=false` 默认不调用 LLM。
- `use_llm=true` 时输出 `llm_analysis.json`。
- `apply_docx_template` 中 LLM 异常不影响 `formatted.docx`。

示例请求：

```json
{
  "input_path": "samples/input/demo.docx",
  "template": "report",
  "use_llm": true
}
```

## 输出文件

- `formatted.docx`：复制输入文档后应用白名单格式操作得到的新文档。
- `*_check_report.md`：检查报告，包含问题摘要、操作摘要、执行结果，以及可选的 LLM 辅助分析章节。
- `*_operations.json`：规则引擎结果，不包含 LLM 返回内容。
- `llm_analysis.json`：LLM 辅助分析结果，仅供人工参考。

## 测试与验收

当前验收结果：

```text
63 passed, 1 warning
```

测试覆盖摘要：

- CLI 主流程与输出文件。
- Web `/check`、`/format`、`use_llm` 开关。
- MCP 工具与 `use_llm` 边界。
- LLM fallback 与 health check。
- LLM snapshot 脱敏、截断和表格内容隔离。
- `operations.json` 与 LLM 结果隔离。
- LLM 推荐模板不覆盖实际模板。
- LLM 返回 operations 不进入规则引擎结果。
- LLM 异常不阻断 `formatted.docx` 输出。
