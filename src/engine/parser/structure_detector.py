"""Detect paragraph roles from text only."""

from __future__ import annotations

import re

from src.engine.model.document_model import DocumentModel, ParagraphInfo, ParagraphRole


HEADING_1_RE = re.compile(r"^[一二三四]、\S+")
HEADING_2_RE = re.compile(r"^（[一二三四]）\S+")
HEADING_3_RE = re.compile(r"^(?:\d+、\S+|\d+\.\s+\S+|\d+(?:\.\d+)+\s+\S+)")


def _normalized_text(paragraph: ParagraphInfo) -> str:
    return (paragraph.text or "").strip()


def _is_first_short_non_empty(paragraph: ParagraphInfo, first_non_empty_index: int | None) -> bool:
    text = _normalized_text(paragraph)
    return paragraph.index == first_non_empty_index and 0 < len(text) < 40


def _detect_paragraph_role(
    paragraph: ParagraphInfo,
    first_non_empty_index: int | None,
) -> ParagraphRole:
    text = _normalized_text(paragraph)
    if not text:
        return "empty"
    if _is_first_short_non_empty(paragraph, first_non_empty_index):
        return "title"
    if HEADING_1_RE.match(text):
        return "heading_1"
    if HEADING_2_RE.match(text):
        return "heading_2"
    if HEADING_3_RE.match(text):
        return "heading_3"
    return "body"


def _first_non_empty_index(paragraphs: list[ParagraphInfo]) -> int | None:
    for paragraph in paragraphs:
        if _normalized_text(paragraph):
            return paragraph.index
    return None


def detect_structure(document: DocumentModel) -> DocumentModel:
    first_non_empty_index = _first_non_empty_index(document.paragraphs)
    updated: list[ParagraphInfo] = []
    for paragraph in document.paragraphs:
        role = _detect_paragraph_role(paragraph, first_non_empty_index)
        updated.append(paragraph.model_copy(update={"role": role}))
    return document.model_copy(update={"paragraphs": updated})
