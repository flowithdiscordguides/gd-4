"""Local Mode folder permission prompts and persisted permission metadata."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from gitdesk import APP_VERSION
from gitdesk.errors import AppError
from gitdesk.localprojects import clean_local_project_list


# The build version is diagnostic metadata only; actual folder access is verified against macOS on every entry.
LOCAL_PERMISSION_CURRENT_VERSION = APP_VERSION


# Returns a JSON-safe timestamp for permission grant records.
def permission_timestamp() -> str:
    """Return the UTC timestamp recorded when Local Mode folder access is granted."""

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return timestamp.replace("+00:00", "Z")


# Sanitizes permission records loaded from settings.json.
def clean_local_permission_grants(value: Any) -> dict[str, dict[str, str]]:
    """Return Local Mode permission metadata keyed by saved project path."""

    if not isinstance(value, dict):
        return {}

    grants: dict[str, dict[str, str]] = {}
    for raw_project_path, raw_grant in value.items():
        project_path = str(raw_project_path or "").strip()
        if not project_path or not isinstance(raw_grant, dict):
            continue
        granted_path = str(raw_grant.get("granted_path") or raw_grant.get("path") or "").strip()
        if not granted_path:
            continue
        grants[project_path] = {
            "project_path": project_path,
            "granted_path": granted_path,
            "app_version": str(raw_grant.get("app_version") or "").strip(),
            "granted_at": str(raw_grant.get("granted_at") or "").strip()[:40],
        }
    return grants


# Resolves a path without requiring the folder to be readable yet.
def permission_path(path_value: str) -> Path:
    """Return a normalized path for permission comparisons."""

    return Path(str(path_value or "").strip()).expanduser().resolve(strict=False)


# Builds informational JSON metadata after the operating system confirms actual folder access.
def permission_grant(project_path: str, granted_path: str) -> dict[str, str]:
    """Return the last successful access record for one Local Mode project."""

    return {
        "project_path": project_path,
        "granted_path": granted_path,
        "app_version": LOCAL_PERMISSION_CURRENT_VERSION,
        "granted_at": permission_timestamp(),
    }


# Touches the saved project folder directly so macOS can show the privacy permission prompt.
def request_project_permission(project: dict[str, str]) -> dict[str, str]:
    """Request access to one saved Local Mode project folder and return a grant record."""

    project_path = permission_path(project["path"])
    try:
        with os.scandir(project_path) as entries:
            next(entries, None)
    except FileNotFoundError:
        return {}
    except NotADirectoryError as error:
        raise AppError(
            "Saved Local Mode project path is not a folder.",
            "LOCAL_PERMISSION_PATH_INVALID",
            {"project_path": project["path"]},
        ) from error
    except PermissionError as error:
        raise AppError(
            "macOS denied this saved project folder. Open System Settings > Privacy & Security > "
            "Files & Folders, allow GitDesk to access Documents, then choose Local Mode again.",
            "LOCAL_PERMISSION_DENIED",
            {
                "project_path": project["path"],
                "recovery": "System Settings > Privacy & Security > Files & Folders",
            },
        ) from error
    except OSError as error:
        raise AppError(
            "GitDesk could not request Local Mode folder permission.",
            "LOCAL_PERMISSION_REQUEST_FAILED",
            {"project_path": project["path"]},
        ) from error
    return permission_grant(project["path"], str(project_path))


# Verifies every saved folder against macOS instead of trusting cached JSON permission metadata.
def local_permission_settings_update(settings: dict[str, Any]) -> dict[str, Any]:
    """Return settings updates after verifying actual Local Mode folder access."""

    grants = clean_local_permission_grants(settings.get("local_permission_grants"))
    projects = clean_local_project_list(settings.get("local_projects"))
    project_paths = {project["path"] for project in projects}
    grants = {path: grant for path, grant in grants.items() if path in project_paths}
    verified_paths = []
    missing_paths = []

    for project in projects:
        grant = request_project_permission(project)
        if not grant:
            grants.pop(project["path"], None)
            missing_paths.append(project["path"])
            continue
        grants[project["path"]] = grant
        verified_paths.append(project["path"])

    return {
        "workspace_mode": "local",
        "local_permission_grants": grants,
        "local_permission_app_version": LOCAL_PERMISSION_CURRENT_VERSION,
        "local_permission_verified_paths": verified_paths,
        "local_permission_missing_paths": missing_paths,
    }
