"""Parse Word numbering definitions as read-only facts."""

from __future__ import annotations

from lxml import etree
from pydantic import BaseModel, Field

from src.engine.model.facts_model import NumberingFacts, NumberingRegistrySummary
from src.engine.parser.docx_package_reader import NSMAP, w_tag, w_val


class NumberingLevel(BaseModel):
    ilvl: int
    start: str | None = None
    num_format: str | None = None
    level_text: str | None = None
    p_style: str | None = None
    suffix: str | None = None
    level_justification: str | None = None


class AbstractNumbering(BaseModel):
    abstract_num_id: str
    levels: dict[int, NumberingLevel] = Field(default_factory=dict)


class NumberingDefinition(BaseModel):
    num_id: str
    abstract_num_id: str | None = None


class NumberingRegistry(BaseModel):
    nums: dict[str, NumberingDefinition] = Field(default_factory=dict)
    abstract_nums: dict[str, AbstractNumbering] = Field(default_factory=dict)
    unresolved_num_ids: list[str] = Field(default_factory=list)

    @property
    def summary(self) -> NumberingRegistrySummary:
        return NumberingRegistrySummary(
            numbering_count=len(self.nums),
            abstract_numbering_count=len(self.abstract_nums),
            unresolved_num_ids=list(self.unresolved_num_ids),
        )


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_numbering_registry(numbering_xml: etree._Element | None) -> NumberingRegistry:
    registry = NumberingRegistry()
    if numbering_xml is None:
        return registry

    for abstract in numbering_xml.findall("w:abstractNum", namespaces=NSMAP):
        abstract_id = w_val(abstract, "abstractNumId")
        if not abstract_id:
            continue
        parsed = AbstractNumbering(abstract_num_id=abstract_id)
        for lvl in abstract.findall("w:lvl", namespaces=NSMAP):
            ilvl = _int_or_none(w_val(lvl, "ilvl"))
            if ilvl is None:
                continue
            parsed.levels[ilvl] = NumberingLevel(
                ilvl=ilvl,
                start=w_val(lvl.find("w:start", namespaces=NSMAP)),
                num_format=w_val(lvl.find("w:numFmt", namespaces=NSMAP)),
                level_text=w_val(lvl.find("w:lvlText", namespaces=NSMAP)),
                p_style=w_val(lvl.find("w:pStyle", namespaces=NSMAP)),
                suffix=w_val(lvl.find("w:suff", namespaces=NSMAP)),
                level_justification=w_val(lvl.find("w:lvlJc", namespaces=NSMAP)),
            )
        registry.abstract_nums[abstract_id] = parsed

    for num in numbering_xml.findall("w:num", namespaces=NSMAP):
        num_id = w_val(num, "numId")
        if not num_id:
            continue
        abstract_id = w_val(num.find("w:abstractNumId", namespaces=NSMAP))
        registry.nums[num_id] = NumberingDefinition(num_id=num_id, abstract_num_id=abstract_id)
    return registry


def paragraph_numbering(paragraph_element: etree._Element, registry: NumberingRegistry, style_has_numbering: bool = False) -> NumberingFacts:
    num_pr = paragraph_element.find("w:pPr/w:numPr", namespaces=NSMAP)
    if num_pr is None:
        return NumberingFacts(
            unsupported_reason="style-derived numbering is not resolved in stage 2" if style_has_numbering else None
        )
    num_id = w_val(num_pr.find("w:numId", namespaces=NSMAP))
    ilvl = _int_or_none(w_val(num_pr.find("w:ilvl", namespaces=NSMAP)))
    facts = NumberingFacts(direct_numbering_present=True, num_id=num_id, ilvl=ilvl)
    if not num_id:
        facts.readable = False
        facts.error = "numPr is missing numId"
        return facts
    num_def = registry.nums.get(num_id)
    if num_def is None:
        facts.readable = False
        facts.error = f"numId not found: {num_id}"
        registry.unresolved_num_ids.append(num_id)
        return facts
    facts.abstract_num_id = num_def.abstract_num_id
    if num_def.abstract_num_id is None:
        facts.readable = False
        facts.error = f"numId has no abstractNumId: {num_id}"
        return facts
    abstract = registry.abstract_nums.get(num_def.abstract_num_id)
    if abstract is None:
        facts.readable = False
        facts.error = f"abstractNumId not found: {num_def.abstract_num_id}"
        return facts
    if ilvl is None:
        return facts
    level = abstract.levels.get(ilvl)
    if level is None:
        facts.readable = False
        facts.error = f"ilvl not found: {ilvl}"
        return facts
    facts.level_start = level.start
    facts.num_format = level.num_format
    facts.level_text = level.level_text
    facts.p_style = level.p_style
    facts.suffix = level.suffix
    facts.level_justification = level.level_justification
    return facts
