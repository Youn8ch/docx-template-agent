# DOCX 格式检查报告

## 基本信息

- 原始文件: `D:\code2026\docx-template-agent\outputs\web\11a2058f0feb4725808c80ef86229fdd\input_source_20260627_163302.docx`
- 使用模板: `report`
- 检查时间: `2026-06-27T16:33:02`
- 段落数: `3`
- 表格数: `1`
- 问题总数: `32`
- 操作总数: `5`

## 问题分类统计

- `alignment`: 5
- `bold`: 5
- `first_line_indent_chars`: 3
- `font_name`: 5
- `font_size`: 5
- `line_spacing`: 3
- `space_after`: 3
- `space_before`: 3

## 问题明细

| ID | 类型 | 目标 | 角色 | 当前值 | 期望值 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| issue-0001 | font_name | paragraph#1 | title | - | SimHei | paragraph 1 font_name mismatch: current=None, expected='SimHei' |
| issue-0002 | font_size | paragraph#1 | title | - | 22 | paragraph 1 font_size mismatch: current=None, expected=22 |
| issue-0003 | bold | paragraph#1 | title | - | True | paragraph 1 bold mismatch: current=None, expected=True |
| issue-0004 | alignment | paragraph#1 | title | - | center | paragraph 1 alignment mismatch: current=None, expected='center' |
| issue-0005 | line_spacing | paragraph#1 | title | - | 1.5 | paragraph 1 line_spacing mismatch: current=None, expected=1.5 |
| issue-0006 | space_before | paragraph#1 | title | - | 0 | paragraph 1 space_before mismatch: current=None, expected=0 |
| issue-0007 | space_after | paragraph#1 | title | - | 12 | paragraph 1 space_after mismatch: current=None, expected=12 |
| issue-0008 | first_line_indent_chars | paragraph#1 | title | - | 0 | paragraph 1 first_line_indent_chars mismatch: current=None, expected=0 |
| issue-0009 | font_name | paragraph#2 | heading_3 | - | SimHei | paragraph 2 font_name mismatch: current=None, expected='SimHei' |
| issue-0010 | font_size | paragraph#2 | heading_3 | - | 14 | paragraph 2 font_size mismatch: current=None, expected=14 |
| issue-0011 | bold | paragraph#2 | heading_3 | - | True | paragraph 2 bold mismatch: current=None, expected=True |
| issue-0012 | alignment | paragraph#2 | heading_3 | - | left | paragraph 2 alignment mismatch: current=None, expected='left' |
| issue-0013 | line_spacing | paragraph#2 | heading_3 | - | 1.5 | paragraph 2 line_spacing mismatch: current=None, expected=1.5 |
| issue-0014 | space_before | paragraph#2 | heading_3 | - | 8 | paragraph 2 space_before mismatch: current=None, expected=8 |
| issue-0015 | space_after | paragraph#2 | heading_3 | - | 4 | paragraph 2 space_after mismatch: current=None, expected=4 |
| issue-0016 | first_line_indent_chars | paragraph#2 | heading_3 | - | 0 | paragraph 2 first_line_indent_chars mismatch: current=None, expected=0 |
| issue-0017 | font_name | paragraph#3 | body | - | SimSun | paragraph 3 font_name mismatch: current=None, expected='SimSun' |
| issue-0018 | font_size | paragraph#3 | body | - | 12 | paragraph 3 font_size mismatch: current=None, expected=12 |
| issue-0019 | bold | paragraph#3 | body | - | False | paragraph 3 bold mismatch: current=None, expected=False |
| issue-0020 | alignment | paragraph#3 | body | - | justify | paragraph 3 alignment mismatch: current=None, expected='justify' |
| issue-0021 | line_spacing | paragraph#3 | body | - | 1.5 | paragraph 3 line_spacing mismatch: current=None, expected=1.5 |
| issue-0022 | space_before | paragraph#3 | body | - | 0 | paragraph 3 space_before mismatch: current=None, expected=0 |
| issue-0023 | space_after | paragraph#3 | body | - | 0 | paragraph 3 space_after mismatch: current=None, expected=0 |
| issue-0024 | first_line_indent_chars | paragraph#3 | body | - | 2 | paragraph 3 first_line_indent_chars mismatch: current=None, expected=2 |
| issue-0025 | font_name | table#1 | table | - | SimSun | table 1 font_name mismatch: current=None, expected='SimSun' |
| issue-0026 | font_size | table#1 | table | - | 10.5 | table 1 font_size mismatch: current=None, expected=10.5 |
| issue-0027 | bold | table#1 | table | - | False | table 1 bold mismatch: current=None, expected=False |
| issue-0028 | alignment | table#1 | table | - | center | table 1 alignment mismatch: current=None, expected='center' |
| issue-0029 | font_name | table_header#1 | table_header | - | SimHei | table_header 1 font_name mismatch: current=None, expected='SimHei' |
| issue-0030 | font_size | table_header#1 | table_header | - | 10.5 | table_header 1 font_size mismatch: current=None, expected=10.5 |
| issue-0031 | bold | table_header#1 | table_header | - | True | table_header 1 bold mismatch: current=None, expected=True |
| issue-0032 | alignment | table_header#1 | table_header | - | center | table_header 1 alignment mismatch: current=None, expected='center' |

## 人工复核建议

- 请重点复核自动生成的 operations 是否只涉及格式属性，不涉及正文文本修改。
- 请抽查标题、正文、表格和表头的实际显示效果，特别是中文字体是否符合内网模板要求。
- 对问题较多的段落或表格，建议先人工确认模板规则是否适用于该文档。

## LLM 辅助分析

- LLM 分析仅供参考，不参与格式化操作生成。
- 推荐模板仅供参考，不会覆盖本次实际使用模板。
- mode: `private_llm`
- status: `ok`
- operations_source: `rule_engine_only`
- operations_generated: `False`
- template_recommendation: recommended_template: not-the-user-template
