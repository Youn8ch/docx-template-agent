"""Read-only access to XML parts inside a docx package."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from lxml import etree
from pydantic import BaseModel


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": WORD_NS}


class DocxPackageParts(BaseModel):
    path: Path
    document_xml: etree._Element
    styles_xml: etree._Element | None = None
    numbering_xml: etree._Element | None = None
    settings_xml: etree._Element | None = None

    model_config = {"arbitrary_types_allowed": True}


def parse_xml_part(package: ZipFile, name: str) -> etree._Element | None:
    try:
        payload = package.read(name)
    except KeyError:
        return None
    return etree.fromstring(payload)


def read_docx_package(path: str | Path) -> DocxPackageParts:
    docx_path = Path(path)
    with ZipFile(docx_path) as package:
        document_xml = parse_xml_part(package, "word/document.xml")
        if document_xml is None:
            raise ValueError("docx is missing word/document.xml")
        return DocxPackageParts(
            path=docx_path,
            document_xml=document_xml,
            styles_xml=parse_xml_part(package, "word/styles.xml"),
            numbering_xml=parse_xml_part(package, "word/numbering.xml"),
            settings_xml=parse_xml_part(package, "word/settings.xml"),
        )


def w_tag(local_name: str) -> str:
    return f"{{{WORD_NS}}}{local_name}"


def w_val(element: etree._Element | None, attr_name: str = "val") -> str | None:
    if element is None:
        return None
    return element.get(w_tag(attr_name))
