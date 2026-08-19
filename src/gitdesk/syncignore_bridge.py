"""Bridge handlers for Sync Ignore rules and allowlisted metadata viewing."""

from __future__ import annotations

# JSON and path helpers support bounded read-only metadata inspection.
import json
from pathlib import Path
from typing import Any, Callable

# GitDesk services validate Local ownership, owner-only storage, and native folder opening.
from gitdesk.errors import AppError
from gitdesk.nativeopen import open_folder
from gitdesk.storage import app_config_path
from gitdesk import syncignore
from gitdesk.syncignore_store import SyncIgnoreStore


# System Settings may inspect these non-secret app-owned JSON files and no arbitrary frontend path.
METADATA_FILE_NAMES = (
    "settings.json",
    "reposettings.json",
    "media-library.json",
    "documents.json",
    "shared-resources.json",
    "local-activity.json",
    "sync-ignore.json",
    "backup-state.json",
)

# Bounded viewing avoids sending an unexpectedly large activity file into the WebView.
MAX_METADATA_VIEW_BYTES = 2 * 1024 * 1024


# Registers the selected-version rule editor and System Settings metadata actions.
def sync_ignore_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for Sync Ignore and metadata inspection."""

    return {
        "syncIgnoreState": lambda payload: handle_sync_ignore_state(controller, payload),
        "saveSyncIgnore": lambda payload: handle_save_sync_ignore(controller, payload),
        "metadataFiles": lambda payload: handle_metadata_files(controller, payload),
        "viewMetadataFile": lambda payload: handle_view_metadata_file(controller, payload),
        "openMetadataFolder": lambda payload: handle_open_metadata_folder(controller, payload),
    }


# Returns current project rules and a fresh selectable tree for the requested version.
def handle_sync_ignore_state(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return Sync Ignore modal state for one saved Local version."""

    settings = controller.settings_store.load()
    project, version_path = syncignore.project_for_version(settings, payload.get("version_path"))
    store = SyncIgnoreStore()
    registry = store.ensure_file()
    ignored_paths = next(
        (
            item["ignored_paths"]
            for item in registry["projects"]
            if item["project_path"] == project["path"]
        ),
        [],
    )
    return syncignore.sync_ignore_state(settings, str(version_path), ignored_paths)


# Validates current entries and atomically replaces one project's complete rule set.
def handle_save_sync_ignore(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist selected Sync Ignore paths and return refreshed modal state."""

    settings = controller.settings_store.load()
    project, version_path = syncignore.project_for_version(settings, payload.get("version_path"))
    ignored_paths = syncignore.validate_selected_paths(version_path, payload.get("ignored_paths"))
    store = SyncIgnoreStore()
    store.save_project_rules(project["path"], ignored_paths)
    return syncignore.sync_ignore_state(settings, str(version_path), ignored_paths)


# Returns allowlisted metadata file locations and existence state for System Settings.
def handle_metadata_files(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return frontend-safe metadata file records without reading their contents."""

    SyncIgnoreStore().ensure_file()
    root = app_config_path()
    return {
        "folder": str(root),
        "files": [
            {"name": name, "path": str(root / name), "exists": (root / name).is_file()}
            for name in METADATA_FILE_NAMES
        ],
    }


# Resolves one allowlisted filename independently from its frontend-supplied path label.
def metadata_path(name_value: Any) -> Path:
    """Return one allowed app metadata path or raise for an unknown filename."""

    name = str(name_value or "").strip()
    if name not in METADATA_FILE_NAMES:
        raise AppError("That metadata file is not available in System Settings.", "METADATA_FILE_FORBIDDEN")
    return app_config_path() / name


# Reads and formats one non-secret JSON file into the bounded System Settings viewer.
def handle_view_metadata_file(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return formatted JSON content for one allowlisted metadata filename."""

    path = metadata_path(payload.get("name"))
    if not path.is_file():
        raise AppError("That metadata file has not been created yet.", "METADATA_FILE_MISSING")
    try:
        if path.stat().st_size > MAX_METADATA_VIEW_BYTES:
            raise AppError("That metadata file is too large for the in-app viewer.", "METADATA_FILE_TOO_LARGE")
        raw_content = path.read_text(encoding="utf-8")
        content = json.dumps(json.loads(raw_content), indent=2, sort_keys=True) + "\n"
    except AppError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AppError("That metadata file could not be displayed.", "METADATA_FILE_READ_FAILED") from error
    return {"name": path.name, "path": str(path), "content": content}


# Opens only GitDesk's fixed metadata directory through the platform file manager.
def handle_open_metadata_folder(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Open the GitDesk metadata folder in Finder, Explorer, or the Linux file manager."""

    return open_folder(str(app_config_path()))
