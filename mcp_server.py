"""MCP server entrypoint for docx-template-agent."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from src.mcp.tools import (
    analyze_docx as analyze_docx_tool,
    apply_docx_template as apply_docx_template_tool,
    check_docx_style as check_docx_style_tool,
    generate_review_report as generate_review_report_tool,
    list_templates as list_templates_tool,
)


mcp = FastMCP(
    "docx-template-agent",
    instructions=(
        "Offline docx template formatting tools. Tools accept JSON objects "
        "and return JSON objects. Document changes are delegated to src.engine "
        "operations only."
    ),
)


@mcp.tool()
def list_templates(request: dict[str, Any] | None = None) -> dict[str, Any]:
    """List available docx formatting templates."""

    return list_templates_tool(request)


@mcp.tool()
def analyze_docx(request: dict[str, Any]) -> dict[str, Any]:
    """Read a docx and return structure/style analysis JSON."""

    return analyze_docx_tool(request)


@mcp.tool()
def check_docx_style(request: dict[str, Any]) -> dict[str, Any]:
    """Check a docx against a template and return issues and safe operations."""

    return check_docx_style_tool(request)


@mcp.tool()
def apply_docx_template(request: dict[str, Any]) -> dict[str, Any]:
    """Apply a template through whitelisted engine operations."""

    return apply_docx_template_tool(request)


@mcp.tool()
def generate_review_report(request: dict[str, Any]) -> dict[str, Any]:
    """Generate markdown and JSON review reports without modifying the docx."""

    return generate_review_report_tool(request)


if __name__ == "__main__":
    mcp.run()
