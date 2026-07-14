"""Resolve Word styles and inherited formatting from XML parts."""

from __future__ import annotations

import re
from collections.abc import Iterable
from copy import deepcopy
from typing import Any, Literal

from lxml import etree
from pydantic import BaseModel, Field

from src.engine.model.facts_model import FormatValue, InheritanceStep, StyleRegistrySummary, ValueSource
from src.engine.parser.docx_package_reader import NSMAP, w_tag, w_val


PROPERTY_KIND = Literal["run", "paragraph"]

RUN_PROPS = {
    "font_name",
    "font_size",
    "bold",
    "italic",
}
PARAGRAPH_PROPS = {
    "alignment",
    "line_spacing",
    "space_before",
    "space_after",
    "first_line_indent",
    "first_line_indent_chars",
    "hanging",
    "hanging_chars",
    "outline_level",
}
TRUSTED_HEADING_IDS = {f"Heading{i}" for i in range(1, 10)}
TRUSTED_HEADING_ID_RE = re.compile(r"^heading ?[1-9]$", re.IGNORECASE)
TRUSTED_CN_HEADING_RE = re.compile(r"^标题 ?[1-9]$")


class StyleDefinition(BaseModel):
    style_id: str
    style_name: str | None = None
    style_type: str | None = None
    based_on: str | None = None
    readable: bool = True
    error: str | None = None
    element: Any = Field(default=None, exclude=True)

    model_config = {"arbitrary_types_allowed": True}


class StyleRegistry(BaseModel):
    styles: dict[str, StyleDefinition] = Field(default_factory=dict)
    doc_defaults_rpr: Any = None
    doc_defaults_ppr: Any = None
    unresolved_based_on: list[str] = Field(default_factory=list)
    cyclic_based_on: list[str] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def summary(self) -> StyleRegistrySummary:
        paragraph_count = sum(1 for style in self.styles.values() if style.style_type == "paragraph")
        character_count = sum(1 for style in self.styles.values() if style.style_type == "character")
        return StyleRegistrySummary(
            style_count=len(self.styles),
            paragraph_style_count=paragraph_count,
            character_style_count=character_count,
            unresolved_based_on=list(self.unresolved_based_on),
            cyclic_based_on=list(self.cyclic_based_on),
        )


def _child(element: etree._Element | None, path: str) -> etree._Element | None:
    if element is None:
        return None
    return element.find(path, namespaces=NSMAP)


def _children(element: etree._Element | None, path: str) -> list[etree._Element]:
    if element is None:
        return []
    return list(element.findall(path, namespaces=NSMAP))


def _style_step(style: StyleDefinition) -> InheritanceStep:
    return InheritanceStep(
        style_id=style.style_id,
        style_name=style.style_name,
        style_type=style.style_type,
    )


def parse_style_registry(styles_xml: etree._Element | None) -> StyleRegistry:
    registry = StyleRegistry()
    if styles_xml is None:
        return registry

    registry.doc_defaults_rpr = _child(styles_xml, "w:docDefaults/w:rPrDefault/w:rPr")
    registry.doc_defaults_ppr = _child(styles_xml, "w:docDefaults/w:pPrDefault/w:pPr")

    for style_el in styles_xml.findall("w:style", namespaces=NSMAP):
        style_id = w_val(style_el, "styleId")
        if not style_id:
            continue
        name = w_val(_child(style_el, "w:name"))
        style_type = w_val(style_el, "type")
        based_on = w_val(_child(style_el, "w:basedOn"))
        definition = StyleDefinition(
            style_id=style_id,
            style_name=name,
            style_type=style_type,
            based_on=based_on,
            element=style_el,
        )
        registry.styles[style_id] = definition
    return registry


def style_element(style: StyleDefinition | None) -> etree._Element | None:
    if style is None:
        return None
    return style.element


def style_inheritance_path(
    registry: StyleRegistry,
    style_id: str | None,
) -> tuple[list[StyleDefinition], list[str]]:
    if not style_id:
        return [], []
    path: list[StyleDefinition] = []
    errors: list[str] = []
    seen: set[str] = set()
    current_id: str | None = style_id
    while current_id:
        if current_id in seen:
            error = f"cyclic basedOn reference: {current_id}"
            errors.append(error)
            if current_id not in registry.cyclic_based_on:
                registry.cyclic_based_on.append(current_id)
            break
        seen.add(current_id)
        style = registry.styles.get(current_id)
        if style is None:
            error = f"basedOn target not found: {current_id}"
            errors.append(error)
            if current_id not in registry.unresolved_based_on:
                registry.unresolved_based_on.append(current_id)
            break
        path.append(style)
        current_id = style.based_on
    return path, errors


def is_trusted_heading_style(registry: StyleRegistry, style_id: str | None) -> tuple[bool, bool]:
    path, _errors = style_inheritance_path(registry, style_id)
    if not path:
        return False, False
    for index, style in enumerate(path):
        if is_builtin_heading_identity(style.style_id, style.style_name):
            return index == 0, index > 0
    return False, False


def is_builtin_heading_identity(style_id: str | None, style_name: str | None) -> bool:
    if style_id:
        normalized_id = style_id.strip()
        if normalized_id in TRUSTED_HEADING_IDS or TRUSTED_HEADING_ID_RE.fullmatch(normalized_id):
            return True
    if style_name:
        normalized_name = style_name.strip()
        if TRUSTED_HEADING_ID_RE.fullmatch(normalized_name) or TRUSTED_CN_HEADING_RE.fullmatch(normalized_name):
            return True
    return False


def _run_property(rpr: etree._Element | None, property_name: str) -> Any:
    if rpr is None:
        return None
    if property_name == "font_name":
        r_fonts = _child(rpr, "w:rFonts")
        if r_fonts is None:
            return None
        values = {
            "eastAsia": r_fonts.get(w_tag("eastAsia")),
            "ascii": r_fonts.get(w_tag("ascii")),
            "hAnsi": r_fonts.get(w_tag("hAnsi")),
            "cs": r_fonts.get(w_tag("cs")),
        }
        return {key: value for key, value in values.items() if value is not None} or None
    if property_name == "font_size":
        size = w_val(_child(rpr, "w:sz"))
        if size is None:
            return None
        try:
            return int(size) / 2
        except ValueError:
            return size
    if property_name == "bold":
        element = _child(rpr, "w:b")
        if element is None:
            return None
        value = w_val(element)
        return value not in {"0", "false", "False"}
    if property_name == "italic":
        element = _child(rpr, "w:i")
        if element is None:
            return None
        value = w_val(element)
        return value not in {"0", "false", "False"}
    return None


def _paragraph_property(ppr: etree._Element | None, property_name: str) -> Any:
    if ppr is None:
        return None
    if property_name == "alignment":
        return w_val(_child(ppr, "w:jc"))
    if property_name == "line_spacing":
        spacing = _child(ppr, "w:spacing")
        if spacing is None:
            return None
        raw = {
            "line": spacing.get(w_tag("line")),
            "lineRule": spacing.get(w_tag("lineRule")),
        }
        return {key: value for key, value in raw.items() if value is not None} or None
    if property_name == "space_before":
        return _twips_to_pt(_child(ppr, "w:spacing"), "before")
    if property_name == "space_after":
        return _twips_to_pt(_child(ppr, "w:spacing"), "after")
    if property_name == "first_line_indent":
        return _twips_to_pt(_child(ppr, "w:ind"), "firstLine")
    if property_name == "first_line_indent_chars":
        return _chars_to_count(_child(ppr, "w:ind"), "firstLineChars")
    if property_name == "hanging":
        return _twips_to_pt(_child(ppr, "w:ind"), "hanging")
    if property_name == "hanging_chars":
        return _chars_to_count(_child(ppr, "w:ind"), "hangingChars")
    if property_name == "outline_level":
        value = w_val(_child(ppr, "w:outlineLvl"))
        if value is None:
            return None
        try:
            return int(value)
        except ValueError:
            return value
    return None


def _twips_to_pt(element: etree._Element | None, attr_name: str) -> Any:
    if element is None:
        return None
    raw = element.get(w_tag(attr_name))
    if raw is None:
        return None
    try:
        return int(raw) / 20
    except ValueError:
        return raw


def _chars_to_count(element: etree._Element | None, attr_name: str) -> Any:
    if element is None:
        return None
    raw = element.get(w_tag(attr_name))
    if raw is None:
        return None
    try:
        return int(raw) / 100
    except ValueError:
        return raw


def _style_rpr(style: StyleDefinition) -> etree._Element | None:
    return _child(style_element(style), "w:rPr")


def _style_ppr(style: StyleDefinition) -> etree._Element | None:
    return _child(style_element(style), "w:pPr")


def _first_present(candidates: Iterable[tuple[Any, ValueSource, StyleDefinition | None]]) -> FormatValue:
    inheritance_path: list[InheritanceStep] = []
    for value, source, style in candidates:
        if style is not None:
            inheritance_path.append(_style_step(style))
        if value is None:
            continue
        return FormatValue(
            raw_value=deepcopy(value),
            resolved_value=deepcopy(_resolve_font_name(value) if isinstance(value, dict) else value),
            source=source,
            explicit=source in {"run_direct", "character_style", "paragraph_direct", "paragraph_style", "base_style"},
            readable=True,
            source_style_id=style.style_id if style else None,
            source_style_name=style.style_name if style else None,
            inheritance_path=inheritance_path,
        )
    return FormatValue(inheritance_path=inheritance_path)


def _resolve_font_name(value: dict[str, Any]) -> Any:
    return value.get("eastAsia") or value.get("ascii") or value.get("hAnsi") or value.get("cs")


def _format_value(
    value: Any,
    source: ValueSource,
    style: StyleDefinition | None = None,
    inheritance_path: list[InheritanceStep] | None = None,
    warnings: list[str] | None = None,
) -> FormatValue:
    return FormatValue(
        raw_value=deepcopy(value),
        resolved_value=deepcopy(_resolve_font_name(value) if isinstance(value, dict) else value),
        source=source,
        explicit=source in {"run_direct", "character_style", "paragraph_direct", "paragraph_style", "base_style"},
        readable=True,
        source_style_id=style.style_id if style else None,
        source_style_name=style.style_name if style else None,
        inheritance_path=inheritance_path or [],
        inherited_path_warnings=warnings or [],
    )


def _unreadable(error: str, inheritance_path: list[InheritanceStep]) -> FormatValue:
    return FormatValue(
        source="unreadable",
        readable=False,
        error=error,
        inheritance_path=inheritance_path,
    )


def _resolve_style_chain_property(
    registry: StyleRegistry,
    style_id: str | None,
    property_name: str,
    property_kind: PROPERTY_KIND,
    direct_source: ValueSource,
) -> tuple[FormatValue | None, list[InheritanceStep], str | None]:
    if not style_id:
        return None, [], None

    inheritance_path: list[InheritanceStep] = []
    seen: set[str] = set()
    current_id: str | None = style_id
    first = True
    while current_id:
        if current_id in seen:
            error = f"cyclic basedOn reference: {current_id}"
            if current_id not in registry.cyclic_based_on:
                registry.cyclic_based_on.append(current_id)
            return None, inheritance_path, error
        seen.add(current_id)

        style = registry.styles.get(current_id)
        if style is None:
            error = f"basedOn target not found: {current_id}"
            if current_id not in registry.unresolved_based_on:
                registry.unresolved_based_on.append(current_id)
            return None, inheritance_path, error

        inheritance_path.append(_style_step(style))
        value = (
            _run_property(_style_rpr(style), property_name)
            if property_kind == "run"
            else _paragraph_property(_style_ppr(style), property_name)
        )
        if value is not None:
            return (
                _format_value(
                    value,
                    direct_source if first else "base_style",
                    style,
                    inheritance_path=list(inheritance_path),
                ),
                inheritance_path,
                None,
            )

        current_id = style.based_on
        first = False
    return None, inheritance_path, None


def resolve_run_property(
    registry: StyleRegistry,
    run_element: etree._Element | None,
    paragraph_style_id: str | None,
    property_name: str,
) -> FormatValue:
    if property_name not in RUN_PROPS:
        return FormatValue(source="unreadable", readable=False, error=f"unsupported run property: {property_name}")
    rpr = _child(run_element, "w:rPr") if run_element is not None else None
    run_direct = _run_property(rpr, property_name)
    if run_direct is not None:
        return _format_value(run_direct, "run_direct")

    character_style_id = w_val(_child(rpr, "w:rStyle"))
    character_value, character_path, character_error = _resolve_style_chain_property(
        registry, character_style_id, property_name, "run", "character_style"
    )
    if character_value is not None:
        return character_value
    if character_error is not None:
        return _unreadable(character_error, character_path)

    paragraph_value, paragraph_path, paragraph_error = _resolve_style_chain_property(
        registry, paragraph_style_id, property_name, "run", "paragraph_style"
    )
    if paragraph_value is not None:
        return paragraph_value
    if paragraph_error is not None:
        return _unreadable(paragraph_error, character_path + paragraph_path)

    default_value = _run_property(registry.doc_defaults_rpr, property_name)
    if default_value is not None:
        return _format_value(default_value, "document_defaults", inheritance_path=character_path + paragraph_path)
    return FormatValue(inheritance_path=character_path + paragraph_path)


def resolve_paragraph_property(
    registry: StyleRegistry,
    paragraph_element: etree._Element | None,
    paragraph_style_id: str | None,
    property_name: str,
) -> FormatValue:
    if property_name not in PARAGRAPH_PROPS:
        return FormatValue(source="unreadable", readable=False, error=f"unsupported paragraph property: {property_name}")
    ppr = _child(paragraph_element, "w:pPr") if paragraph_element is not None else None
    direct = _paragraph_property(ppr, property_name)
    if direct is not None:
        return _format_value(direct, "paragraph_direct")

    paragraph_value, paragraph_path, paragraph_error = _resolve_style_chain_property(
        registry, paragraph_style_id, property_name, "paragraph", "paragraph_style"
    )
    if paragraph_value is not None:
        return paragraph_value
    if paragraph_error is not None:
        return _unreadable(paragraph_error, paragraph_path)

    default_value = _paragraph_property(registry.doc_defaults_ppr, property_name)
    if default_value is not None:
        return _format_value(default_value, "document_defaults", inheritance_path=paragraph_path)
    return FormatValue(inheritance_path=paragraph_path)


def paragraph_style_id(paragraph_element: etree._Element | None) -> str | None:
    return w_val(_child(_child(paragraph_element, "w:pPr"), "w:pStyle")) if paragraph_element is not None else None


def run_style_id(run_element: etree._Element | None) -> str | None:
    return w_val(_child(_child(run_element, "w:rPr"), "w:rStyle")) if run_element is not None else None
