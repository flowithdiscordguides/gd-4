"""Local project and physical folder-version operations for GitDesk."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from gitdesk import localfeatures
from gitdesk import sharedresources
from gitdesk.categorynames import CATEGORY_CONTAINER_NAME, clean_category_name
from gitdesk.errors import AppError
from gitdesk.localpathremap import remap_path_prefix, remap_permission_grants, remap_repository_settings
from gitdesk.localproject_records import clean_local_project_list, project_record
from gitdesk.localproject_state import (
    clean_workspace_mode,
    local_project_selection_state,
    local_project_selection_update,
    local_projects_state,
    selection_fields,
)

# Local project folders must be plain child names, never paths or hidden/system folder names.
LOCAL_PROJECT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,79}$")

# Parent-folder favorites are capped so the create-project picker stays compact.
MAX_PARENT_FAVORITES = 12


# Validates the folder name used when creating a new local project.
def clean_local_project_name(value: str) -> str:
    """Return a safe local project folder name."""

    name = str(value or "").strip()
    if not name or name in {".", ".."}:
        raise AppError("Local project name is required.", "LOCAL_PROJECT_NAME_EMPTY")
    if "/" in name or "\\" in name or name.startswith(".") or not LOCAL_PROJECT_PATTERN.match(name):
        raise AppError("Local project name contains invalid characters.", "LOCAL_PROJECT_NAME_INVALID")
    return name


# Cleans saved parent-folder favorites without requiring disconnected drives to be mounted.
def clean_local_parent_favorites(value: Any) -> list[str]:
    """Return de-duplicated local parent-folder favorite paths."""

    if not isinstance(value, list):
        return []

    favorites = []
    seen_paths = set()
    for raw_path in value:
        path = str(raw_path or "").strip()
        if path and path not in seen_paths:
            favorites.append(path)
            seen_paths.add(path)
    return favorites[:MAX_PARENT_FAVORITES]


# Resolves a user-supplied folder path and verifies that it exists.
def normalize_existing_directory(path_value: str, empty_code: str, invalid_code: str) -> Path:
    """Return a resolved existing directory for local project operations."""

    cleaned_path = str(path_value or "").strip()
    if not cleaned_path:
        raise AppError("Folder path is required.", empty_code)

    folder_path = Path(cleaned_path).expanduser().resolve()
    if not folder_path.exists() or not folder_path.is_dir():
        raise AppError("Folder path must point to an existing directory.", invalid_code)
    return folder_path


# Updates every non-secret setting that stores a local project, feature, version, or repository path.
def remap_settings_paths(settings: dict[str, Any], old_root: Path, new_root: Path) -> dict[str, Any]:
    """Return settings updates after a folder has moved from old_root to new_root."""

    projects = []
    for record in clean_local_project_list(settings.get("local_projects")):
        next_path = remap_path_prefix(record["path"], old_root, new_root)
        next_icon_path = remap_path_prefix(record.get("icon_path"), old_root, new_root)
        projects.append(project_record(
            Path(next_path),
            record.get("category", ""),
            next_icon_path,
            record.get("category_foldered") is True,
        ))
    statuses = {
        remap_path_prefix(path, old_root, new_root): status
        for path, status in (settings.get("local_version_statuses") or {}).items()
    }
    timeline = []
    for event in settings.get("project_timeline") or []:
        if isinstance(event, dict):
            timeline.append({
                **event,
                "project_path": remap_path_prefix(event.get("project_path"), old_root, new_root),
                "feature_path": remap_path_prefix(event.get("feature_path"), old_root, new_root),
                "version_path": remap_path_prefix(event.get("version_path"), old_root, new_root),
            })
    updates = remap_repository_settings(settings, old_root, new_root)
    updates.update({
        "workspace_mode": "local",
        "local_projects": projects,
        "active_local_project": remap_path_prefix(settings.get("active_local_project"), old_root, new_root),
        "active_local_feature": remap_path_prefix(settings.get("active_local_feature"), old_root, new_root),
        "active_local_version": remap_path_prefix(settings.get("active_local_version"), old_root, new_root),
        "local_permission_grants": remap_permission_grants(settings, old_root, new_root),
        "local_version_statuses": statuses,
        "project_timeline": timeline,
    })
    return updates


# Renames a selected project folder and prepares the matching persisted path updates.
def rename_local_project(settings: dict[str, Any], project_path_value: str, name_value: str) -> dict[str, Any]:
    """Rename one local project folder and return settings updates for the new path."""

    old_path = normalize_existing_directory(
        project_path_value,
        "LOCAL_PROJECT_PATH_EMPTY",
        "LOCAL_PROJECT_PATH_INVALID",
    )
    new_path = (old_path.parent / clean_local_project_name(name_value)).resolve()
    if new_path == old_path:
        return {
            "source": str(old_path),
            "target": str(new_path),
            "updates": remap_settings_paths(settings, old_path, new_path),
        }
    if new_path.exists():
        raise AppError("A project folder with that name already exists.", "LOCAL_PROJECT_EXISTS")

    old_path.rename(new_path)
    updates = remap_settings_paths(settings, old_path, new_path)
    if not any(record["path"] == str(new_path) for record in clean_local_project_list(updates["local_projects"])):
        updates["local_projects"].append(project_record(new_path))
    return {"source": str(old_path), "target": str(new_path), "updates": updates}


# Adds or refreshes a local project plus active feature/version in settings.
def local_project_settings_update(
    settings: dict[str, Any],
    project_path_value: str,
    feature_path_value: str = "",
    version_path_value: str = "",
    category: str = "",
    category_foldered: bool | None = None,
) -> dict[str, Any]:
    """Return settings updates for the active local project, feature, and version."""

    project_path = normalize_existing_directory(
        project_path_value,
        "LOCAL_PROJECT_PATH_EMPTY",
        "LOCAL_PROJECT_PATH_INVALID",
    )
    projects = [
        record for record in clean_local_project_list(settings.get("local_projects"))
        if record["path"] != str(project_path)
    ]
    existing_records = clean_local_project_list(settings.get("local_projects"))
    existing = next((record for record in existing_records if record["path"] == str(project_path)), None)
    existing_category = existing.get("category", "") if existing else ""
    existing_icon_path = existing.get("icon_path", "") if existing else ""
    existing_category_foldered = existing.get("category_foldered") is True if existing else False
    saved_category = str(category or existing_category).strip()
    saved_category_foldered = (
        existing_category_foldered
        if category_foldered is None
        else category_foldered is True
    )
    projects.append(project_record(
        project_path,
        saved_category,
        existing_icon_path,
        saved_category_foldered,
    ))
    projects.sort(key=lambda item: item["name"].lower())
    active_feature = ""
    active_version = ""
    if version_path_value:
        inferred_feature = localfeatures.feature_path_for_version(project_path, version_path_value)
        feature_path = (
            localfeatures.normalize_feature_directory(project_path, feature_path_value)
            if feature_path_value else inferred_feature
        )
        version_path = localfeatures.validate_version_for_feature(project_path, feature_path, version_path_value)
        active_feature = str(feature_path)
        active_version = str(version_path)
    elif feature_path_value:
        feature_path = localfeatures.normalize_feature_directory(project_path, feature_path_value)
        active_feature = str(feature_path)
    return {
        "workspace_mode": "local",
        "local_projects": projects,
        "active_local_project": str(project_path),
        "active_local_feature": active_feature,
        "active_local_version": active_version,
    }


# Removes one local project from the app registry without deleting its folder.
def remove_local_project_settings(settings: dict[str, Any], project_path_value: str) -> dict[str, Any]:
    """Return settings updates that remove one saved local project record."""

    project_path = str(project_path_value or "").strip()
    projects = [
        record
        for record in clean_local_project_list(settings.get("local_projects"))
        if record["path"] != project_path
    ]
    active_project = str(settings.get("active_local_project") or "")
    if active_project == project_path:
        active_project = ""
    updates = {"local_projects": projects, "active_local_project": active_project}
    if not active_project:
        updates.update({"active_local_feature": "", "active_local_version": ""})
    return updates


# Updates a local project's category label while preserving the saved path and active selection.
def local_project_category_update(settings: dict[str, Any], project_path_value: str, category: str) -> dict[str, Any]:
    """Return settings updates that assign a category to one local project record."""

    project_path = str(project_path_value or "").strip()
    projects = []
    for record in clean_local_project_list(settings.get("local_projects")):
        if record["path"] == project_path:
            saved_category = str(category or "").strip()
            category_foldered = (
                record.get("category_foldered") is True
                or bool(saved_category) and Path(record["path"]).parent.name == saved_category
            )
            record = {
                **record,
                "category": saved_category,
                "category_foldered": category_foldered,
            }
        projects.append(record)
    return {"local_projects": projects}


# Adds a validated parent folder to the front of the quick-access favorite list.
def local_parent_favorite_update(settings: dict[str, Any], parent_path_value: str) -> dict[str, Any]:
    """Return settings updates that save one local project parent folder favorite."""

    parent_path = normalize_existing_directory(parent_path_value, "LOCAL_PARENT_EMPTY", "LOCAL_PARENT_INVALID")
    favorite_path = str(parent_path)
    favorites = [
        path
        for path in clean_local_parent_favorites(settings.get("local_parent_favorites"))
        if path != favorite_path
    ]
    return {"local_parent_favorites": [favorite_path] + favorites[:MAX_PARENT_FAVORITES - 1]}


# Creates a new project folder and its ordered init/v1 feature version folder.
def create_local_project(
    parent_path_value: str,
    name_value: str,
    resources: list[str],
    category: str = "",
    create_category_folder: bool = False,
) -> dict[str, Any]:
    """Create a local project with a 01 init/v1 project-name folder and optional starter files."""

    parent_path = normalize_existing_directory(parent_path_value, "LOCAL_PARENT_EMPTY", "LOCAL_PARENT_INVALID")
    resources = sharedresources.validate_resource_selection(resources)
    category = clean_category_name(category)
    project_parent = parent_path
    category_foldered = create_category_folder is True
    if category_foldered:
        if not category:
            raise AppError(
                "Choose a category before creating this project.",
                "LOCAL_PROJECT_CATEGORY_REQUIRED",
            )
        raw_category_root = parent_path / CATEGORY_CONTAINER_NAME
        if raw_category_root.is_symlink():
            raise AppError("The categories folder cannot be a symbolic link.", "LOCAL_PROJECT_CATEGORY_PATH_INVALID")
        category_root = raw_category_root.resolve()
        if category_root.parent != parent_path:
            raise AppError(
                "The categories folder must stay inside the selected parent.",
                "LOCAL_PROJECT_CATEGORY_PATH_INVALID",
            )
        if category_root.exists() and not category_root.is_dir():
            raise AppError(
                "The categories path already exists and is not a folder.",
                "LOCAL_PROJECT_CATEGORY_PATH_INVALID",
            )
        raw_category_path = category_root / category
        if raw_category_path.is_symlink():
            raise AppError("Category folders cannot be symbolic links.", "LOCAL_PROJECT_CATEGORY_PATH_INVALID")
        project_parent = raw_category_path.resolve()
        if project_parent.parent != category_root:
            raise AppError(
                "Category folder must stay inside the categories folder.",
                "LOCAL_PROJECT_CATEGORY_PATH_INVALID",
            )
        if project_parent.exists() and not project_parent.is_dir():
            raise AppError("Category path already exists and is not a folder.", "LOCAL_PROJECT_CATEGORY_PATH_INVALID")

    project_path = (project_parent / clean_local_project_name(name_value)).resolve()
    if project_path.parent != project_parent:
        raise AppError("Local project must stay inside the selected parent folder.", "LOCAL_PROJECT_PATH_INVALID")
    if project_path.is_symlink():
        raise AppError("Local project folders cannot be symbolic links.", "LOCAL_PROJECT_PATH_INVALID")
    if project_path.exists() and not project_path.is_dir():
        raise AppError("Local project path already exists and is not a folder.", "LOCAL_PROJECT_EXISTS")
    if project_path.exists() and any(project_path.iterdir()):
        raise AppError("Local project folder already exists and is not empty.", "LOCAL_PROJECT_EXISTS")

    project_path.mkdir(parents=True, exist_ok=True)
    feature_result = localfeatures.create_initial_feature(str(project_path), resources)
    return {
        "project": project_record(project_path, category, "", category_foldered),
        "feature": feature_result["feature"],
        "version": feature_result["version"],
        "copied_shared_resource_files": feature_result["copied_shared_resource_files"],
        "copied_ai_files": feature_result["copied_ai_files"],
    }
