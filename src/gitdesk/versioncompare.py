"""Folder-to-folder local version comparison and copy helpers."""

from __future__ import annotations

import filecmp
from pathlib import Path, PurePosixPath
import shutil
from typing import Any

from gitdesk.errors import AppError
from gitdesk.localversions import PRUNED_TREE_NAMES, normalize_version_directory, size_label


# Diff payloads are bounded so comparing a large project does not freeze the WebView.
MAX_COMPARE_FILES = 2500


# Validates a version-relative path before copying files between local versions.
def clean_compare_path(value: str) -> str:
    """Return a safe relative path for version compare and copy operations."""

    normalized = str(value or "").replace("\\", "/").strip().strip("/")
    parts = PurePosixPath(normalized).parts
    drive_path = len(normalized) >= 2 and normalized[1] == ":"
    if not normalized or normalized == "." or normalized.startswith("/") or drive_path or ".." in parts:
        raise AppError("Compared file paths must stay inside version folders.", "VERSION_COMPARE_PATH_INVALID")
    return normalized


# Returns whether a filesystem entry should be excluded from compare results.
def should_skip_path(path: Path) -> bool:
    """Return True when a generated or dependency folder should not be compared."""

    return any(part in PRUNED_TREE_NAMES for part in path.parts)


# Builds a relative-file map for one version folder.
def version_file_map(root: Path) -> dict[str, Path]:
    """Return a map of relative file paths to absolute paths for one version folder."""

    files = {}
    for file_path in root.rglob("*"):
        relative = file_path.relative_to(root)
        if should_skip_path(relative) or not file_path.is_file() or file_path.is_symlink():
            continue
        files[relative.as_posix()] = file_path
        if len(files) >= MAX_COMPARE_FILES:
            break
    return files


# Returns the size label for an existing file path.
def file_size_label(path: Path | None) -> str:
    """Return a display size for a compared file."""

    if not path or not path.exists():
        return ""
    return size_label(path.stat().st_size)


# Compares file contents and returns a stable status label.
def compare_file_status(left_path: Path | None, right_path: Path | None) -> str:
    """Return added, deleted, modified, or unchanged for a compared file."""

    if left_path and not right_path:
        return "deleted"
    if right_path and not left_path:
        return "added"
    if left_path and right_path and not filecmp.cmp(left_path, right_path, shallow=False):
        return "modified"
    return "unchanged"


# Builds one frontend row for a compared file.
def compare_row(relative_path: str, left_path: Path | None, right_path: Path | None) -> dict[str, str]:
    """Return one display row for a version comparison."""

    status = compare_file_status(left_path, right_path)
    return {
        "path": relative_path,
        "status": status,
        "left_size": file_size_label(left_path),
        "right_size": file_size_label(right_path),
    }


# Compares two version folders without modifying either folder.
def compare_versions(left_path_value: str, right_path_value: str) -> dict[str, Any]:
    """Return changed-file rows comparing two local version folders."""

    left_root = normalize_version_directory(left_path_value)
    right_root = normalize_version_directory(right_path_value)
    left_files = version_file_map(left_root)
    right_files = version_file_map(right_root)
    all_paths = sorted(set(left_files) | set(right_files))
    rows = [
        compare_row(path, left_files.get(path), right_files.get(path))
        for path in all_paths
    ]
    visible_rows = [row for row in rows if row["status"] != "unchanged"]
    return {
        "left": str(left_root),
        "right": str(right_root),
        "files": visible_rows,
        "summary": {
            "added": sum(1 for row in visible_rows if row["status"] == "added"),
            "deleted": sum(1 for row in visible_rows if row["status"] == "deleted"),
            "modified": sum(1 for row in visible_rows if row["status"] == "modified"),
            "unchanged": sum(1 for row in rows if row["status"] == "unchanged"),
            "truncated": len(left_files) >= MAX_COMPARE_FILES or len(right_files) >= MAX_COMPARE_FILES,
        },
    }


# Copies one validated file or directory into the target version.
def copy_one_path(source_root: Path, target_root: Path, relative_path_value: str) -> None:
    """Copy one source path into a target version folder."""

    relative_path = clean_compare_path(relative_path_value)
    source_path = (source_root / relative_path).resolve()
    target_path = (target_root / relative_path).resolve()
    try:
        source_path.relative_to(source_root)
        target_path.relative_to(target_root)
    except ValueError as error:
        raise AppError("Copied version paths must stay inside version folders.", "VERSION_COPY_PATH_INVALID") from error
    if not source_path.exists():
        raise AppError("The selected source file does not exist.", "VERSION_COPY_SOURCE_MISSING")
    if source_path.is_dir():
        shutil.copytree(source_path, target_path, dirs_exist_ok=True, symlinks=False)
        return
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path, follow_symlinks=False)


# Copies selected files from one local version into another.
def copy_compared_files(source_path_value: str, target_path_value: str, paths: list[str]) -> dict[str, Any]:
    """Copy selected files from a source version into a target version."""

    if not paths:
        raise AppError("Select at least one compared file to copy.", "VERSION_COPY_EMPTY")
    source_root = normalize_version_directory(source_path_value)
    target_root = normalize_version_directory(target_path_value)
    copied = []
    for raw_path in paths:
        clean_path = clean_compare_path(raw_path)
        copy_one_path(source_root, target_root, clean_path)
        copied.append(clean_path)
    return {"source": str(source_root), "target": str(target_root), "copied": copied}
