"""Owner-only project-scoped Sync Ignore metadata for GitDesk."""

from __future__ import annotations

# Standard-library JSON and path helpers keep rules private and portable.
import json
from pathlib import Path, PurePosixPath
from typing import Any

# Shared storage helpers provide app-wide locking and atomic owner-only replacement.
from gitdesk.errors import AppError
from gitdesk.reposettings_recovery import invalid_json_backup_path, load_recoverable_json, mark_backup_recovered
from gitdesk.storage import APP_STORAGE_LOCK, app_config_path, atomic_write_private_bytes, atomic_write_private_json
from gitdesk.syncchains import sync_timestamp


# The schema version makes future rule-shape migrations explicit.
SYNC_IGNORE_SCHEMA_VERSION = 1

# Rule collections are bounded so a malformed frontend cannot create unmanageable metadata.
MAX_SYNC_IGNORE_RULES = 2000

# Sync Ignore metadata contains private paths and therefore uses owner-only permissions.
SYNC_IGNORE_DIRECTORY_MODE = 0o700
SYNC_IGNORE_FILE_MODE = 0o600


# Normalizes one version-relative path without permitting traversal or Git metadata rules.
def clean_ignore_path(value: Any) -> str:
    """Return one portable relative ignore path, or an empty string when malformed."""

    raw_path = str(value or "").strip().replace("\\", "/").strip("/")
    if not raw_path:
        return ""
    path = PurePosixPath(raw_path)
    # Rules must stay relative and `.git` remains an unconditional built-in exclusion.
    if path.is_absolute() or any(part in {"", ".", "..", ".git"} for part in path.parts):
        return ""
    return path.as_posix()


# De-duplicates rules and removes children already covered by a selected parent directory.
def clean_ignore_paths(value: Any) -> list[str]:
    """Return a bounded minimal list of valid project-relative ignore paths."""

    if not isinstance(value, list):
        return []
    cleaned = sorted(
        {path for raw_path in value if (path := clean_ignore_path(raw_path))},
        key=lambda path: (path.count("/"), path.casefold()),
    )
    collapsed: list[str] = []
    # Parent rules cover every descendant, so retaining child rules would create misleading duplicate state.
    for path in cleaned:
        if any(path == parent or path.startswith(f"{parent}/") for parent in collapsed):
            continue
        collapsed.append(path)
        if len(collapsed) >= MAX_SYNC_IGNORE_RULES:
            break
    return sorted(collapsed, key=str.casefold)


# Sanitizes one project record without touching its potentially disconnected folder.
def clean_project_rules(value: Any) -> dict[str, Any] | None:
    """Return one valid project rule record, or None when its owner path is absent."""

    if not isinstance(value, dict):
        return None
    project_path = str(value.get("project_path") or "").strip()
    if not project_path:
        return None
    return {
        "project_path": project_path,
        "ignored_paths": clean_ignore_paths(value.get("ignored_paths")),
        "updated_at": str(value.get("updated_at") or "").strip()[:40],
    }


# Produces the complete persisted registry while de-duplicating project owners by path.
def clean_registry(value: Any) -> dict[str, Any]:
    """Return a complete sanitized Sync Ignore registry."""

    raw = value if isinstance(value, dict) else {}
    projects = []
    seen_paths = set()
    for raw_project in raw.get("projects") if isinstance(raw.get("projects"), list) else []:
        project = clean_project_rules(raw_project)
        if not project or project["project_path"] in seen_paths:
            continue
        projects.append(project)
        seen_paths.add(project["project_path"])
    return {
        "schema_version": SYNC_IGNORE_SCHEMA_VERSION,
        "projects": sorted(projects, key=lambda item: item["project_path"].casefold()),
    }


# SyncIgnoreStore owns sync-ignore.json independently from repository settings and version folders.
class SyncIgnoreStore:
    """Persist project rule sets beside GitDesk's other owner-only metadata JSON files."""

    # Allows focused tests to supply an isolated metadata file.
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or app_config_path() / "sync-ignore.json"

    # Returns the empty versioned registry without creating a file.
    def defaults(self) -> dict[str, Any]:
        """Return a fresh empty Sync Ignore registry."""

        return clean_registry({})

    # Preserves malformed bytes before replacing the live metadata file.
    def preserve_invalid_json(self) -> Path:
        """Return the private backup path containing unreadable Sync Ignore bytes."""

        backup_path = invalid_json_backup_path(self.config_path)
        try:
            atomic_write_private_bytes(
                backup_path,
                self.config_path.read_bytes(),
                SYNC_IGNORE_DIRECTORY_MODE,
                SYNC_IGNORE_FILE_MODE,
            )
        except OSError as error:
            raise AppError("Sync Ignore metadata could not be preserved.", "SYNC_IGNORE_INVALID_JSON") from error
        return backup_path

    # Loads and repairs the registry while retaining recoverable malformed input.
    def load(self) -> dict[str, Any]:
        """Return the current sanitized Sync Ignore registry."""

        with APP_STORAGE_LOCK:
            if not self.config_path.exists():
                return self.defaults()
            try:
                raw_registry = json.loads(self.config_path.read_text(encoding="utf-8"))
            except OSError as error:
                raise AppError("Unable to read Sync Ignore metadata.", "SYNC_IGNORE_READ_FAILED") from error
            except json.JSONDecodeError:
                backup_path = self.preserve_invalid_json()
                registry = clean_registry(load_recoverable_json(backup_path))
                self.write(registry)
                mark_backup_recovered(backup_path)
                return registry
            registry = clean_registry(raw_registry)
            if raw_registry != registry:
                self.write(registry)
            return registry

    # Writes a complete sanitized registry with owner-only permissions.
    def write(self, registry: dict[str, Any]) -> None:
        """Persist Sync Ignore metadata atomically."""

        try:
            atomic_write_private_json(
                self.config_path,
                clean_registry(registry),
                SYNC_IGNORE_DIRECTORY_MODE,
                SYNC_IGNORE_FILE_MODE,
            )
        except OSError as error:
            raise AppError("Unable to save Sync Ignore metadata.", "SYNC_IGNORE_WRITE_FAILED") from error

    # Creates the canonical file when System Settings needs a concrete artifact to open or view.
    def ensure_file(self) -> dict[str, Any]:
        """Return current rules and create the default file only when it is absent."""

        with APP_STORAGE_LOCK:
            registry = self.load()
            if not self.config_path.exists():
                self.write(registry)
            return registry

    # Returns the exact saved rules for one registered Local project.
    def rules_for_project(self, project_path: str) -> list[str]:
        """Return copied ignored paths for project_path."""

        cleaned_path = str(project_path or "").strip()
        record = next(
            (item for item in self.load()["projects"] if item["project_path"] == cleaned_path),
            None,
        )
        return list(record["ignored_paths"]) if record else []

    # Replaces one project's complete rule set while preserving every other project.
    def save_project_rules(self, project_path: str, ignored_paths: Any) -> dict[str, Any]:
        """Persist ignored_paths for project_path and return the complete registry."""

        cleaned_project_path = str(project_path or "").strip()
        if not cleaned_project_path:
            raise AppError("A Local project is required for Sync Ignore.", "SYNC_IGNORE_PROJECT_REQUIRED")
        record = {
            "project_path": cleaned_project_path,
            "ignored_paths": clean_ignore_paths(ignored_paths),
            "updated_at": sync_timestamp(),
        }
        with APP_STORAGE_LOCK:
            registry = self.load()
            registry["projects"] = [
                item for item in registry["projects"] if item["project_path"] != cleaned_project_path
            ]
            registry["projects"].append(record)
            self.write(registry)
            return clean_registry(registry)

    # Moves one project-owned rule record when Local Mode changes the physical project root.
    def remap_project_path(self, old_path_value: Any, new_path_value: Any) -> dict[str, Any]:
        """Replace one saved project path while preserving its exact ignored rules."""

        old_path = str(old_path_value or "").strip()
        new_path = str(new_path_value or "").strip()
        if not old_path or not new_path or old_path == new_path:
            return self.load()
        with APP_STORAGE_LOCK:
            registry = self.load()
            source_record = next(
                (item for item in registry["projects"] if item["project_path"] == old_path),
                None,
            )
            if source_record is None:
                return registry
            remapped = {
                **source_record,
                "project_path": new_path,
                "updated_at": sync_timestamp(),
            }
            registry["projects"] = [
                item
                for item in registry["projects"]
                if item["project_path"] not in {old_path, new_path}
            ]
            registry["projects"].append(remapped)
            self.write(registry)
            return clean_registry(registry)
