"""Sanitized Local Mode project records persisted in GitDesk's private registry."""

from __future__ import annotations

from pathlib import Path
from typing import Any


# Keeps an icon path only when it remains lexically contained by its owning project.
def clean_project_icon_path(value: Any, project_path_value: Any) -> str:
    """Return a normalized in-project icon path, or an empty string for unsafe metadata."""

    raw_icon_path = str(value or "").strip()
    raw_project_path = str(project_path_value or "").strip()
    if not raw_icon_path or not raw_project_path:
        return ""
    try:
        project_path = Path(raw_project_path).expanduser().resolve(strict=False)
        icon_path = Path(raw_icon_path).expanduser().resolve(strict=False)
        icon_path.relative_to(project_path)
    except (OSError, RuntimeError, ValueError):
        return ""
    return str(icon_path)


# Cleans a registry record without requiring its project or optional artwork to exist during settings load.
def clean_local_project_record(value: Any) -> dict[str, Any] | None:
    """Return a sanitized Local Mode project record, or None when the record is malformed."""

    if not isinstance(value, dict):
        return None

    path = str(value.get("path") or "").strip()
    if not path:
        return None
    name = str(value.get("name") or Path(path).name).strip() or Path(path).name
    category = str(value.get("category") or "").strip()
    category_foldered = (
        value.get("category_foldered") is True
        if "category_foldered" in value
        else bool(category) and Path(path).parent.name == category
    )
    return {
        "path": path,
        "name": name,
        "category": category,
        "icon_path": clean_project_icon_path(value.get("icon_path"), path),
        "category_foldered": category_foldered,
    }


# De-duplicates sanitized project records by absolute path so every dropdown option has one metadata owner.
def clean_local_project_list(value: Any) -> list[dict[str, Any]]:
    """Return valid Local Mode project records sorted by their display names."""

    if not isinstance(value, list):
        return []

    records = []
    seen_paths = set()
    for raw_record in value:
        record = clean_local_project_record(raw_record)
        if record and record["path"] not in seen_paths:
            records.append(record)
            seen_paths.add(record["path"])
    return sorted(records, key=lambda item: item["name"].lower())


# Builds the minimal owner-only record written when a project is created, selected, renamed, or recategorized.
def project_record(
    project_path: Path,
    category: str = "",
    icon_path: str = "",
    category_foldered: bool = False,
) -> dict[str, Any]:
    """Return registry metadata for one Local Mode project folder."""

    resolved_path = project_path.resolve()
    return {
        "path": str(resolved_path),
        "name": resolved_path.name,
        "category": str(category or "").strip(),
        "icon_path": clean_project_icon_path(icon_path, resolved_path),
        "category_foldered": category_foldered is True,
    }
