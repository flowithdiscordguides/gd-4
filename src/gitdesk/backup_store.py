"""Owner-only Backup Mode destination, scan, and completed-version state."""

from __future__ import annotations

# JSON and path helpers sanitize persisted removable-drive state.
import json
from pathlib import Path
from typing import Any

# Shared storage helpers guarantee atomic owner-only metadata replacement.
from gitdesk.backup_selection import clean_backup_selection
from gitdesk.errors import AppError
from gitdesk.reposettings_recovery import invalid_json_backup_path, load_recoverable_json, mark_backup_recovered
from gitdesk.storage import APP_STORAGE_LOCK, app_config_path, atomic_write_private_bytes, atomic_write_private_json


# The schema version distinguishes Backup Mode metadata from destination snapshot manifests.
BACKUP_STATE_SCHEMA_VERSION = 5

# Private destination paths and change samples remain visible only to the current user.
BACKUP_STATE_DIRECTORY_MODE = 0o700
BACKUP_STATE_FILE_MODE = 0o600

# Completed version history stays bounded in app metadata while all folders remain on the chosen drive.
MAX_BACKUP_VERSIONS = 250

# Destination-parent favorites match the compact New Project picker without growing indefinitely.
MAX_BACKUP_PARENT_FAVORITES = 12

# Changed source ownership is bounded independently from the shorter path-level change preview.
MAX_SCAN_SOURCE_IDS = 2000


# Converts malformed numeric metadata into a non-negative safe value.
def non_negative_int(value: Any) -> int:
    """Return a non-negative integer or zero when value is malformed."""

    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


# Cleans saved parent folders without requiring removable drives to remain connected.
def clean_parent_favorites(value: Any) -> list[str]:
    """Return de-duplicated Backup Mode parent-folder favorites."""

    if not isinstance(value, list):
        return []
    favorites = []
    seen = set()
    for item in value:
        path = str(item or "").strip()
        key = path.casefold()
        if path and key not in seen:
            favorites.append(path)
            seen.add(key)
    return favorites[:MAX_BACKUP_PARENT_FAVORITES]


# Sanitizes stable changed-source identifiers without allowing duplicates or unbounded metadata growth.
def clean_scan_source_ids(value: Any) -> list[str]:
    """Return a bounded de-duplicated changed-source identifier list."""

    if not isinstance(value, list):
        return []
    source_ids = []
    seen = set()
    for item in value:
        source_id = str(item or "").strip()[:128]
        if source_id and source_id not in seen:
            source_ids.append(source_id)
            seen.add(source_id)
    return source_ids[:MAX_SCAN_SOURCE_IDS]


# Sanitizes one completed snapshot record without requiring its external drive to be connected.
def clean_version(value: Any) -> dict[str, Any] | None:
    """Return one valid completed backup version record, or None."""

    if not isinstance(value, dict):
        return None
    raw_changes = value.get("changes") if isinstance(value.get("changes"), dict) else {}
    path = str(value.get("path") or "").strip()
    name = str(value.get("name") or "").strip()
    created_at = str(value.get("created_at") or "").strip()[:40]
    if not path or not name or not created_at:
        return None
    return {
        "name": name[:160],
        "path": path,
        "created_at": created_at,
        "file_count": non_negative_int(value.get("file_count")),
        "directory_count": non_negative_int(value.get("directory_count")),
        "total_bytes": non_negative_int(value.get("total_bytes")),
        "skipped_count": non_negative_int(value.get("skipped_count")),
        "changes": {
            "added": non_negative_int(raw_changes.get("added")),
            "modified": non_negative_int(raw_changes.get("modified")),
            "deleted": non_negative_int(raw_changes.get("deleted")),
            "total": non_negative_int(raw_changes.get("total")),
        },
    }


# Sanitizes one pending scan summary without retaining the potentially enormous full manifest.
def clean_scan(value: Any) -> dict[str, Any]:
    """Return bounded pending-change and unavailable-source state."""

    raw = value if isinstance(value, dict) else {}
    changes = raw.get("changes") if isinstance(raw.get("changes"), list) else []
    errors = raw.get("errors") if isinstance(raw.get("errors"), list) else []
    return {
        "scanned_at": str(raw.get("scanned_at") or "").strip()[:40],
        "has_changes": raw.get("has_changes") is True,
        "added": non_negative_int(raw.get("added")),
        "modified": non_negative_int(raw.get("modified")),
        "deleted": non_negative_int(raw.get("deleted")),
        "total": non_negative_int(raw.get("total")),
        "changes": [
            {"kind": str(item.get("kind") or "")[:16], "path": str(item.get("path") or "")[:1000]}
            for item in changes[:500]
            if isinstance(item, dict)
        ],
        "truncated": raw.get("truncated") is True,
        "changed_source_ids": clean_scan_source_ids(raw.get("changed_source_ids")),
        "errors": [
            {
                "label": str(item.get("label") or "")[:160],
                "path": str(item.get("path") or "")[:1000],
                "category": str(item.get("category") or "")[:160],
                "message": str(item.get("message") or "")[:500],
                "code": str(item.get("code") or "")[:100],
            }
            for item in errors[:100]
            if isinstance(item, dict)
        ],
    }


# Produces the complete safe state and keeps newest completed versions first.
def clean_state(value: Any) -> dict[str, Any]:
    """Return a complete sanitized Backup Mode state object."""

    raw = value if isinstance(value, dict) else {}
    raw_versions = raw.get("versions") if isinstance(raw.get("versions"), list) else []
    versions = [
        version
        for item in raw_versions
        if (version := clean_version(item))
    ]
    versions.sort(key=lambda item: item["created_at"], reverse=True)
    latest_path = str(raw.get("latest_snapshot") or "").strip()
    if latest_path and not any(item["path"] == latest_path for item in versions):
        latest_path = ""
    return {
        "schema_version": BACKUP_STATE_SCHEMA_VERSION,
        "destination": str(raw.get("destination") or "").strip(),
        "parent_favorites": clean_parent_favorites(raw.get("parent_favorites")),
        "selection": clean_backup_selection(raw.get("selection")),
        "latest_snapshot": latest_path,
        "versions": versions[:MAX_BACKUP_VERSIONS],
        "scan": clean_scan(raw.get("scan")),
    }


# BackupStore owns state independently from general SettingsStore to avoid expanding its near-limit module.
class BackupStore:
    """Persist Backup Mode destination, pending changes, and completed snapshots."""

    # Allows focused tests to supply an isolated owner-only state file.
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or app_config_path() / "backup-state.json"

    # Returns a fresh empty Backup Mode state.
    def defaults(self) -> dict[str, Any]:
        """Return an empty versioned Backup Mode state."""

        return clean_state({})

    # Preserves malformed bytes before recovery and replacement.
    def preserve_invalid_json(self) -> Path:
        """Return the private backup path containing unreadable Backup Mode state."""

        backup_path = invalid_json_backup_path(self.config_path)
        try:
            atomic_write_private_bytes(
                backup_path,
                self.config_path.read_bytes(),
                BACKUP_STATE_DIRECTORY_MODE,
                BACKUP_STATE_FILE_MODE,
            )
        except OSError as error:
            raise AppError("Backup Mode state could not be preserved.", "BACKUP_STATE_INVALID_JSON") from error
        return backup_path

    # Loads and repairs state while allowing disconnected destination drives.
    def load(self) -> dict[str, Any]:
        """Return current sanitized Backup Mode state."""

        with APP_STORAGE_LOCK:
            if not self.config_path.exists():
                return self.defaults()
            try:
                raw_state = json.loads(self.config_path.read_text(encoding="utf-8"))
            except OSError as error:
                raise AppError("Unable to read Backup Mode state.", "BACKUP_STATE_READ_FAILED") from error
            except json.JSONDecodeError:
                backup_path = self.preserve_invalid_json()
                state = clean_state(load_recoverable_json(backup_path))
                self.write(state)
                mark_backup_recovered(backup_path)
                return state
            state = clean_state(raw_state)
            if raw_state != state:
                self.write(state)
            return state

    # Writes complete sanitized state with owner-only permissions.
    def write(self, state: dict[str, Any]) -> None:
        """Persist Backup Mode state atomically."""

        try:
            atomic_write_private_json(
                self.config_path,
                clean_state(state),
                BACKUP_STATE_DIRECTORY_MODE,
                BACKUP_STATE_FILE_MODE,
            )
        except OSError as error:
            raise AppError("Unable to save Backup Mode state.", "BACKUP_STATE_WRITE_FAILED") from error

    # Validates and stores a user-picked existing destination directory.
    def save_destination(self, path_value: Any) -> dict[str, Any]:
        """Persist one existing non-symlink backup destination and reset stale scan state."""

        raw_path = str(path_value or "").strip()
        path = Path(raw_path).expanduser()
        if not raw_path or path.is_symlink() or not path.is_dir():
            raise AppError("Choose an existing backup destination folder.", "BACKUP_DESTINATION_INVALID")
        with APP_STORAGE_LOCK:
            state = self.load()
            resolved_path = str(path.resolve())
            # Re-selecting the same drive folder must retain its completed version history and latest baseline.
            if state["destination"] == resolved_path:
                return state
            state["destination"] = resolved_path
            state["latest_snapshot"] = ""
            state["versions"] = []
            state["scan"] = clean_scan({})
            self.write(state)
            return clean_state(state)

    # Moves one validated parent folder to the front of Backup Mode's quick-access favorites.
    def save_parent_favorite(self, path_value: Any) -> dict[str, Any]:
        """Persist one available backup parent as the newest favorite."""

        raw_path = str(path_value or "").strip()
        path = Path(raw_path).expanduser()
        if not raw_path or path.is_symlink() or not path.is_dir():
            raise AppError("Choose an existing backup parent folder.", "BACKUP_PARENT_FAVORITE_INVALID")
        with APP_STORAGE_LOCK:
            state = self.load()
            favorite = str(path.resolve())
            remaining = [
                item
                for item in state["parent_favorites"]
                if item.casefold() != favorite.casefold()
            ]
            state["parent_favorites"] = [favorite, *remaining][:MAX_BACKUP_PARENT_FAVORITES]
            self.write(state)
            return clean_state(state)

    # Replaces the pending scan summary while preserving destination and version history.
    def save_scan(self, scan: dict[str, Any]) -> dict[str, Any]:
        """Persist a bounded change scan and return complete Backup Mode state."""

        with APP_STORAGE_LOCK:
            state = self.load()
            state["scan"] = clean_scan(scan)
            self.write(state)
            return clean_state(state)

    # Saves a confirmed source scope with its scan result when no new snapshot is necessary.
    def save_selection_scan(
        self,
        selection: list[dict[str, Any]],
        scan: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist confirmed selection and pending scan state together."""

        with APP_STORAGE_LOCK:
            state = self.load()
            state["selection"] = clean_backup_selection(selection)
            state["scan"] = clean_scan(scan)
            self.write(state)
            return clean_state(state)

    # Adds one completed snapshot, marks it latest, and preserves any explicitly skipped paths as pending.
    def add_version(
        self,
        version: dict[str, Any],
        selection: list[dict[str, Any]],
        pending_scan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist one completed backup version and its confirmed source selection."""

        cleaned_version = clean_version(version)
        if not cleaned_version:
            raise AppError("Completed backup metadata is invalid.", "BACKUP_VERSION_INVALID")
        with APP_STORAGE_LOCK:
            state = self.load()
            state["versions"] = [
                cleaned_version,
                *[item for item in state["versions"] if item["path"] != cleaned_version["path"]],
            ][:MAX_BACKUP_VERSIONS]
            state["latest_snapshot"] = cleaned_version["path"]
            state["selection"] = clean_backup_selection(selection)
            state["scan"] = clean_scan(
                pending_scan or {"scanned_at": cleaned_version["created_at"]},
            )
            self.write(state)
            return clean_state(state)

    # Replaces metadata for one physically merged version while retaining history order and latest ownership.
    def replace_version(self, version: dict[str, Any]) -> dict[str, Any]:
        """Persist refreshed metadata for one existing completed Backup version."""

        cleaned_version = clean_version(version)
        if not cleaned_version:
            raise AppError("Merged backup metadata is invalid.", "BACKUP_VERSION_INVALID")
        with APP_STORAGE_LOCK:
            state = self.load()
            matching = [item for item in state["versions"] if item["path"] == cleaned_version["path"]]
            if not matching:
                raise AppError("The merged parent is not in Backup history.", "BACKUP_MERGE_PARENT_INVALID")
            state["versions"] = [
                cleaned_version if item["path"] == cleaned_version["path"] else item
                for item in state["versions"]
            ]
            self.write(state)
            return clean_state(state)
