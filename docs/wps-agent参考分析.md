# wps-agent 参考项目分析

> 本文只分析 `ref/wps-agent-master` 中与 docx 离线处理相关的设计，不作为源码迁移说明。参考项目不得修改，不得全量复制；本文结论服务于 `docx-template-agent` 第一版 MVP。

## 1. wps-agent 的 docx 离线处理架构

`wps-agent` 的 docx 能力是“双模式”设计：一部分通过 WPS COM 在线控制文档，另一部分通过 `docx_engine` 直接读写 `.docx` 包内 OOXML。对本项目有参考价值的只有后者。

与 docx 离线处理相关的主链路如下：

```text
输入 docx
  -> xml_parser.unpack_docx / parse_docx
  -> serializer.build_document_model
  -> document_model.Document / Paragraph / Run / Table / Section
  -> intelligence.DocumentAnalyzer 或 formatter.Formatter
  -> serializer.serialize_document_model
  -> xml_parser.pack_docx
  -> 输出 docx
```

`offline/docx_builder.py` 是高层封装，负责把读取、分析、自动格式化、模板套用、编号、文本替换、保存串起来。`mcp_server.py` 暴露了 `offline_docx` 工具，并且在 `content`、`format` 工具中也存在部分基于 filepath 的离线分支。

需要注意：参考项目虽然有离线 docx 能力，但它的目标是“大而全的文档助手”，允许创建文档、插入内容、替换文本、删除 run/段落、重建正文结构等操作。这与本项目“只做安全排版、不改业务内容”的第一版边界不同。

## 2. docx_engine 的核心设计思想

`docx_engine` 的核心思想是把 `.docx` 当作 ZIP 包和 OOXML 树处理，而不是依赖 WPS 客户端：

- `xml_parser.py` 负责解包、打包和读取关键 XML 部件，包括 `word/document.xml`、`styles.xml`、`numbering.xml`、页眉页脚、脚注尾注、关系文件、媒体文件等。
- `document_model.py` 把 OOXML 映射成内存模型，主要对象是 `Document`、`Paragraph`、`Run`、`Table`、`Cell`、`Section`。
- `serializer.py` 在模型和 XML 之间转换，并保存原 XML 引用，尽量做增量写回，以保留未建模的 OOXML 属性。
- `style_resolver.py` 解析 `styles.xml`，根据 `basedOn` 继承链计算有效段落格式和字符格式。
- `intelligence.py` 基于规则识别文档类型、段落角色、标题结构和格式质量问题。
- `formatter.py` 基于文档类型或模板直接修改模型中的格式属性，再交由 serializer 写回。

对本项目最有价值的不是它的完整实现，而是分层思路：解析层、模型层、样式解析层、分析层、写回层相互独立。这个方向适合转化为本项目自己的轻量 `engine`。

## 3. offline/docx_builder.py 的处理流程

`OfflineDocxBuilder` 是一个面向调用方的外观类：

- `load(docx_path)`：调用 `parse_docx` 解包并解析 XML，再调用 `build_document_model` 生成 `Document`。
- `create()`：基于空白模板创建新文档模型。
- `save(output_path)`：调用 `serialize_document_model` 写入新 `.docx`。
- `analyze()`：用 `DocumentAnalyzer` 输出文档类型、统计信息、大纲、标题和格式质量。
- `auto_format(document_type)`：检测文档类型后调用 `Formatter.auto_format` 直接修改模型。
- `apply_template(template_name)`：套用内置格式模板。
- `add_numbering()`：给标题添加多级编号。
- `replace_text(old, new)`：跨 run 替换文本。
- `get_text()` / `get_statistics()`：只读获取文本和统计。

适合参考的是“高层编排类”的边界：调用方不直接接触 XML，流程集中在 load/analyze/plan/apply/save。  
不适合迁移的是它直接暴露 `replace_text`、`create`、`add_numbering` 等会修改正文内容或生成正文结构的能力。

## 4. 哪些能力适合本项目参考

适合参考的能力：

- `.docx` 作为 ZIP 包离线处理，不依赖 WPS、不依赖 COM。
- 读取 `document.xml`、`styles.xml`、`numbering.xml`、`rels` 的基本路径。
- 使用 `lxml` 处理 OOXML 命名空间和 XML 节点。
- 建立最小内存模型：文档、段落、run、表格、单元格、section。
- 为段落、run、表格单元格保留来源引用，便于安全定位原始 XML。
- 解析标题层级、样式 ID、段落对齐、缩进、段前段后、行距、字体、字号、加粗等格式属性。
- 解析 `styles.xml` 的样式继承链，用于判断有效格式。
- 输出结构化分析结果，而不是直接修改文档。
- 写回时尽量只改目标格式节点，保留其他 XML 部件。
- 统一错误类型，给调用方返回清晰错误。

这些能力应被改造成 `docx-template-agent` 的最小闭环：读取输入、分析结构、生成 operations、白名单校验、在副本上执行、安全写出。

## 5. 哪些模块不建议迁移

不建议迁移或不应进入第一版 MVP 的能力：

- `wps_bridge/` 及所有 WPS COM 能力。
- `requirements.txt` 中的 `pywin32` 依赖。
- `mcp_server.py` 中依赖 WPS 运行态的 `document`、`table`、`search`、`layout`、`review`、`compare`、`transfer`、`migrate`、`excel`、`presentation` 等工具设计。
- `content` 工具里的插入文本、删除 run、删除范围、替换范围、创建封面、批量写内容等能力。
- `offline_docx.replace_text`，因为它修改正文业务内容。
- `formatter.py` 中会删除空段落、修正文本文字/标点、给标题文本前插编号的逻辑。
- `serializer.py` 中支持新增、删除、重排段落的完整写回能力。
- 复杂语义模型、布局分析、AI 内容生成、自动增强、摘要、改写、翻译等能力。
- 大而全的 MCP 工具注册方式。

这些模块服务于通用办公助手，不服务于本项目第一版“安全、可审计、只做格式修正”的目标。

## 6. 哪些能力建议我们轻量重写

建议轻量重写，而不是复制：

- `DocxParser`：只解析 MVP 需要的 XML 部件和格式属性，不做全量 OOXML 覆盖。
- `DocumentModel`：只保留检查和 operations 执行所需字段，避免提供删除段落、替换文本等危险方法。
- `StyleResolver`：只实现样式名、样式 ID、`basedOn`、段落格式、字体格式的最小解析。
- `Analyzer`：只识别标题、正文、表格、表头等 MVP 角色，不引入复杂文档类型推断。
- `OperationValidator`：本项目必须新增，参考项目没有强白名单机制。
- `OperationExecutor`：只能接受已验证 operation，禁止业务逻辑直接改 docx。
- `DocxWriter`：以复制输入文件到输出路径为前提，只修改白名单格式属性。
- `ReportWriter`：输出 Markdown 检查报告和 JSON 修改明细，这是本项目 MVP 明确需要但参考项目不是核心。

建议第一版优先支持的 operation 类型：

- `set_paragraph_style`
- `set_heading_style`
- `set_paragraph_alignment`
- `set_paragraph_spacing`
- `set_paragraph_line_spacing`
- `set_paragraph_first_line_indent`
- `set_run_font`
- `set_run_size`
- `set_run_bold`
- `set_page_margins`
- `set_table_cell_paragraph_format`
- `set_table_cell_run_format`

其中表格相关 operation 只能改单元格内段落和 run 的格式，不能改单元格文本、行列结构和合并关系。

## 7. 可以少量借鉴的工具函数或实现思路

可以借鉴思路，但不要复制源码：

- OOXML 命名空间集中定义，提供统一的 qualified name 辅助方法。
- twips 与 point 的换算规则：段落缩进、间距、页边距常用 twips，字号常用 half-points。
- `.docx` 解包后定位 `word/document.xml`、`word/styles.xml`、`word/numbering.xml`、`word/_rels/document.xml.rels`。
- run 文本读取需要汇总多个 `w:t`。
- 段落格式读取主要来自 `w:pPr`，字符格式读取主要来自 `w:rPr`。
- 样式继承解析可以按 `basedOn` 链从父样式到子样式逐层覆盖。
- 表格单元格内也包含段落，分析时要区分正文段落和表格内段落。
- 写回时尽量定位原始 XML 节点，只改白名单允许的属性或子节点。
- 输出前检查 `output_path` 不等于输入路径。
- 对解析失败、缺失关键 XML、非法 operation、写出失败使用可分类错误。

## 8. 许可证和代码复制风险提醒

当前参考目录中未发现独立 `LICENSE` 或 `NOTICE` 文件，仅看到 `README.md`。在许可证不明确的情况下，应按高风险处理：

- 不复制参考项目源码、注释、文档段落和测试用例。
- 不做“改名式迁移”。
- 只参考架构边界、流程分层、OOXML 处理常识和公开标准概念。
- 本项目实现应使用自己的数据结构、函数命名、错误模型和测试样例。
- 如果未来确需复用任何具体代码，必须先确认许可证、来源和合规边界。

此外，参考项目依赖包含 `pywin32`，并以 WPS COM 为重要能力来源；这与本项目第一版硬性约束冲突，不能引入。

## 9. 对 docx-template-agent 的启发

对本项目最重要的启发是：离线 docx 排版工具应该把“分析”和“修改”彻底分开。

建议本项目第一版采用以下主流程：

```text
input docx
  -> read-only parse
  -> build minimal DocumentModel
  -> analyze roles and current formats
  -> check YAML template rules
  -> generate operation plan
  -> validate operations by whitelist
  -> copy input docx to output path
  -> apply validated formatting operations
  -> write output docx
  -> emit Markdown report and JSON changes
```

关键设计原则：

- `engine` 不依赖 CLI、MCP、Web、模型服务。
- 所有修改必须是 operation，不允许 analyzer、checker、接口层直接改 XML。
- `DocumentModel` 不提供修改正文文本和删除段落的方法。
- 解析出的正文文本只用于识别、预览和报告，不作为改写目标。
- 写回层默认拒绝未知属性和未知目标。
- 输出必须写入新路径，禁止覆盖输入文件。
- 对无法确认是否安全的操作，降级为只读报告。

参考项目中 `Formatter.auto_format` 是“直接改模型”的做法，本项目应改成“生成 operations”。这会让每次修改可审计、可校验，也方便生成 JSON 明细。

## 10. wps-agent 模块到本项目模块的映射表

| wps-agent 参考位置 | 主要职责 | 本项目建议模块 | 迁移建议 |
|---|---|---|---|
| `docx_engine/xml_parser.py` | 解包、打包、解析核心 XML | `engine/docx_parser.py`、`engine/docx_package.py` | 轻量重写，只保留 MVP 必需部件 |
| `docx_engine/document_model.py` | 文档、段落、run、表格、section 内存模型 | `engine/models.py` | 轻量重写，移除危险修改方法 |
| `docx_engine/serializer.py` | XML 到模型、模型写回 XML | `engine/model_builder.py`、`engine/docx_writer.py`、`engine/operation_executor.py` | 拆分重写，写回只能由 operation 驱动 |
| `docx_engine/style_resolver.py` | 样式继承和有效格式解析 | `engine/style_resolver.py` | 可参考思路，最小实现 |
| `docx_engine/intelligence.py` | 文档类型、角色、质量分析 | `engine/analyzer.py` | 只保留标题/正文/表格等规则分析 |
| `docx_engine/formatter.py` | 自动格式化、模板套用、编号、文本修正 | `engine/rule_checker.py`、`engine/operation_planner.py` | 不迁移直接修改逻辑，改为生成 operations |
| `offline/docx_builder.py` | 离线处理外观类 | `engine/pipeline.py` | 借鉴编排思想，流程改为 analyze/plan/validate/apply |
| `mcp_server.py offline_docx` | MCP 离线 docx 工具入口 | 暂不进入 MVP；未来可做 `adapters/mcp` | 第一版不需要迁移 |
| `mcp_server.py content` 离线读分支 | 文本、段落、结构读取 | `engine/reader.py`、`engine/analyzer.py` | 可参考只读能力，禁止写内容能力 |
| `mcp_server.py format` 离线写分支 | 设置字体和段落格式 | `engine/operation_executor.py` | 只参考目标属性集合，必须增加白名单校验 |
| `wps_bridge/` | WPS COM 自动化 | 无 | 禁止迁移 |
| Excel/PPT/review/compare/migrate/transfer | 跨应用和复杂办公能力 | 无 | 禁止分析和迁移 |

## MVP 结论

`wps-agent` 证明了 docx 可以通过纯离线 OOXML 路线完成结构读取和格式写回，但它的实现范围远大于本项目需要。`docx-template-agent` 第一版应只吸收三点：

1. 离线解包、解析、写回 `.docx` 的分层思想。
2. 段落、run、表格、样式、section 的最小模型思想。
3. 样式解析和格式属性写回的实现思路。

第一版不应迁移它的 COM 层、内容改写能力、删除/插入正文能力、自动编号改文本能力、复杂 AI/MCP 能力。所有可执行修改必须先转成结构化 operations，并经过白名单校验后才能作用到复制后的输出文档。
