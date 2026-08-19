"""Path-prefix remapping for Local Mode settings that identify moved folders."""

from __future__ import annotations

from pathlib import Path
from typing import Any


# Rewrites a saved absolute path when it points at or inside a moved folder.
def remap_path_prefix(path_value: Any, old_root: Path, new_root: Path) -> str:
    """Return a path moved from old_root to new_root, or the original string when unrelated."""

    raw_path = str(path_value or "").strip()
    if not raw_path:
        return ""
    try:
        path = Path(raw_path).expanduser().resolve()
        relative_path = path.relative_to(old_root)
    except (OSError, ValueError):
        return raw_path
    return str((new_root / relative_path).resolve())


# Detects whether nested metadata still contains one path root or any of its descendants.
def metadata_uses_path_prefix(value: Any, root: Path) -> bool:
    """Return whether a nested settings value contains a path below root."""

    if isinstance(value, dict):
        return any(
            metadata_uses_path_prefix(key, root) or metadata_uses_path_prefix(item, root)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(metadata_uses_path_prefix(item, root) for item in value)
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        Path(value).expanduser().resolve().relative_to(root)
    except (OSError, ValueError):
        return False
    return True


# Updates saved repository records when a Local Mode project root contains a Git-enabled version.
def remap_repository_settings(settings: dict[str, Any], old_root: Path, new_root: Path) -> dict[str, Any]:
    """Return managed repository path updates for paths affected by a folder move."""

    repositories = {}
    for login, records in (settings.get("managed_repositories") or {}).items():
        repositories[str(login)] = [
            {**record, "path": remap_path_prefix(record.get("path"), old_root, new_root)}
            for record in records
            if isinstance(record, dict)
        ]
    active_paths = {
        str(login): remap_path_prefix(path, old_root, new_root)
        for login, path in (settings.get("active_repository_by_account") or {}).items()
    }
    return {
        "repository_path": remap_path_prefix(settings.get("repository_path"), old_root, new_root),
        "managed_repositories": repositories,
        "active_repository_by_account": active_paths,
    }


# Updates Local Mode permission metadata whose keys and values identify the moved project root.
def remap_permission_grants(settings: dict[str, Any], old_root: Path, new_root: Path) -> dict[str, Any]:
    """Return permission grants with every path under old_root moved to new_root."""

    grants = {}
    for raw_path, raw_grant in (settings.get("local_permission_grants") or {}).items():
        if not isinstance(raw_grant, dict):
            continue
        next_path = remap_path_prefix(raw_path, old_root, new_root)
        grants[next_path] = {
            **raw_grant,
            "project_path": remap_path_prefix(raw_grant.get("project_path"), old_root, new_root),
            "granted_path": remap_path_prefix(raw_grant.get("granted_path"), old_root, new_root),
        }
    return grants
