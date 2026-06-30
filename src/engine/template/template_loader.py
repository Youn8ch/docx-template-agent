"""YAML template loader for offline docx formatting templates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_TEMPLATE_DIR = Path("templates")
REQUIRED_TOP_LEVEL_KEYS = ("rules", "safety")


def _resolve_template_path(template_id_or_path: str | Path, template_dir: str | Path) -> Path:
    value = Path(template_id_or_path)
    if value.suffix.lower() in {".yaml", ".yml"} or value.parent != Path("."):
        return value

    return Path(template_dir) / f"{value.name}.yaml"


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"template not found: {path}")
    if not path.is_file():
        raise ValueError(f"template path is not a file: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid yaml template: {path}") from exc
    except OSError as exc:
        raise OSError(f"failed to read template: {path}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"template yaml root must be a mapping: {path}")
    return data


def _validate_template(data: dict[str, Any], path: Path) -> None:
    missing = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in data]
    if missing:
        raise ValueError(f"template {path} missing required key(s): {', '.join(missing)}")
    if not isinstance(data["rules"], dict):
        raise ValueError(f"template {path} key 'rules' must be a mapping")
    if not isinstance(data["safety"], dict):
        raise ValueError(f"template {path} key 'safety' must be a mapping")
    if not data.get("template_id"):
        raise ValueError(f"template {path} missing required key: template_id")


def load_template(
    template_id_or_path: str | Path,
    template_dir: str | Path = DEFAULT_TEMPLATE_DIR,
) -> dict[str, Any]:
    """Load a template by id such as ``report`` or by explicit YAML path."""

    template_path = _resolve_template_path(template_id_or_path, template_dir)
    data = _read_yaml(template_path)
    _validate_template(data, template_path)
    return data


def list_templates(template_dir: str | Path = DEFAULT_TEMPLATE_DIR) -> list[dict[str, str]]:
    """Return metadata for all available YAML templates in the template directory."""

    root = Path(template_dir)
    if not root.exists():
        raise FileNotFoundError(f"template directory not found: {root}")
    if not root.is_dir():
        raise ValueError(f"template directory path is not a directory: {root}")

    templates: list[dict[str, str]] = []
    for path in sorted(root.glob("*.y*ml")):
        data = _read_yaml(path)
        _validate_template(data, path)
        templates.append(
            {
                "template_id": str(data.get("template_id", "")),
                "template_name": str(data.get("template_name", "")),
                "description": str(data.get("description", "")),
            }
        )
    return templates
