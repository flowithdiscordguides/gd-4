"""Validation and complete tree building for project-scoped Sync Ignore rules."""

from __future__ import annotations

# Filesystem traversal uses non-following stat calls so selected links cannot escape a version.
import os
from pathlib import Path
import stat
from typing import Any

# Local project helpers establish the saved project and physical version ownership boundary.
from gitdesk.errors import AppError
from gitdesk.localfeatures import feature_path_for_version
from gitdesk.localproject_records import clean_local_project_list
from gitdesk.localversions import normalize_version_directory, size_label
from gitdesk.syncignore_store import clean_ignore_paths


# Resolves a selected version to exactly one saved Local project.
def project_for_version(settings: dict[str, Any], version_path_value: Any) -> tuple[dict[str, Any], Path]:
    """Return the owning saved project and validated version directory."""

    version_path = normalize_version_directory(str(version_path_value or settings.get("active_local_version") or ""))
    for project in clean_local_project_list(settings.get("local_projects")):
        project_path = Path(project["path"]).expanduser().resolve()
        try:
            feature_path_for_version(project_path, str(version_path))
            return project, version_path
        except AppError:
            continue
    raise AppError("The selected version does not belong to a saved Local project.", "SYNC_IGNORE_VERSION_INVALID")


# Returns whether one relative path is covered by an exact file rule or parent directory rule.
def path_is_ignored(relative_path: str, ignored_paths: set[str]) -> bool:
    """Return True when relative_path is selected directly or through an ignored parent."""

    return any(
        relative_path == ignored_path or relative_path.startswith(f"{ignored_path}/")
        for ignored_path in ignored_paths
    )


# Converts one non-followed directory entry into frontend-safe tree metadata.
def tree_node(
    entry: os.DirEntry[str],
    root: Path,
    ignored_paths: set[str],
) -> dict[str, Any]:
    """Return one selectable file or directory node rooted at root without reading its children."""

    entry_path = Path(entry.path)
    relative_path = entry_path.relative_to(root).as_posix()
    try:
        entry_stat = entry.stat(follow_symlinks=False)
    except OSError as error:
        raise AppError("A Sync Ignore entry could not be inspected.", "SYNC_IGNORE_TREE_READ_FAILED") from error
    is_directory = stat.S_ISDIR(entry_stat.st_mode)
    is_link = stat.S_ISLNK(entry_stat.st_mode)
    node = {
        "name": entry.name,
        "path": relative_path,
        "type": "directory" if is_directory else "file",
        "checked": path_is_ignored(relative_path, ignored_paths),
        "size_label": "" if is_directory else size_label(entry_stat.st_size),
        "children": [],
        "link": is_link,
    }
    return node


# Reads one directory in stable folder-first order without following symlinked directories.
def directory_entries(directory: Path) -> list[os.DirEntry[str]]:
    """Return every non-Git directory entry in deterministic display order."""

    try:
        entries = list(os.scandir(directory))
    except OSError as error:
        raise AppError("The selected version could not be read.", "SYNC_IGNORE_TREE_READ_FAILED") from error
    entries.sort(key=lambda entry: (not entry.is_dir(follow_symlinks=False), entry.name.casefold()))
    return [entry for entry in entries if entry.name != ".git"]


# Builds every nested child iteratively so deep physical trees do not hit Python's recursion limit.
def tree_children(directory: Path, root: Path, ignored_paths: set[str]) -> list[dict[str, Any]]:
    """Return the complete selectable child tree for directory."""

    entries = directory_entries(directory)
    nodes = [tree_node(entry, root, ignored_paths) for entry in entries]
    pending = [
        (Path(entry.path), node)
        for entry, node in zip(entries, nodes)
        if node["type"] == "directory" and not node["link"]
    ]
    # Each real directory is scanned once; symlinked directories remain selectable leaf nodes.
    while pending:
        child_directory, parent_node = pending.pop()
        child_entries = directory_entries(child_directory)
        child_nodes = [tree_node(entry, root, ignored_paths) for entry in child_entries]
        parent_node["children"] = child_nodes
        pending.extend(
            (Path(entry.path), node)
            for entry, node in zip(child_entries, child_nodes)
            if node["type"] == "directory" and not node["link"]
        )
    return nodes


# Builds the exact modal state for one selected Local version.
def sync_ignore_state(
    settings: dict[str, Any],
    version_path_value: Any,
    ignored_paths: list[str],
) -> dict[str, Any]:
    """Return project identity, saved rules, and the complete current-version tree."""

    project, version_path = project_for_version(settings, version_path_value)
    cleaned_paths = clean_ignore_paths(ignored_paths)
    children = tree_children(version_path, version_path, set(cleaned_paths))
    return {
        "project": {"name": project["name"], "path": project["path"]},
        "version": {"name": version_path.name, "path": str(version_path)},
        "ignored_paths": cleaned_paths,
        "tree": {
            "root": str(version_path),
            "children": children,
        },
    }


# Confirms every selected rule still names an entry inside the current version.
def validate_selected_paths(version_path: Path, ignored_paths: Any) -> list[str]:
    """Return clean rules whose current-version targets exist without following links."""

    cleaned_paths = clean_ignore_paths(ignored_paths)
    for relative_path in cleaned_paths:
        candidate = version_path / Path(*relative_path.split("/"))
        try:
            candidate.relative_to(version_path)
            exists = candidate.exists() or candidate.is_symlink()
        except (OSError, ValueError):
            exists = False
        if not exists:
            raise AppError(
                f"Sync Ignore selection no longer exists: {relative_path}",
                "SYNC_IGNORE_PATH_MISSING",
            )
    return cleaned_paths
