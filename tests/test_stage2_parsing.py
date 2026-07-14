from lxml import etree

import pytest
from pydantic import ValidationError
from docx.shared import Length, Pt
from enum import Enum

from src.engine.model.facts_model import DocumentFacts, FormatValue, ParagraphFacts, PositionFeatures
from src.engine.parser.docx_package_reader import NSMAP
from src.engine.parser.numbering_parser import paragraph_numbering, parse_numbering_registry
from src.engine.parser.style_resolver import (
    is_trusted_heading_style,
    paragraph_style_id,
    parse_style_registry,
    resolve_paragraph_property,
    resolve_run_property,
    style_inheritance_path,
)


def _xml(text: str):
    return etree.fromstring(text.encode("utf-8"))


def test_format_value_records_source_and_inheritance_path():
    styles = _xml(
        """
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:docDefaults>
            <w:rPrDefault><w:rPr><w:sz w:val="18"/></w:rPr></w:rPrDefault>
          </w:docDefaults>
          <w:style w:type="paragraph" w:styleId="Base">
            <w:name w:val="Base Style"/>
            <w:rPr><w:sz w:val="24"/></w:rPr>
          </w:style>
          <w:style w:type="paragraph" w:styleId="Body">
            <w:name w:val="Body Style"/>
            <w:basedOn w:val="Base"/>
          </w:style>
        </w:styles>
        """
    )
    paragraph = _xml(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:pPr><w:pStyle w:val="Body"/></w:pPr>
          <w:r><w:t>Hello</w:t></w:r>
        </w:p>
        """
    )
    registry = parse_style_registry(styles)
    value = resolve_run_property(registry, paragraph.find("w:r", namespaces=NSMAP), "Body", "font_size")

    assert value.raw_value == 12
    assert value.resolved_value == 12
    assert value.source == "base_style"
    assert value.source_style_id == "Base"
    assert [step.style_id for step in value.inheritance_path] == ["Body", "Base"]


def test_run_direct_precedes_character_style_paragraph_style_and_defaults():
    styles = _xml(
        """
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:docDefaults>
            <w:rPrDefault><w:rPr><w:b w:val="0"/></w:rPr></w:rPrDefault>
          </w:docDefaults>
          <w:style w:type="paragraph" w:styleId="Body">
            <w:name w:val="Body"/>
            <w:rPr><w:b w:val="0"/></w:rPr>
          </w:style>
          <w:style w:type="character" w:styleId="Strong">
            <w:name w:val="Strong"/>
            <w:rPr><w:b/></w:rPr>
          </w:style>
        </w:styles>
        """
    )
    run = _xml(
        """
        <w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:rPr><w:rStyle w:val="Strong"/><w:b w:val="0"/></w:rPr>
          <w:t>Hello</w:t>
        </w:r>
        """
    )

    value = resolve_run_property(parse_style_registry(styles), run, "Body", "bold")

    assert value.resolved_value is False
    assert value.source == "run_direct"


def test_paragraph_direct_precedes_style_and_defaults():
    styles = _xml(
        """
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:docDefaults>
            <w:pPrDefault><w:pPr><w:jc w:val="left"/></w:pPr></w:pPrDefault>
          </w:docDefaults>
          <w:style w:type="paragraph" w:styleId="Body">
            <w:name w:val="Body"/>
            <w:pPr><w:jc w:val="center"/></w:pPr>
          </w:style>
        </w:styles>
        """
    )
    paragraph = _xml(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:pPr><w:pStyle w:val="Body"/><w:jc w:val="right"/></w:pPr>
        </w:p>
        """
    )

    value = resolve_paragraph_property(parse_style_registry(styles), paragraph, "Body", "alignment")

    assert value.resolved_value == "right"
    assert value.source == "paragraph_direct"


def test_multilevel_based_on_path_and_trusted_heading_inheritance():
    styles = _xml(
        """
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:style w:type="paragraph" w:styleId="Heading1">
            <w:name w:val="Heading 1"/>
          </w:style>
          <w:style w:type="paragraph" w:styleId="CustomHeading">
            <w:name w:val="Custom Heading"/>
            <w:basedOn w:val="Heading1"/>
          </w:style>
          <w:style w:type="paragraph" w:styleId="ProjectHeading">
            <w:name w:val="Project Heading"/>
            <w:basedOn w:val="CustomHeading"/>
          </w:style>
        </w:styles>
        """
    )
    registry = parse_style_registry(styles)
    path, errors = style_inheritance_path(registry, "ProjectHeading")
    trusted, inherited = is_trusted_heading_style(registry, "ProjectHeading")

    assert errors == []
    assert [style.style_id for style in path] == ["ProjectHeading", "CustomHeading", "Heading1"]
    assert trusted is False
    assert inherited is True


def test_cyclic_based_on_reference_does_not_loop():
    styles = _xml(
        """
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:style w:type="paragraph" w:styleId="A"><w:basedOn w:val="B"/></w:style>
          <w:style w:type="paragraph" w:styleId="B"><w:basedOn w:val="A"/></w:style>
        </w:styles>
        """
    )
    registry = parse_style_registry(styles)
    path, errors = style_inheritance_path(registry, "A")

    assert [style.style_id for style in path] == ["A", "B"]
    assert errors == ["cyclic basedOn reference: A"]
    assert registry.summary.cyclic_based_on == ["A"]


def test_missing_based_on_reference_is_reported():
    styles = _xml(
        """
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:style w:type="paragraph" w:styleId="A"><w:basedOn w:val="Missing"/></w:style>
        </w:styles>
        """
    )
    registry = parse_style_registry(styles)
    path, errors = style_inheritance_path(registry, "A")

    assert [style.style_id for style in path] == ["A"]
    assert errors == ["basedOn target not found: Missing"]
    assert registry.summary.unresolved_based_on == ["Missing"]


def test_numbering_registry_resolves_level_facts():
    numbering = _xml(
        """
        <w:numbering xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:abstractNum w:abstractNumId="7">
            <w:lvl w:ilvl="1">
              <w:start w:val="1"/>
              <w:numFmt w:val="decimal"/>
              <w:lvlText w:val="%1.%2"/>
              <w:pStyle w:val="ListParagraph"/>
              <w:suff w:val="tab"/>
              <w:lvlJc w:val="left"/>
            </w:lvl>
          </w:abstractNum>
          <w:num w:numId="42"><w:abstractNumId w:val="7"/></w:num>
        </w:numbering>
        """
    )
    paragraph = _xml(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:pPr><w:numPr><w:ilvl w:val="1"/><w:numId w:val="42"/></w:numPr></w:pPr>
        </w:p>
        """
    )
    registry = parse_numbering_registry(numbering)
    facts = paragraph_numbering(paragraph, registry)

    assert facts.num_id == "42"
    assert facts.ilvl == 1
    assert facts.abstract_num_id == "7"
    assert facts.level_start == "1"
    assert facts.num_format == "decimal"
    assert facts.level_text == "%1.%2"
    assert facts.p_style == "ListParagraph"
    assert facts.suffix == "tab"
    assert facts.level_justification == "left"
    assert facts.readable is True


def test_numbering_illegal_reference_is_not_silently_completed():
    paragraph = _xml(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="99"/></w:numPr></w:pPr>
        </w:p>
        """
    )
    registry = parse_numbering_registry(None)
    facts = paragraph_numbering(paragraph, registry)

    assert facts.readable is False
    assert facts.error == "numId not found: 99"
    assert registry.summary.unresolved_num_ids == ["99"]


def test_fact_models_do_not_share_list_or_dict_defaults():
    first = DocumentFacts()
    second = DocumentFacts()
    first.body_paragraphs.append(
        ParagraphFacts(
            container_type="body",
            paragraph_index=1,
            position_features=PositionFeatures(
                container_type="body",
                paragraph_index=1,
                top_level_document_flow=True,
            ),
        )
    )
    first.body_paragraphs[0].rule_hints.append(
        {"hint_type": "short_text", "confidence": 0.5, "evidence": ["short"]}
    )
    value_a = FormatValue()
    value_b = FormatValue()
    value_a.inheritance_path.append({"style_id": "A"})

    assert second.body_paragraphs == []
    assert value_b.inheritance_path == []


def test_paragraph_style_id_reads_from_xml():
    paragraph = _xml(
        """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:pPr><w:pStyle w:val="Normal"/></w:pPr>
        </w:p>
        """
    )

    assert paragraph_style_id(paragraph) == "Normal"


def test_format_value_rejects_non_json_stable_objects():
    with pytest.raises(ValidationError):
        FormatValue(raw_value=_xml("<root/>"))

    with pytest.raises(ValidationError):
        FormatValue(resolved_value=float("inf"))


def test_format_value_accepts_only_exact_json_primitives():
    class IntLike(int):
        pass

    class FloatLike(float):
        pass

    class Choice(Enum):
        VALUE = "value"

    for value in ["text", 1, 1.25, True, False, None, {"items": [1, "x", None]}]:
        assert FormatValue(raw_value=value).raw_value == value

    rejected_values = [
        Pt(12),
        Length(240),
        Choice.VALUE,
        IntLike(1),
        FloatLike(1.25),
        {"bad": [Pt(10)]},
        [Choice.VALUE],
        float("nan"),
        float("inf"),
        float("-inf"),
    ]
    for value in rejected_values:
        with pytest.raises(ValidationError):
            FormatValue(raw_value=value)


def test_run_direct_value_survives_character_style_cycle():
    styles = _xml(
        """
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:style w:type="character" w:styleId="A"><w:basedOn w:val="B"/></w:style>
          <w:style w:type="character" w:styleId="B"><w:basedOn w:val="A"/></w:style>
        </w:styles>
        """
    )
    run = _xml(
        """
        <w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:rPr><w:rStyle w:val="A"/><w:b w:val="0"/></w:rPr>
          <w:t>Hello</w:t>
        </w:r>
        """
    )

    value = resolve_run_property(parse_style_registry(styles), run, None, "bold")

    assert value.readable is True
    assert value.resolved_value is False
    assert value.source == "run_direct"


def test_current_style_value_survives_missing_based_on():
    styles = _xml(
        """
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:style w:type="character" w:styleId="Strong">
            <w:basedOn w:val="Missing"/>
            <w:rPr><w:b/></w:rPr>
          </w:style>
        </w:styles>
        """
    )
    run = _xml(
        """
        <w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:rPr><w:rStyle w:val="Strong"/></w:rPr>
          <w:t>Hello</w:t>
        </w:r>
        """
    )

    value = resolve_run_property(parse_style_registry(styles), run, None, "bold")

    assert value.readable is True
    assert value.resolved_value is True
    assert value.source == "character_style"


def test_inheritance_failure_is_field_local():
    styles = _xml(
        """
        <w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:style w:type="paragraph" w:styleId="Body">
            <w:basedOn w:val="Missing"/>
            <w:rPr><w:sz w:val="24"/></w:rPr>
          </w:style>
        </w:styles>
        """
    )
    registry = parse_style_registry(styles)
    run = _xml(
        """
        <w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:t>Hello</w:t>
        </w:r>
        """
    )

    font_size = resolve_run_property(registry, run, "Body", "font_size")
    italic = resolve_run_property(registry, run, "Body", "italic")

    assert font_size.readable is True
    assert font_size.resolved_value == 12
    assert italic.readable is False
    assert italic.error == "basedOn target not found: Missing"
