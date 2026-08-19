"""Project Hub state, import scanning, timeline, and backup helpers."""

from __future__ import annotations

# Standard-library helpers provide timestamps, JSON backups, paths, and typed payloads.
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

# GitDesk domain modules derive local project, repository, and Sync Chain state.
from gitdesk import localprojects
from gitdesk.errors import AppError
from gitdesk.localversions import version_number
from gitdesk.managedrepos import active_repository_for_account, repositories_for_account
from gitdesk.syncchain_lifecycle import remove_project_chains
from gitdesk.syncchains import clean_sync_chains


# Timeline history is capped so the settings file stays small during long-running projects.
MAX_TIMELINE_EVENTS = 250

# Backup exports are versioned so future imports can reject incompatible formats safely.
PROJECT_HUB_EXPORT_VERSION = 3


# Returns an ISO timestamp that sorts in the same order as the timeline list.
def timeline_timestamp() -> str:
    """Return a UTC timestamp string for a Project Hub timeline event."""

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return timestamp.replace("+00:00", "Z")


# Builds a compact timeline event without storing secrets or large payloads.
def timeline_event(
    event_type: str,
    title: str,
    detail: str = "",
    project_path: str = "",
    feature_path: str = "",
    version_path: str = "",
    status: str = "info",
) -> dict[str, str]:
    """Return one sanitized Project Hub timeline event."""

    return {
        "timestamp": timeline_timestamp(),
        "type": str(event_type or "event").strip()[:64],
        "title": str(title or "Project event").strip()[:160],
        "detail": str(detail or "").strip()[:320],
        "project_path": str(project_path or "").strip(),
        "feature_path": str(feature_path or "").strip(),
        "version_path": str(version_path or "").strip(),
        "status": str(status or "info").strip()[:32],
    }


# Adds one event while preserving only the newest bounded event list.
def timeline_update(settings: dict[str, Any], event: dict[str, str]) -> dict[str, Any]:
    """Return a settings update containing the existing timeline plus a new event."""

    timeline = list(settings.get("project_timeline") or [])
    timeline.insert(0, event)
    return {"project_timeline": timeline[:MAX_TIMELINE_EVENTS]}


# Resolves a selected folder as a local project root.
def normalize_project_root(path_value: str) -> Path:
    """Return an existing local project root path selected by the user."""

    cleaned_path = str(path_value or "").strip()
    if not cleaned_path:
        raise AppError("Choose an existing project folder first.", "PROJECT_IMPORT_PATH_EMPTY")
    project_path = Path(cleaned_path).expanduser().resolve()
    if not project_path.exists() or not project_path.is_dir():
        raise AppError("Project import path must point to an existing folder.", "PROJECT_IMPORT_PATH_INVALID")
    return project_path


# Converts one direct child folder into import-scan metadata.
def scan_child_folder(child_path: Path) -> dict[str, Any]:
    """Return metadata for one folder found inside an imported project."""

    number = version_number(child_path.name)
    nested_versions = []
    if not number:
        nested_versions = [
            {"name": item.name, "number": version_number(item.name), "path": str(item.resolve())}
            for item in sorted(child_path.iterdir(), key=lambda candidate: candidate.name.lower())
            if item.is_dir() and version_number(item.name)
        ]
    return {
        "name": child_path.name,
        "path": str(child_path.resolve()),
        "kind": "version" if number else "feature" if nested_versions else "loose",
        "version_number": number,
        "versions": sorted(nested_versions, key=lambda item: item["number"]),
    }


# Scans a messy project folder without moving, deleting, or renaming anything.
def scan_existing_project(path_value: str) -> dict[str, Any]:
    """Return a non-mutating inventory for an existing project folder."""

    project_path = normalize_project_root(path_value)
    children = [
        scan_child_folder(child)
        for child in sorted(project_path.iterdir(), key=lambda item: item.name.lower())
        if child.is_dir() and not child.name.startswith(".")
    ]
    direct_versions = [item for item in children if item["kind"] == "version"]
    feature_folders = [item for item in children if item["kind"] == "feature"]
    loose_folders = [item for item in children if item["kind"] == "loose"]
    return {
        "project": {"path": str(project_path), "name": project_path.name},
        "direct_versions": direct_versions,
        "feature_folders": feature_folders,
        "loose_folders": loose_folders,
        "git_present": (project_path / ".git").is_dir(),
        "summary": {
            "direct_versions": len(direct_versions),
            "features": len(feature_folders),
            "loose_folders": len(loose_folders),
        },
    }


# Chooses the newest recognized version so imported projects open somewhere useful.
def preferred_import_selection(scan: dict[str, Any]) -> tuple[str, str]:
    """Return feature and version paths that should become active after import."""

    feature_folders = scan.get("feature_folders") or []
    for feature in feature_folders:
        versions = feature.get("versions") or []
        if versions:
            return str(feature["path"]), str(versions[-1]["path"])

    direct_versions = scan.get("direct_versions") or []
    if direct_versions:
        project_path = str(scan["project"]["path"])
        return project_path, str(direct_versions[-1]["path"])
    return "", ""


# Builds settings updates that register an existing folder as a managed local project.
def import_existing_project(settings: dict[str, Any], path_value: str) -> dict[str, Any]:
    """Return settings updates that import an existing project folder into Local Mode."""

    scan = scan_existing_project(path_value)
    feature_path, version_path = preferred_import_selection(scan)
    updates = localprojects.local_project_settings_update(
        settings,
        str(scan["project"]["path"]),
        feature_path,
        version_path,
    )
    updates.update(
        timeline_update(
            {**settings, **updates},
            timeline_event(
                "project_imported",
                f"Imported {scan['project']['name']}",
                "Existing folder added to Project Hub without moving files.",
                str(scan["project"]["path"]),
                feature_path,
                version_path,
                "success",
            ),
        )
    )
    return updates


# Reads the active local project, feature, and version from derived Local Mode state.
def active_local_context(settings: dict[str, Any]) -> dict[str, Any]:
    """Return the active Local Mode project, feature, and version records."""

    local_state = localprojects.local_projects_state(settings)
    project = next(
        (item for item in local_state["projects"] if item["path"] == local_state["active_project"]),
        None,
    )
    feature = None
    version = None
    if project:
        feature = next(
            (item for item in project.get("features", []) if item["path"] == local_state["active_feature"]),
            None,
        )
    if feature:
        version = next(
            (item for item in feature.get("versions", []) if item["path"] == local_state["active_version"]),
            None,
        )
    return {"local": local_state, "project": project, "feature": feature, "version": version}


# Summarizes the active GitHub account and managed repository connection for Project Hub workflows.
def github_connection_state(settings: dict[str, Any]) -> dict[str, Any]:
    """Return non-secret GitHub connection metadata for Project Hub workflows."""

    login = str(settings.get("active_account") or "")
    repository = active_repository_for_account(settings, login) if login else None
    return {
        "active_account": login,
        "repository": repository,
        "repositories": repositories_for_account(settings, login) if login else [],
        "owner": str(settings.get("github_owner") or ""),
        "repo": str(settings.get("github_repo") or ""),
    }


# Produces Project Hub state without coupling the frontend to settings internals.
def project_hub_state(settings: dict[str, Any]) -> dict[str, Any]:
    """Return Project Hub state from settings and filesystem-derived local state."""

    local_context = active_local_context(settings)
    return {
        "local": local_context["local"],
        "active_project": local_context["project"],
        "active_feature": local_context["feature"],
        "active_version": local_context["version"],
        "github": github_connection_state(settings),
        "timeline": list(settings.get("project_timeline") or [])[:MAX_TIMELINE_EVENTS],
    }


# Creates a portable, non-secret backup payload for Project Hub settings.
def export_project_hub_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON backup payload that excludes GitHub tokens."""

    payload = {
        "format": "gitdesk-project-hub",
        "version": PROJECT_HUB_EXPORT_VERSION,
        "exported_at": timeline_timestamp(),
        "settings": {
            "workspace_mode": settings.get("workspace_mode", "repo"),
            "create_categories_as_folders": settings.get("create_categories_as_folders", False),
            "local_projects": settings.get("local_projects", []),
            "local_project_categories": settings.get("local_project_categories", []),
            "local_parent_favorites": settings.get("local_parent_favorites", []),
            "active_local_project": settings.get("active_local_project", ""),
            "active_local_feature": settings.get("active_local_feature", ""),
            "active_local_version": settings.get("active_local_version", ""),
            "local_cleanup_paths": settings.get("local_cleanup_paths", []),
            "local_version_statuses": settings.get("local_version_statuses", {}),
            "project_timeline": settings.get("project_timeline", []),
            "activity_tracker_started_on": settings.get("activity_tracker_started_on", ""),
            "managed_repositories": settings.get("managed_repositories", {}),
            "active_repository_by_account": settings.get("active_repository_by_account", {}),
            "repository_categories": settings.get("repository_categories", {}),
            "sync_chains": settings.get("sync_chains", []),
            "github_accounts": settings.get("github_accounts", []),
            "active_account": settings.get("active_account", ""),
        },
    }
    return {"payload": payload, "json": json.dumps(payload, indent=2, sort_keys=True)}


# Parses a Project Hub backup and returns setting keys that are safe to import.
def import_project_hub_settings(raw_json: str) -> dict[str, Any]:
    """Return safe settings updates parsed from an exported Project Hub JSON payload."""

    try:
        payload = json.loads(str(raw_json or ""))
    except json.JSONDecodeError as error:
        raise AppError("Project Hub import JSON is invalid.", "PROJECT_HUB_IMPORT_JSON_INVALID") from error
    if not isinstance(payload, dict) or payload.get("format") != "gitdesk-project-hub":
        raise AppError("Project Hub import file has the wrong format.", "PROJECT_HUB_IMPORT_FORMAT_INVALID")
    if int(payload.get("version") or 0) not in {1, 2, PROJECT_HUB_EXPORT_VERSION}:
        raise AppError("Project Hub import version is not supported.", "PROJECT_HUB_IMPORT_VERSION_INVALID")
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        raise AppError("Project Hub import settings are missing.", "PROJECT_HUB_IMPORT_SETTINGS_INVALID")
    allowed_keys = {
        "workspace_mode",
        "create_categories_as_folders",
        "local_projects",
        "local_project_categories",
        "local_parent_favorites",
        "active_local_project",
        "active_local_feature",
        "active_local_version",
        "local_cleanup_paths",
        "local_version_statuses",
        "project_timeline",
        "activity_tracker_started_on",
        "managed_repositories",
        "active_repository_by_account",
        "repository_categories",
        "sync_chains",
        "github_accounts",
        "active_account",
    }
    return {key: settings[key] for key in allowed_keys if key in settings}


# Drops missing local projects while leaving existing folders untouched.
def repair_missing_projects(settings: dict[str, Any]) -> dict[str, Any]:
    """Return settings updates with missing local project records removed."""

    projects = [
        record
        for record in localprojects.clean_local_project_list(settings.get("local_projects"))
        if Path(record["path"]).expanduser().is_dir()
    ]
    active_project = str(settings.get("active_local_project") or "")
    if active_project and not any(record["path"] == active_project for record in projects):
        active_project = projects[0]["path"] if projects else ""
    updates = {"local_projects": projects, "active_local_project": active_project}
    updates["sync_chains"] = remove_project_chains(
        {**settings, "sync_chains": clean_sync_chains(settings.get("sync_chains"))},
        {record["path"] for record in projects},
    )
    if not active_project:
        updates.update({"active_local_feature": "", "active_local_version": ""})
    return updates
