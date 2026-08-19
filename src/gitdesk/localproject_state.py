"""Derived complete and selected-project state for GitDesk Local Mode."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gitdesk import localfeatures
from gitdesk import localproject_icons
from gitdesk import sharedresources
from gitdesk.errors import AppError
from gitdesk.localproject_records import clean_local_project_list
from gitdesk.localversions import clean_cleanup_paths, version_number
from gitdesk.sharedresource_store import SharedResourceStore


# Workspace modes keep repository, physical-project, media-library, and backup workflows separate.
WORKSPACE_MODES = {"repo", "local", "media", "backup"}


# Normalizes persisted mode values before they reach the frontend workspace controller.
def clean_workspace_mode(value: Any) -> str:
    """Return the saved workspace mode, defaulting to repo for malformed settings."""

    mode = str(value or "repo").strip().lower()
    return mode if mode in WORKSPACE_MODES else "repo"


# Enriches one project's already-discovered features from a single Shared Resource registry snapshot.
def resource_features(
    features: list[dict[str, Any]],
    resource_store: SharedResourceStore,
    resource_registry: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return feature records enriched with tracked Shared Resource summaries."""

    enriched_features = []
    for feature in features:
        versions = [
            {
                **version,
                "shared_resources": sharedresources.installed_resource_summary(
                    version["path"],
                    resource_store,
                    resource_registry,
                ),
            }
            for version in feature.get("versions") or []
        ]
        enriched_features.append({**feature, "versions": versions})
    return enriched_features


# Builds one project payload while keeping unrelated saved project folders outside the call path.
def project_state(
    record: dict[str, Any],
    active_project: str,
    resource_store: SharedResourceStore,
    resource_registry: dict[str, Any],
    features: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return one project record without scanning any unrelated saved project."""

    exists = Path(record["path"]).expanduser().is_dir()
    project_features = features if features is not None else (
        localfeatures.list_features(record["path"]) if exists else []
    )
    project = {
        "name": record["name"],
        "path": record["path"],
        "category": record.get("category", ""),
        "exists": exists,
        "features": resource_features(project_features, resource_store, resource_registry),
        "icon_path": record.get("icon_path", ""),
        "icon_name": "",
        "icon_data_url": "",
        "icon_source": "",
    }
    if record["path"] == active_project:
        project.update(localproject_icons.project_icon_preview(record, project_features))
    return project


# Keeps selection metadata identical between the complete and lightweight response shapes.
def selection_fields(settings: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical selection fields shared by full and targeted state responses."""

    return {
        "mode": clean_workspace_mode(settings.get("workspace_mode")),
        "active_project": str(settings.get("active_local_project") or ""),
        "active_feature": str(settings.get("active_local_feature") or ""),
        "active_version": str(settings.get("active_local_version") or ""),
        "cleanup_paths": clean_cleanup_paths(settings.get("local_cleanup_paths")),
    }


# Validates cached child paths without walking the selected project's complete feature and version hierarchy.
def local_project_selection_update(
    settings: dict[str, Any],
    project_path_value: str,
    feature_path_value: str,
    version_path_value: str,
) -> dict[str, str]:
    """Return a bounded, server-validated update for one cached project selection."""

    project_path_text = str(project_path_value or "").strip()
    record = next(
        (
            item
            for item in clean_local_project_list(settings.get("local_projects"))
            if item["path"] == project_path_text
        ),
        None,
    )
    if not record:
        raise AppError("The selected local project is not saved.", "LOCAL_PROJECT_NOT_FOUND")
    project_path = localfeatures.normalize_project_directory(record["path"])
    update = {
        "active_local_project": record["path"],
        "active_local_feature": "",
        "active_local_version": "",
    }

    feature_path_text = str(feature_path_value or "").strip()
    if not feature_path_text:
        return update
    try:
        feature_path = Path(feature_path_text).expanduser().resolve()
        feature_exists = feature_path.is_dir()
    except (OSError, RuntimeError):
        return update
    valid_legacy_feature = feature_path == project_path
    valid_feature_child = feature_path.parent == project_path and not version_number(feature_path.name)
    if not feature_exists or not (valid_legacy_feature or valid_feature_child):
        return update
    update["active_local_feature"] = str(feature_path)

    version_path_text = str(version_path_value or "").strip()
    if not version_path_text:
        return update
    try:
        version_path = Path(version_path_text).expanduser().resolve()
        version_exists = version_path.is_dir()
    except (OSError, RuntimeError):
        return update
    if version_exists and version_path.parent == feature_path and version_number(version_path.name):
        update["active_local_version"] = str(version_path)
    return update


# Resolves only the requested saved project for latency-sensitive create and dropdown workflows.
def local_project_selection_state(
    settings: dict[str, Any],
    project_path_value: str,
    features: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return authoritative state for one selected project without rebuilding every project."""

    project_path = str(project_path_value or "").strip()
    record = next(
        (item for item in clean_local_project_list(settings.get("local_projects")) if item["path"] == project_path),
        None,
    )
    if not record:
        raise AppError("The selected local project is not saved.", "LOCAL_PROJECT_NOT_FOUND")
    resource_store = SharedResourceStore()
    resource_registry = resource_store.load()
    fields = selection_fields(settings)
    return {
        **fields,
        "project": project_state(record, fields["active_project"], resource_store, resource_registry, features),
    }


# Retains the comprehensive rescan used by explicit refreshes and hierarchy-mutating workflows.
def local_projects_state(settings: dict[str, Any]) -> dict[str, Any]:
    """Return complete frontend state for Local Mode project, feature, and version selectors."""

    fields = selection_fields(settings)
    active_project = fields["active_project"]
    active_feature = fields["active_feature"]
    active_version = fields["active_version"]
    if active_project and active_version and not active_feature:
        try:
            project_path = Path(active_project).expanduser().resolve()
            active_feature = str(localfeatures.feature_path_for_version(project_path, active_version))
        except AppError:
            active_feature = ""
        fields["active_feature"] = active_feature

    resource_store = SharedResourceStore()
    resource_registry = resource_store.load()
    projects = [
        project_state(record, active_project, resource_store, resource_registry)
        for record in clean_local_project_list(settings.get("local_projects"))
    ]
    return {**fields, "projects": projects}
