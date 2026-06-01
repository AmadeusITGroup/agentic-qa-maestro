"""
App flow knowledge tools for Agentic QA Maestro.

Loads pre-recorded app flow YAML files and provides them as context
to enrich the app discovery phase (Phase 2.5).
"""

import os
from pathlib import Path
from typing import Any

import yaml
from agent_framework import tool


def _resolve_app_flows_dir() -> Path:
    """Resolve the app_flows directory relative to the project root."""
    # Check env var first, then default to app_flows/ relative to cwd
    flows_dir = os.environ.get("APP_FLOWS_DIR", "app_flows")
    return Path(flows_dir)


def _load_all_flows() -> dict[str, Any]:
    """Load all YAML files from the app_flows directory."""
    flows_dir = _resolve_app_flows_dir()
    all_flows: dict[str, Any] = {}

    if not flows_dir.exists():
        return all_flows

    for yaml_file in sorted(flows_dir.glob("*.yaml")):
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
            if data:
                all_flows[yaml_file.stem] = data

    return all_flows


@tool
def get_app_knowledge() -> str:
    """Load all pre-recorded app flow data from app_flows/*.yaml files.

    Returns a structured summary of known pages, selectors, navigation flows,
    and feature availability for the target application. This enriches the
    live browser discovery with pre-recorded knowledge.
    """
    flows = _load_all_flows()

    if not flows:
        return "No app flow files found in app_flows/ directory. Skipping knowledge enrichment."

    sections = []
    for app_name, data in flows.items():
        app_info = data.get("app", {})
        sections.append(f"## App: {app_info.get('name', app_name)}")
        sections.append(f"Base URL: {app_info.get('base_url', 'N/A')}")
        sections.append(f"Description: {app_info.get('description', 'N/A')}")

        # Pages and selectors
        pages = data.get("pages", [])
        if pages:
            sections.append("\n### Known Pages & Selectors:")
            for page in pages:
                sections.append(f"\n**{page['name']}** ({page.get('path', '/')})")
                sections.append(f"  Description: {page.get('description', '')}")
                selectors = page.get("selectors", {})
                for sel_name, sel_value in selectors.items():
                    sections.append(f"  - {sel_name}: `{sel_value}`")

        # Known flows
        flows_list = data.get("flows", [])
        if flows_list:
            sections.append("\n### Known Navigation Flows:")
            for flow in flows_list:
                sections.append(f"\n**{flow['name']}**")
                for i, step in enumerate(flow.get("steps", []), 1):
                    action = step.get("action", "")
                    selector = step.get("selector", "")
                    target = step.get("target", "")
                    desc = f"  {i}. {action}"
                    if selector:
                        desc += f" → `{selector}`"
                    if target:
                        desc += f" → {target}"
                    sections.append(desc)

        # Known features
        features = data.get("known_features", [])
        if features:
            sections.append("\n### Known Features:")
            for feat in features:
                status = "✅" if feat.get("available") else "❌"
                sections.append(f"  {status} {feat['name']} — {feat.get('notes', '')}")

        sections.append("")

    return "\n".join(sections)


@tool
def list_app_flows() -> str:
    """List all available app flow files in the app_flows/ directory."""
    flows_dir = _resolve_app_flows_dir()

    if not flows_dir.exists():
        return "No app_flows/ directory found."

    files = sorted(flows_dir.glob("*.yaml"))
    if not files:
        return "app_flows/ directory exists but contains no YAML files."

    result = "Available app flow files:\n"
    for f in files:
        result += f"  - {f.name}\n"
    return result


APP_KNOWLEDGE_TOOLS = [get_app_knowledge, list_app_flows]
