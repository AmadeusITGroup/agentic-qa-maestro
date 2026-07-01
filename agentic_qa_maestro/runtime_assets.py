"""Helpers for packaged runtime assets used by installed CLI flows."""

from importlib.resources import files
from pathlib import Path
from typing import Iterable


_RESOURCE_ROOT = files("agentic_qa_maestro").joinpath("resources")


def packaged_asset(*parts: str):
    """Return a Traversable pointing at a packaged runtime asset."""
    asset = _RESOURCE_ROOT
    for part in parts:
        asset = asset.joinpath(part)
    return asset


def read_packaged_text(*parts: str) -> str:
    """Read a packaged text asset as UTF-8."""
    return packaged_asset(*parts).read_text(encoding="utf-8")


def iter_packaged_app_flows() -> Iterable:
    """Yield packaged app flow YAML files."""
    app_flows_dir = packaged_asset("app_flows")
    if not app_flows_dir.is_dir():
        return []
    return sorted(
        (entry for entry in app_flows_dir.iterdir() if entry.name.endswith(".yaml")),
        key=lambda entry: entry.name,
    )


def scaffold_runtime_files(destination: Path, force: bool = False) -> dict[str, list[str]]:
    """Write default runtime files into a target directory."""
    destination.mkdir(parents=True, exist_ok=True)
    app_flows_dir = destination / "app_flows"
    app_flows_dir.mkdir(exist_ok=True)

    assets = {
        destination / "application.yaml": read_packaged_text("application.yaml"),
        destination / ".env": read_packaged_text("example.env"),
        app_flows_dir / "example-app.yaml": read_packaged_text("app_flows", "example-app.yaml"),
    }

    created: list[str] = []
    skipped: list[str] = []

    for target_path, content in assets.items():
        if target_path.exists() and not force:
            skipped.append(str(target_path))
            continue
        target_path.write_text(content, encoding="utf-8")
        created.append(str(target_path))

    return {"created": created, "skipped": skipped}