"""FastAPI upload/download UI for the offline docx formatter."""

from __future__ import annotations

from html import escape

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from src.web import service


app = FastAPI(title="docx-template-agent Web")


def _template_options(selected: str | None = None) -> str:
    options = []
    for template in service.list_templates():
        template_id = template["template_id"]
        label = template.get("template_name") or template_id
        description = template.get("description") or ""
        selected_attr = " selected" if template_id == selected else ""
        text = f"{label} ({template_id})"
        if description:
            text = f"{text} - {description}"
        options.append(
            f'<option value="{escape(template_id)}"{selected_attr}>{escape(text)}</option>'
        )
    return "\n".join(options)


def _page(content: str = "", selected_template: str | None = None) -> HTMLResponse:
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>docx-template-agent</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; color: #202124; background: #f7f7f4; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 32px 20px; }}
    h1 {{ font-size: 28px; margin: 0 0 8px; }}
    form {{ background: #fff; border: 1px solid #ddd8ce; border-radius: 8px; padding: 20px; margin-top: 24px; }}
    label {{ display: block; font-weight: 650; margin: 14px 0 6px; }}
    input, select {{ box-sizing: border-box; width: 100%; padding: 10px; border: 1px solid #c8c3b8; border-radius: 6px; background: #fff; }}
    .checkline {{ display: flex; align-items: center; gap: 8px; margin-top: 14px; font-weight: 500; }}
    .checkline input {{ width: auto; }}
    .actions {{ display: flex; gap: 12px; flex-wrap: wrap; margin-top: 18px; }}
    button {{ border: 0; border-radius: 6px; padding: 10px 16px; background: #22577a; color: #fff; cursor: pointer; font-weight: 650; }}
    button.secondary {{ background: #5f6f52; }}
    .result {{ background: #fff; border: 1px solid #d6d0c4; border-radius: 8px; padding: 18px; margin-top: 20px; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; padding: 0; list-style: none; }}
    .stats li {{ border: 1px solid #e4dfd5; border-radius: 6px; padding: 10px; background: #fbfaf8; }}
    .downloads a {{ display: inline-block; margin: 6px 10px 0 0; color: #174ea6; }}
    .error {{ border-color: #c5221f; color: #9b1c1c; }}
  </style>
</head>
<body>
<main>
  <h1>docx-template-agent</h1>
  <p>上传 docx，选择模板，然后执行格式检查或生成新的排版 docx。</p>
  <form method="post" enctype="multipart/form-data">
    <label for="file">DOCX 文件</label>
    <input id="file" name="file" type="file" accept=".docx" required>
    <label for="template">模板</label>
    <select id="template" name="template_id" required>
      {_template_options(selected_template)}
    </select>
    <label class="checkline">
      <input name="use_llm" type="checkbox" value="true">
      启用 LLM 辅助分析
    </label>
    <div class="actions">
      <button type="submit" formaction="/check">执行格式检查</button>
      <button type="submit" formaction="/format" class="secondary">执行模板排版</button>
    </div>
  </form>
  {content}
</main>
</body>
</html>"""
    return HTMLResponse(html)


def _result_html(result: service.WebJobResult) -> str:
    docx_link = ""
    if result.formatted_docx is not None:
        docx_link = (
            f'<a href="/download/{result.job_id}/docx">下载新 docx</a>'
        )
    llm_link = ""
    if result.llm_analysis is not None:
        llm_link = f'<a href="/download/{result.job_id}/llm_analysis">下载 LLM 分析 JSON</a>'
    return f"""
<section class="result">
  <h2>{'模板排版完成' if result.action == 'format' else '格式检查完成'}</h2>
  <ul class="stats">
    <li>模板<br><strong>{escape(result.template)}</strong></li>
    <li>段落数<br><strong>{result.paragraph_count}</strong></li>
    <li>表格数<br><strong>{result.table_count}</strong></li>
    <li>问题数<br><strong>{result.issue_count}</strong></li>
    <li>操作数<br><strong>{result.operation_count}</strong></li>
    <li>失败操作<br><strong>{result.failed_operation_count}</strong></li>
  </ul>
  <div class="downloads">
    {docx_link}
    <a href="/download/{result.job_id}/markdown">下载 markdown 检查报告</a>
    <a href="/download/{result.job_id}/json">下载 json 修改明细</a>
    {llm_link}
  </div>
</section>"""


def _error_html(message: str) -> str:
    return f'<section class="result error"><strong>处理失败</strong><p>{escape(message)}</p></section>'


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return _page()


@app.get("/api/templates")
def api_templates() -> dict[str, object]:
    templates = service.list_templates()
    return {"ok": True, "templates": templates, "count": len(templates)}


@app.post("/check", response_class=HTMLResponse)
def check_docx(
    file: UploadFile = File(...),
    template_id: str = Form(...),
    use_llm: bool = Form(False),
) -> HTMLResponse:
    try:
        result = service.run_check(
            file.file,
            file.filename or "upload.docx",
            template_id,
            use_llm=use_llm,
        )
    except Exception as exc:
        return _page(_error_html(str(exc)), template_id)
    return _page(_result_html(result), template_id)


@app.post("/format", response_class=HTMLResponse)
def format_docx(
    file: UploadFile = File(...),
    template_id: str = Form(...),
    use_llm: bool = Form(False),
) -> HTMLResponse:
    try:
        result = service.run_format(
            file.file,
            file.filename or "upload.docx",
            template_id,
            use_llm=use_llm,
        )
    except Exception as exc:
        return _page(_error_html(str(exc)), template_id)
    return _page(_result_html(result), template_id)


@app.get("/download/{job_id}/{artifact}")
def download(job_id: str, artifact: str) -> FileResponse:
    try:
        path = service.resolve_download(job_id, artifact)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(path, filename=path.name)
