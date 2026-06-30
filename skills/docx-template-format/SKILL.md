# docx-template-format

本 skill 用于 `docx-template-agent` 的 docx 模板化排版流程。它面向离线 `.docx` 文档，在不改变业务内容的前提下，依据 YAML 模板执行格式检查、模板套用和复核报告生成。

优先使用项目暴露的 MCP 工具完成工作，不直接操作 `.docx` 文件，不绕过规则引擎、`FormatOperation` 白名单或输出安全检查。

## 使用边界

- 只用于 docx 模板化排版。
- 不允许修改正文业务内容。
- 不允许删除段落。
- 不允许修改表格数据，包括表格单元格文本、行列数据和业务值。
- 不允许覆盖原文件，输出 docx 必须写入新的文件路径。
- 真正排版依据只能是 YAML 模板、规则引擎和 `FormatOperation` 白名单。
- LLM 只做辅助分析，不得作为最终排版依据。
- LLM 不允许生成或采纳 `FormatOperation`。
- LLM 不允许修改正文。
- LLM 不影响 `formatted.docx`。
- `operations.json` 是规则引擎结果，不包含 LLM 结果。
- `llm_analysis.json` 是辅助分析结果，仅供人工参考。

## MCP 工具

固定优先使用以下 MCP 工具：

1. `list_templates`
2. `analyze_docx`
3. `check_docx_style`
4. `apply_docx_template`
5. `generate_review_report`

LLM 接入边界：

- 只有 `apply_docx_template` 和 `generate_review_report` 支持 `use_llm`。
- `list_templates`、`analyze_docx`、`check_docx_style` 不接 LLM。
- `use_llm=false` 默认不调用 LLM。
- `use_llm=true` 时可输出 `llm_analysis.json`。
- 遇到 LLM 失败时，继续使用规则引擎结果。

## 推荐调用示例

模板排版，不启用 LLM：

```json
{
  "input_path": "samples/input/demo.docx",
  "template": "report",
  "use_llm": false
}
```

模板排版，启用 LLM 辅助分析：

```json
{
  "input_path": "samples/input/demo.docx",
  "template": "report",
  "use_llm": true
}
```

只生成复核报告，并启用 LLM 辅助分析：

```json
{
  "input_path": "samples/input/demo.docx",
  "template": "report",
  "use_llm": true
}
```

上述第三个请求应调用 `generate_review_report`，不会写出新的 formatted docx。

## 固定工作流

如果用户没有明确指定模板：

1. 调用 `list_templates` 列出可用模板。
2. 调用 `analyze_docx` 读取文档结构。
3. 根据文档结构和用户意图建议模板，但不得声称模板由 LLM 决定。
4. 继续执行前说明所选模板及原因。

执行模板排版时：

1. `check_docx_style`
2. `apply_docx_template`
3. `generate_review_report`，如只需复核报告可单独调用

不得跳过检查步骤。任何可能影响业务内容、段落数量、表格数据或原始文件安全的操作都必须拒绝执行。

## LLM 辅助边界

LLM 只能帮助阅读和解释：

- 文档类型判断。
- 标题层级建议。
- 检查报告摘要。
- 模板推荐提示。

LLM 不允许：

- 生成 `FormatOperation`。
- 输出可执行格式化计划。
- 修改、替换、摘要、翻译或重写正文。
- 修改表格单元格文本。
- 覆盖用户或 CLI 指定模板。
- 影响 `build_operations()` 或 `apply_operations()` 的结果。

## 最终回复要求

最终回复应包含：

- 使用模板
- 原始文件路径
- 输出 docx 路径，如本次生成
- 检查报告路径
- json 明细路径
- LLM 分析路径，如本次启用并生成
- 问题数量
- 自动修正数量
- 人工复核建议

如果流程未能完整执行，最终回复仍应说明已完成步骤、失败步骤、失败原因，以及是否产生了任何输出文件。LLM 失败不应作为排版失败处理，应说明已 fallback 到规则引擎结果。
