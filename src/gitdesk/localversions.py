"""Physical local version folder operations for GitDesk Local Mode."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any

from gitdesk.errors import AppError
from gitdesk.nativeopen import open_folder, open_in_editor
from gitdesk import sharedresources


# Version folders follow Xander's vN plus optional label pattern, such as v1 calculator or v2 dark theme.
VERSION_PATTERN = re.compile(r"^v(?P<number>[1-9][0-9]*)(?:\s+(?P<label>.+))?$")

# Version labels become part of a folder name, so separators and control-like names are rejected.
VERSION_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,95}$")

# Large generated folders are shown as selectable rows without recursively expanding every child file.
PRUNED_TREE_NAMES = {
    ".git",
    ".cache",
    ".mypy_cache",
    ".next",
    ".nuxt",
    ".parcel-cache",
    ".pytest_cache",
    ".ruff_cache",
    ".turbo",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "env",
    "node_modules",
    "target",
    "venv",
}

# These paths are preselected because moving them forward saves space without removing source code.
SUGGESTED_MOVE_NAMES = (PRUNED_TREE_NAMES - {".git"}) | {".venv"}

# Tree payloads are bounded so a huge project folder cannot freeze the WebView while rendering checkboxes.
MAX_TREE_NODES = 1500


# Validates the optional descriptive part of a version folder name.
def clean_version_label(value: str) -> str:
    """Return a safe version label, or an empty string when no label was entered."""

    label = str(value or "").strip()
    if not label:
        return ""
    if "/" in label or "\\" in label or label in {".", ".."} or not VERSION_LABEL_PATTERN.match(label):
        raise AppError("Version label contains invalid characters.", "LOCAL_VERSION_LABEL_INVALID")
    return label


# Finds the numeric version prefix from folder names such as v1 and v2 add auth.
def version_number(folder_name: str) -> int:
    """Return the local version number encoded in a folder name, or zero when it is not a version."""

    match = VERSION_PATTERN.match(folder_name)
    return int(match.group("number")) if match else 0


# Normalizes one relative cleanup path before it is saved or used in a move operation.
def clean_cleanup_path(value: Any) -> str:
    """Return a safe version-relative cleanup path."""

    normalized = str(value or "").replace("\\", "/").strip().strip("/")
    parts = PurePosixPath(normalized).parts
    drive_path = len(normalized) >= 2 and normalized[1] == ":"
    if not normalized or normalized == "." or normalized.startswith("/") or drive_path or ".." in parts:
        raise AppError("Cleanup paths must stay inside the version folder.", "LOCAL_CLEANUP_PATH_INVALID")
    return normalized


# Sanitizes cleanup path selections while keeping parent selections from duplicating child work.
def clean_cleanup_paths(value: Any) -> list[str]:
    """Return a de-duplicated list of safe cleanup paths."""

    if not isinstance(value, list):
        return []

    cleaned = []
    for raw_path in value:
        try:
            path = clean_cleanup_path(raw_path)
        except AppError:
            continue
        if path not in cleaned:
            cleaned.append(path)
    return reduce_cleanup_paths(cleaned)


# Keeps only topmost selected paths so moving a folder also covers its selected children.
def reduce_cleanup_paths(paths: list[str]) -> list[str]:
    """Return cleanup paths with children removed when a parent is already selected."""

    reduced = []
    for path in sorted(paths, key=lambda item: (item.count("/"), item)):
        if not any(path == existing or path.startswith(f"{existing}/") for existing in reduced):
            reduced.append(path.rstrip("/"))
    return reduced


# Resolves a user-supplied version path and verifies that it exists.
def normalize_version_directory(path_value: str) -> Path:
    """Return a resolved existing local version directory."""

    cleaned_path = str(path_value or "").strip()
    if not cleaned_path:
        raise AppError("Version folder path is required.", "LOCAL_VERSION_EMPTY")

    folder_path = Path(cleaned_path).expanduser().resolve()
    if not folder_path.exists() or not folder_path.is_dir():
        raise AppError("Version folder path must point to an existing directory.", "LOCAL_VERSION_INVALID")
    return folder_path


# Resolves a project or feature folder that can contain vN version folders.
def normalize_versions_parent(path_value: str, empty_code: str, invalid_code: str) -> Path:
    """Return a resolved existing directory that can contain local versions."""

    cleaned_path = str(path_value or "").strip()
    if not cleaned_path:
        raise AppError("Version parent folder path is required.", empty_code)

    folder_path = Path(cleaned_path).expanduser().resolve()
    if not folder_path.exists() or not folder_path.is_dir():
        raise AppError("Version parent folder path must point to an existing directory.", invalid_code)
    return folder_path


# Lists vN folders directly under a project or feature folder.
def list_versions(path_value: str, empty_code: str, invalid_code: str) -> list[dict[str, Any]]:
    """Return sorted local version folders directly under one parent folder."""

    parent_path = normalize_versions_parent(path_value, empty_code, invalid_code)
    versions = []
    for child in parent_path.iterdir():
        number = version_number(child.name)
        if number and child.is_dir():
            versions.append({"name": child.name, "number": number, "path": str(child.resolve())})
    return sorted(versions, key=lambda item: item["number"])


# Creates the next version folder name from existing vN folders and a user label.
def next_version_path(source_path: Path, label_value: str) -> Path:
    """Return an unused destination path for the next local version."""

    project_path = source_path.parent
    next_number = max([version_number(item.name) for item in project_path.iterdir() if item.is_dir()] or [0]) + 1
    label = clean_version_label(label_value)
    folder_name = f"v{next_number} {label}" if label else f"v{next_number}"
    target_path = (project_path / folder_name).resolve()
    if target_path.exists():
        raise AppError("The next version folder already exists.", "LOCAL_VERSION_EXISTS")
    return target_path


# Returns whether a relative path should be moved instead of copied.
def should_move(relative_path: str, move_paths: set[str]) -> bool:
    """Return True when a path is selected for move-forward cleanup."""

    return relative_path in move_paths or any(relative_path.startswith(f"{path}/") for path in move_paths)


# Copies one file-system item while skipping paths that will be moved after the copy phase.
def copy_item_excluding_moves(source_root: Path, source_item: Path, target_item: Path, move_paths: set[str]) -> None:
    """Copy source content into the target version while excluding selected move paths."""

    relative_path = source_item.relative_to(source_root).as_posix()
    if should_move(relative_path, move_paths):
        return
    if source_item.is_symlink() or source_item.is_file():
        target_item.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_item, target_item, follow_symlinks=False)
        return
    if source_item.is_dir():
        target_item.mkdir(parents=True, exist_ok=True)
        for child in source_item.iterdir():
            copy_item_excluding_moves(source_root, child, target_item / child.name, move_paths)


# Moves selected paths from the source version into the already-created target version.
def move_selected_paths(source_root: Path, target_root: Path, move_paths: list[str]) -> None:
    """Move selected cleanup paths into the new version after copying other content succeeds."""

    for relative_path in move_paths:
        source_path = (source_root / relative_path).resolve()
        target_path = (target_root / relative_path).resolve()
        try:
            source_path.relative_to(source_root)
            target_path.relative_to(target_root)
        except ValueError as error:
            raise AppError("Cleanup paths must stay inside version folders.", "LOCAL_CLEANUP_PATH_INVALID") from error
        if not source_path.exists() and not source_path.is_symlink():
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), str(target_path))


# Duplicates one version into the next vN folder using copy for unchecked paths and move for checked paths.
def duplicate_local_version(source_path_value: str, label_value: str, move_path_values: list[str]) -> dict[str, Any]:
    """Create the next physical local version folder from a source version."""

    source_path = normalize_version_directory(source_path_value)
    target_path = next_version_path(source_path, label_value)
    move_paths = clean_cleanup_paths(move_path_values)
    move_path_set = set(move_paths)
    target_path.mkdir(parents=False)

    for child in source_path.iterdir():
        copy_item_excluding_moves(source_path, child, target_path / child.name, move_path_set)
    move_selected_paths(source_path, target_path, move_paths)
    sharedresources.clone_installations(str(source_path), str(target_path))

    return {
        "source": str(source_path),
        "target": str(target_path),
        "moved_paths": move_paths,
        "copied_mode": "unchecked",
        "moved_mode": "checked",
    }


# Renames legacy bare v1 folders so editor windows show the project name.
def rename_bare_v1_to_project(source_path_value: str, project_name_value: str) -> dict[str, str]:
    """Rename a selected v1 folder to v1 plus the owning project name."""

    source_path = normalize_version_directory(source_path_value)
    if source_path.name != "v1":
        raise AppError("Only a folder named exactly v1 can use this rename action.", "LOCAL_VERSION_RENAME_INVALID")

    project_label = clean_version_label(project_name_value)
    if not project_label:
        raise AppError("Project name is required before v1 can be renamed.", "LOCAL_PROJECT_NAME_EMPTY")
    target_path = source_path.with_name(f"v1 {project_label}").resolve()
    if target_path.exists():
        raise AppError("The named v1 folder already exists.", "LOCAL_VERSION_EXISTS")

    source_path.rename(target_path)
    return {"source": str(source_path), "target": str(target_path), "name": target_path.name}


# Converts byte counts into compact labels for the cleanup preview.
def size_label(byte_count: int) -> str:
    """Return a compact human-readable size label."""

    value = float(byte_count)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(byte_count)} B"


# Builds one cleanup tree node while pruning known dependency/cache directories.
def tree_node(path: Path, root: Path, saved_paths: set[str], counter: dict[str, int]) -> dict[str, Any]:
    """Return a frontend cleanup tree node for one file or directory."""

    counter["count"] += 1
    relative_path = path.relative_to(root).as_posix()
    is_directory = path.is_dir() and not path.is_symlink()
    suggested = path.name in SUGGESTED_MOVE_NAMES or relative_path in saved_paths
    node = {
        "name": path.name,
        "path": relative_path,
        "type": "directory" if is_directory else "file",
        "suggested": suggested,
        "checked": suggested,
        "size_label": size_label(path.stat().st_size) if path.exists() and not is_directory else "",
        "children": [],
        "pruned": is_directory and path.name in PRUNED_TREE_NAMES,
    }
    if is_directory and not node["pruned"] and counter["count"] < MAX_TREE_NODES:
        node["children"] = tree_children(path, root, saved_paths, counter)
    return node


# Builds bounded child nodes so nested folders cannot exceed the cleanup tree cap.
def tree_children(path: Path, root: Path, saved_paths: set[str], counter: dict[str, int]) -> list[dict[str, Any]]:
    """Return child tree nodes until the global node cap is reached."""

    nodes = []
    children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    for child in children:
        if counter["count"] >= MAX_TREE_NODES:
            break
        nodes.append(tree_node(child, root, saved_paths, counter))
    return nodes


# Scans a version folder into a bounded checkbox tree for move-forward cleanup selection.
def local_version_tree(source_path_value: str, saved_cleanup_paths: list[str]) -> dict[str, Any]:
    """Return a selectable file tree for a local version folder."""

    source_path = normalize_version_directory(source_path_value)
    saved_paths = set(clean_cleanup_paths(saved_cleanup_paths))
    counter = {"count": 0}
    children = tree_children(source_path, source_path, saved_paths, counter)
    return {"root": str(source_path), "children": children, "truncated": counter["count"] >= MAX_TREE_NODES}


# Opens a normal local folder without requiring it to be a Git repository.
def open_local_folder(path_value: str) -> dict[str, str]:
    """Open a local version folder in the platform file manager."""

    folder_path = normalize_version_directory(path_value)
    return open_folder(str(folder_path))


# Opens a normal local folder in the selected code editor when its launcher is available.
def open_local_vscode(path_value: str, editor_preferences: dict[str, str] | None = None) -> dict[str, str]:
    """Open a local version folder in the user's selected code editor."""

    folder_path = normalize_version_directory(path_value)
    return open_in_editor(str(folder_path), editor_preferences)
