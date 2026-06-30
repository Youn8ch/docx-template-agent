from pathlib import Path

from src.engine.model.document_model import DocumentModel, ParagraphInfo
from src.engine.parser.structure_detector import detect_structure


def test_detects_title_headings_and_body_without_changing_text():
    paragraphs = [
        ParagraphInfo(index=1, text="  "),
        ParagraphInfo(index=2, text="\u6b63\u5f0f\u62a5\u544a"),
        ParagraphInfo(index=3, text="\u4e00\u3001\u603b\u4f53\u60c5\u51b5"),
        ParagraphInfo(index=4, text="\uff08\u4e00\uff09\u5de5\u4f5c\u8fdb\u5c55"),
        ParagraphInfo(index=5, text="1. \u91cd\u70b9\u4e8b\u9879"),
        ParagraphInfo(index=6, text="\u8fd9\u662f\u4e00\u6bb5\u6b63\u6587\u5185\u5bb9\u3002"),
    ]
    document = DocumentModel(filepath=Path("sample.docx"), paragraphs=paragraphs)

    detected = detect_structure(document)

    assert [paragraph.role for paragraph in detected.paragraphs] == [
        "empty",
        "title",
        "heading_1",
        "heading_2",
        "heading_3",
        "body",
    ]
    assert [paragraph.text for paragraph in detected.paragraphs] == [
        paragraph.text for paragraph in paragraphs
    ]
