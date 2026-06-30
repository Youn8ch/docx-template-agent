# DOCX 格式检查报告

## 基本信息

- 原始文件: `D:\code2026\docx-template-agent\outputs\web\ee34b6e94b4d425e9d8cfb95fe31613a\demo_source_20260627_150036.docx`
- 使用模板: `report`
- 检查时间: `2026-06-27T15:00:36`
- 段落数: `8`
- 表格数: `1`
- 问题总数: `62`
- 操作总数: `10`

## 问题分类统计

- `alignment`: 10
- `bold`: 5
- `first_line_indent_chars`: 6
- `font_name`: 10
- `font_size`: 7
- `line_spacing`: 8
- `space_after`: 8
- `space_before`: 8

## 问题明细

| ID | 类型 | 目标 | 角色 | 当前值 | 期望值 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| issue-0001 | font_name | paragraph#1 | title | 宋体 | SimHei | paragraph 1 font_name mismatch: current='宋体', expected='SimHei' |
| issue-0002 | font_size | paragraph#1 | title | 18.0 | 22 | paragraph 1 font_size mismatch: current=18.0, expected=22 |
| issue-0003 | alignment | paragraph#1 | title | - | center | paragraph 1 alignment mismatch: current=None, expected='center' |
| issue-0004 | line_spacing | paragraph#1 | title | - | 1.5 | paragraph 1 line_spacing mismatch: current=None, expected=1.5 |
| issue-0005 | space_before | paragraph#1 | title | - | 0 | paragraph 1 space_before mismatch: current=None, expected=0 |
| issue-0006 | space_after | paragraph#1 | title | - | 12 | paragraph 1 space_after mismatch: current=None, expected=12 |
| issue-0007 | first_line_indent_chars | paragraph#1 | title | - | 0 | paragraph 1 first_line_indent_chars mismatch: current=None, expected=0 |
| issue-0008 | font_name | paragraph#2 | heading_1 | 宋体 | SimHei | paragraph 2 font_name mismatch: current='宋体', expected='SimHei' |
| issue-0009 | alignment | paragraph#2 | heading_1 | - | left | paragraph 2 alignment mismatch: current=None, expected='left' |
| issue-0010 | line_spacing | paragraph#2 | heading_1 | - | 1.5 | paragraph 2 line_spacing mismatch: current=None, expected=1.5 |
| issue-0011 | space_before | paragraph#2 | heading_1 | - | 12 | paragraph 2 space_before mismatch: current=None, expected=12 |
| issue-0012 | space_after | paragraph#2 | heading_1 | - | 6 | paragraph 2 space_after mismatch: current=None, expected=6 |
| issue-0013 | first_line_indent_chars | paragraph#2 | heading_1 | - | 0 | paragraph 2 first_line_indent_chars mismatch: current=None, expected=0 |
| issue-0014 | font_name | paragraph#3 | heading_2 | 宋体 | SimHei | paragraph 3 font_name mismatch: current='宋体', expected='SimHei' |
| issue-0015 | font_size | paragraph#3 | heading_2 | 14.0 | 15 | paragraph 3 font_size mismatch: current=14.0, expected=15 |
| issue-0016 | alignment | paragraph#3 | heading_2 | - | left | paragraph 3 alignment mismatch: current=None, expected='left' |
| issue-0017 | line_spacing | paragraph#3 | heading_2 | - | 1.5 | paragraph 3 line_spacing mismatch: current=None, expected=1.5 |
| issue-0018 | space_before | paragraph#3 | heading_2 | - | 10 | paragraph 3 space_before mismatch: current=None, expected=10 |
| issue-0019 | space_after | paragraph#3 | heading_2 | - | 6 | paragraph 3 space_after mismatch: current=None, expected=6 |
| issue-0020 | first_line_indent_chars | paragraph#3 | heading_2 | - | 0 | paragraph 3 first_line_indent_chars mismatch: current=None, expected=0 |
| issue-0021 | font_name | paragraph#4 | heading_3 | 宋体 | SimHei | paragraph 4 font_name mismatch: current='宋体', expected='SimHei' |
| issue-0022 | font_size | paragraph#4 | heading_3 | 12.0 | 14 | paragraph 4 font_size mismatch: current=12.0, expected=14 |
| issue-0023 | alignment | paragraph#4 | heading_3 | - | left | paragraph 4 alignment mismatch: current=None, expected='left' |
| issue-0024 | line_spacing | paragraph#4 | heading_3 | - | 1.5 | paragraph 4 line_spacing mismatch: current=None, expected=1.5 |
| issue-0025 | space_before | paragraph#4 | heading_3 | - | 8 | paragraph 4 space_before mismatch: current=None, expected=8 |
| issue-0026 | space_after | paragraph#4 | heading_3 | - | 4 | paragraph 4 space_after mismatch: current=None, expected=4 |
| issue-0027 | first_line_indent_chars | paragraph#4 | heading_3 | - | 0 | paragraph 4 first_line_indent_chars mismatch: current=None, expected=0 |
| issue-0028 | font_name | paragraph#5 | body | 微软雅黑 | SimSun | paragraph 5 font_name mismatch: current='微软雅黑', expected='SimSun' |
| issue-0029 | font_size | paragraph#5 | body | 10.5 | 12 | paragraph 5 font_size mismatch: current=10.5, expected=12 |
| issue-0030 | bold | paragraph#5 | body | - | False | paragraph 5 bold mismatch: current=None, expected=False |
| issue-0031 | alignment | paragraph#5 | body | - | justify | paragraph 5 alignment mismatch: current=None, expected='justify' |
| issue-0032 | line_spacing | paragraph#5 | body | - | 1.5 | paragraph 5 line_spacing mismatch: current=None, expected=1.5 |
| issue-0033 | space_before | paragraph#5 | body | - | 0 | paragraph 5 space_before mismatch: current=None, expected=0 |
| issue-0034 | space_after | paragraph#5 | body | - | 0 | paragraph 5 space_after mismatch: current=None, expected=0 |
| issue-0035 | font_name | paragraph#6 | body | 微软雅黑 | SimSun | paragraph 6 font_name mismatch: current='微软雅黑', expected='SimSun' |
| issue-0036 | font_size | paragraph#6 | body | 10.5 | 12 | paragraph 6 font_size mismatch: current=10.5, expected=12 |
| issue-0037 | bold | paragraph#6 | body | - | False | paragraph 6 bold mismatch: current=None, expected=False |
| issue-0038 | alignment | paragraph#6 | body | - | justify | paragraph 6 alignment mismatch: current=None, expected='justify' |
| issue-0039 | line_spacing | paragraph#6 | body | - | 1.5 | paragraph 6 line_spacing mismatch: current=None, expected=1.5 |
| issue-0040 | space_before | paragraph#6 | body | - | 0 | paragraph 6 space_before mismatch: current=None, expected=0 |
| issue-0041 | space_after | paragraph#6 | body | - | 0 | paragraph 6 space_after mismatch: current=None, expected=0 |
| issue-0042 | first_line_indent_chars | paragraph#6 | body | - | 2 | paragraph 6 first_line_indent_chars mismatch: current=None, expected=2 |
| issue-0043 | font_name | paragraph#7 | body | 微软雅黑 | SimSun | paragraph 7 font_name mismatch: current='微软雅黑', expected='SimSun' |
| issue-0044 | font_size | paragraph#7 | body | 10.5 | 12 | paragraph 7 font_size mismatch: current=10.5, expected=12 |
| issue-0045 | bold | paragraph#7 | body | - | False | paragraph 7 bold mismatch: current=None, expected=False |
| issue-0046 | alignment | paragraph#7 | body | - | justify | paragraph 7 alignment mismatch: current=None, expected='justify' |
| issue-0047 | line_spacing | paragraph#7 | body | - | 1.5 | paragraph 7 line_spacing mismatch: current=None, expected=1.5 |
| issue-0048 | space_before | paragraph#7 | body | - | 0 | paragraph 7 space_before mismatch: current=None, expected=0 |
| issue-0049 | space_after | paragraph#7 | body | - | 0 | paragraph 7 space_after mismatch: current=None, expected=0 |
| issue-0050 | font_name | paragraph#8 | body | 微软雅黑 | SimSun | paragraph 8 font_name mismatch: current='微软雅黑', expected='SimSun' |
| issue-0051 | font_size | paragraph#8 | body | 10.5 | 12 | paragraph 8 font_size mismatch: current=10.5, expected=12 |
| issue-0052 | bold | paragraph#8 | body | - | False | paragraph 8 bold mismatch: current=None, expected=False |
| issue-0053 | alignment | paragraph#8 | body | - | justify | paragraph 8 alignment mismatch: current=None, expected='justify' |
| issue-0054 | line_spacing | paragraph#8 | body | - | 1.5 | paragraph 8 line_spacing mismatch: current=None, expected=1.5 |
| issue-0055 | space_before | paragraph#8 | body | - | 0 | paragraph 8 space_before mismatch: current=None, expected=0 |
| issue-0056 | space_after | paragraph#8 | body | - | 0 | paragraph 8 space_after mismatch: current=None, expected=0 |
| issue-0057 | first_line_indent_chars | paragraph#8 | body | - | 2 | paragraph 8 first_line_indent_chars mismatch: current=None, expected=2 |
| issue-0058 | font_name | table#1 | table | 宋体 | SimSun | table 1 font_name mismatch: current='宋体', expected='SimSun' |
| issue-0059 | bold | table#1 | table | [True, False] | False | table 1 bold mismatch: current=[True, False], expected=False |
| issue-0060 | alignment | table#1 | table | - | center | table 1 alignment mismatch: current=None, expected='center' |
| issue-0061 | font_name | table_header#1 | table_header | 宋体 | SimHei | table_header 1 font_name mismatch: current='宋体', expected='SimHei' |
| issue-0062 | alignment | table_header#1 | table_header | - | center | table_header 1 alignment mismatch: current=None, expected='center' |

## 人工复核建议

- 请重点复核自动生成的 operations 是否只涉及格式属性，不涉及正文文本修改。
- 请抽查标题、正文、表格和表头的实际显示效果，特别是中文字体是否符合内网模板要求。
- 对问题较多的段落或表格，建议先人工确认模板规则是否适用于该文档。
