from pathlib import Path

from src.engine.template.template_loader import list_templates, load_template


def test_load_report_template_by_id():
    template = load_template("report")

    assert template["template_id"] == "report"
    assert "rules" in template
    assert "safety" in template
    assert {"title", "heading_1", "heading_2", "heading_3", "body"}.issubset(
        template["rules"]
    )
    assert template["safety"]["allow_text_change"] is False
    assert template["safety"]["allow_delete_paragraph"] is False
    assert template["safety"]["allow_modify_table_text"] is False
    assert template["safety"]["allow_overwrite_source"] is False


def test_load_report_template_by_path():
    template_path = Path("templates") / "report.yaml"

    template = load_template(template_path)

    assert template["template_id"] == "report"


def test_report_template_is_listed():
    templates = list_templates()

    assert any(template["template_id"] == "report" for template in templates)
