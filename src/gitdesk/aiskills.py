"""Backward-compatible category storage for GitDesk Shared Resources."""

from __future__ import annotations

from pathlib import Path
import platform
import re
import shutil
import subprocess
import os
import sys
from typing import Any

from gitdesk.errors import AppError
from gitdesk.gitops import open_repository
from gitdesk.storage import app_data_path, source_checkout_root


# Shared Resource names remain category-compatible so existing saved selections need no migration.
CATEGORY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,63}$")

# macOS and editor-local metadata should never become part of a copied Shared Resource.
IGNORED_SKILL_FILE_NAMES = {".DS_Store", "settings.local.json"}

# Shared Resources use one neutral directory name in source, packaged, and per-user storage.
SHARED_RESOURCE_DIRECTORY_NAME = "Shared-Resources"


# Finds the project root only for read-only source assets.
def project_root() -> Path:
    """Return the application root that owns bundled Shared Resource assets."""

    checkout_root = source_checkout_root()
    if checkout_root is not None:
        return checkout_root
    bundle_root = str(getattr(sys, "_MEIPASS", "") or "").strip()
    return Path(bundle_root).resolve() if bundle_root else Path(__file__).resolve().parents[2]


# Returns the per-user editable Shared Resources folder for source and packaged runs.
def writable_categories_root(create: bool = False) -> Path:
    """Return the category folder where new user-created Shared Resources are written."""

    root = app_data_path() / SHARED_RESOURCE_DIRECTORY_NAME / "categories"
    if create:
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise AppError("Unable to prepare the Shared Resources folder.", "AI_SKILL_ROOT_FAILED") from error
    return root


# Returns the one read-only category folder supplied by source or a packaged build.
def bundled_categories_roots() -> list[Path]:
    """Return the existing read-only Shared Resource category folder."""

    bundle_root = str(getattr(sys, "_MEIPASS", "") or "").strip()
    candidates = []
    if bundle_root:
        candidates.append(Path(bundle_root) / SHARED_RESOURCE_DIRECTORY_NAME / "categories")
    elif source_checkout_root() is not None:
        candidates.append(project_root() / SHARED_RESOURCE_DIRECTORY_NAME / "categories")

    roots = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists() and resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return roots


# Preserves the singular helper for callers that need the bundled root.
def bundled_categories_root() -> Path | None:
    """Return the existing bundled category root, when available."""

    roots = bundled_categories_roots()
    return roots[0] if roots else None


# Returns every category root that should be listed or copied from.
def category_roots(create: bool = False) -> list[Path]:
    """Return writable and bundled category roots without duplicate paths."""

    roots = [writable_categories_root(create=create)]
    for bundled_root in bundled_categories_roots():
        if bundled_root not in roots:
            roots.append(bundled_root)
    return roots


# Returns the writable root for existing callers that create or open categories.
def categories_root(create: bool = False) -> Path:
    """Return the editable Shared Resources category root folder."""

    return writable_categories_root(create=create)


# Validates one category name before it becomes a directory name.
def clean_category_name(value: str) -> str:
    """Return a safe Shared Resource category folder name."""

    name = str(value or "").strip()
    if not name or name in {".", ".."}:
        raise AppError("Shared Resource name is required.", "AI_SKILL_CATEGORY_EMPTY")
    if "/" in name or "\\" in name or not CATEGORY_PATTERN.match(name):
        raise AppError("Shared Resource name contains invalid characters.", "AI_SKILL_CATEGORY_INVALID")
    return name


# Cleans a persisted category selection list without requiring folders to exist.
def clean_category_selection(value: Any) -> list[str]:
    """Return valid selected Shared Resource names."""

    if not isinstance(value, list):
        return []

    cleaned = []
    seen = set()
    for raw_name in value:
        try:
            name = clean_category_name(str(raw_name or ""))
        except AppError:
            continue
        if name not in seen:
            cleaned.append(name)
            seen.add(name)
    return cleaned


# Finds every source folder that contributes files for one category.
def category_source_paths(name_value: str) -> list[Path]:
    """Return matching category folders in copy order, with user files applied last."""

    name = clean_category_name(name_value)
    sources = []
    for root in reversed(category_roots(create=True)):
        path = root / name
        if path.exists() and path.is_dir():
            sources.append(path)
    return sources


# Converts category source folders to frontend-safe metadata.
def category_payload(name: str, source_paths: list[Path]) -> dict[str, Any]:
    """Return display metadata for one Shared Resource assembled from source folders."""

    relative_files = set()
    for path in source_paths:
        for item in path.rglob("*"):
            if item.is_file() and not item.is_symlink() and item.name not in IGNORED_SKILL_FILE_NAMES:
                relative_files.add(item.relative_to(path).as_posix())
    writable_path = writable_categories_root(create=True) / name
    return {
        "name": name,
        "path": str(writable_path if writable_path.exists() else source_paths[0]),
        "file_count": len(relative_files),
    }


# Lists all current Shared Resources from disk.
def list_categories() -> dict[str, Any]:
    """Return all Shared Resources from writable and bundled folders."""

    names = []
    for root in category_roots(create=True):
        try:
            category_paths = sorted(root.iterdir(), key=lambda item: item.name.lower())
        except OSError as error:
            raise AppError("Unable to read the Shared Resources folder.", "AI_SKILL_ROOT_READ_FAILED") from error
        for path in category_paths:
            # Invalid or duplicate folder names stay invisible so they can never become project destinations.
            if not path.is_dir() or path.name in names:
                continue
            try:
                names.append(clean_category_name(path.name))
            except AppError:
                continue
    categories = [category_payload(name, category_source_paths(name)) for name in sorted(names, key=str.lower)]
    return {
        "root": str(categories_root(create=True)),
        "categories": categories,
    }


# Creates a Shared Resource folder under the editable categories root.
def create_category(name_value: str) -> dict[str, Any]:
    """Create and return one Shared Resource folder."""

    name = clean_category_name(name_value)
    root = categories_root(create=True)
    path = (root / name).resolve()
    if path.parent != root:
        raise AppError("Shared Resource must stay inside the categories folder.", "AI_SKILL_CATEGORY_INVALID")
    path.mkdir(parents=True, exist_ok=True)
    return category_payload(name, category_source_paths(name))


# Opens an editable resource folder, materializing bundled content first when necessary.
def open_category(name_value: str) -> dict[str, Any]:
    """Open one editable Shared Resource folder in the platform file manager."""

    name = clean_category_name(name_value)
    source_paths = category_source_paths(name)
    if not source_paths:
        raise AppError("Shared Resource does not exist.", "AI_SKILL_CATEGORY_NOT_FOUND")
    path = categories_root(create=True) / name
    path.mkdir(parents=True, exist_ok=True)
    effective_files = {}
    # Later source roots override earlier bundled files, while existing writable files remain authoritative.
    for source_path in source_paths:
        for source_item in source_path.rglob("*"):
            if (
                source_item.name in IGNORED_SKILL_FILE_NAMES
                or source_item.is_symlink()
                or not source_item.is_file()
            ):
                continue
            effective_files[source_item.relative_to(source_path)] = source_item
    for relative_path, source_item in effective_files.items():
        target_item = path / relative_path
        if source_item == target_item or target_item.exists():
            continue
        target_item.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_item, target_item)

    if platform.system() == "Darwin":
        subprocess.Popen(["open", str(path)])
    elif platform.system() == "Windows":
        os.startfile(str(path))
    else:
        subprocess.Popen(["xdg-open", str(path)])
    return category_payload(name, category_source_paths(name))


# Returns a safe repository destination for one Shared Resource file.
def repository_skill_target(repo_root: Path, relative_path: Path) -> Path:
    """Return the target path for a category file copied into the repository root."""

    if ".git" in relative_path.parts:
        raise AppError("Shared Resource files cannot target the .git folder.", "AI_SKILL_FILE_INVALID")

    target_path = (repo_root / relative_path).resolve()
    try:
        target_path.relative_to(repo_root)
    except ValueError as error:
        raise AppError("Shared Resource files must stay inside the repository.", "AI_SKILL_FILE_INVALID") from error
    return target_path


# Returns a safe destination for one Shared Resource file copied into a plain local folder.
def folder_skill_target(destination_root: Path, relative_path: Path) -> Path:
    """Return the target path for a category file copied into a non-Git folder."""

    if ".git" in relative_path.parts:
        raise AppError("Shared Resource files cannot target the .git folder.", "AI_SKILL_FILE_INVALID")

    target_path = (destination_root / relative_path).resolve()
    try:
        target_path.relative_to(destination_root)
    except ValueError as error:
        raise AppError(
            "Shared Resource files must stay inside the destination folder.",
            "AI_SKILL_FILE_INVALID",
        ) from error
    return target_path


# Copies a validated category folder into a validated destination root.
def copy_category_to_folder(name_value: str, destination_root: Path) -> dict[str, Any]:
    """Copy one Shared Resource into a destination folder and return copy metadata."""

    name = clean_category_name(name_value)
    source_paths = category_source_paths(name)
    if not source_paths:
        raise AppError("Shared Resource does not exist.", "AI_SKILL_CATEGORY_NOT_FOUND")

    copied_relative_paths = set()
    for source_path in source_paths:
        for source_item in source_path.rglob("*"):
            if source_item.name in IGNORED_SKILL_FILE_NAMES or source_item.is_symlink() or not source_item.is_file():
                continue
            relative_path = source_item.relative_to(source_path)
            target_item = folder_skill_target(destination_root, relative_path)
            target_item.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_item, target_item)
            copied_relative_paths.add(relative_path.as_posix())
    copied_files = len(copied_relative_paths)

    return {
        "category": name,
        "destination": str(destination_root),
        "file_count": copied_files,
    }


# Copies the files from one category directly into the active repository root.
def add_category_to_repository(name_value: str, repository_path_value: str) -> dict[str, Any]:
    """Copy one Shared Resource's files into the selected repository."""

    repo = open_repository(repository_path_value)
    repo_root = Path(repo.working_tree_dir or repository_path_value).resolve()
    return copy_category_to_repository_root(name_value, repo_root)


# Copies one Shared Resource into a repository root after Git validation has resolved the root.
def copy_category_to_repository_root(name_value: str, repo_root: Path) -> dict[str, Any]:
    """Copy one Shared Resource into an already-resolved repository root."""

    result = copy_category_to_folder(name_value, repo_root)
    return {
        "category": result["category"],
        "destination": result["destination"],
        "file_count": result["file_count"],
    }


# Copies one Shared Resource into a normal local folder for Local Mode project creation.
def add_category_to_folder(name_value: str, folder_path_value: str) -> dict[str, Any]:
    """Copy one Shared Resource into a plain local folder."""

    destination_root = Path(str(folder_path_value or "")).expanduser().resolve()
    if not destination_root.exists() or not destination_root.is_dir():
        raise AppError("Shared Resources destination folder does not exist.", "AI_SKILL_DESTINATION_INVALID")
    return copy_category_to_folder(name_value, destination_root)
