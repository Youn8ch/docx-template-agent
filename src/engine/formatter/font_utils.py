"""Font and paragraph-format helpers for python-docx."""

from __future__ import annotations

from typing import Any

from docx.oxml.ns import qn
from docx.shared import Pt


def normalize_font_name(name: str | None) -> str | None:
    return name.strip() if isinstance(name, str) and name.strip() else None


def is_valid_font_size(size_pt: float | int | None) -> bool:
    if size_pt is None:
        return True
    try:
        return 1 <= float(size_pt) <= 200
    except (TypeError, ValueError):
        return False


def set_run_font_name(run: Any, font_name: str | None) -> None:
    normalized = normalize_font_name(font_name)
    if normalized is None:
        return

    run.font.name = normalized
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.get_or_add_rFonts()
    r_fonts.set(qn("w:eastAsia"), normalized)


def set_run_font_size(run: Any, font_size: float | int | None) -> None:
    if font_size is None:
        return
    if not is_valid_font_size(font_size):
        raise ValueError(f"invalid font size: {font_size}")
    run.font.size = Pt(float(font_size))


def set_run_bold(run: Any, bold: bool | None) -> None:
    if bold is not None:
        run.font.bold = bool(bold)


def set_run_font(run: Any, properties: dict[str, Any]) -> None:
    set_run_font_name(run, properties.get("font_name"))
    set_run_font_size(run, properties.get("font_size"))
    set_run_bold(run, properties.get("bold"))


def first_line_indent_chars_value(properties: dict[str, Any]) -> int | None:
    chars = properties.get("first_line_indent_chars")
    if chars is None:
        return None
    return int(float(chars) * 100)
