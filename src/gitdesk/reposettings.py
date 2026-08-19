"""Durable non-secret repository registry storage for GitDesk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gitdesk.errors import AppError
from gitdesk.reposettings_recovery import invalid_json_backup_candidates, invalid_json_backup_path
from gitdesk.reposettings_recovery import load_recoverable_json, mark_backup_recovered
from gitdesk.reposettings_recovery import merge_recovered_registry_settings, registry_has_metadata
from gitdesk.reposettings_schema import REPO_SETTINGS_SCHEMA_VERSION, clean_category_name
from gitdesk.reposettings_schema import clean_registry_settings, merge_legacy_registry_settings
from gitdesk.storage import APP_STORAGE_LOCK, app_config_path, atomic_write_private_bytes, atomic_write_private_json


# Registry files contain non-secret private paths, chains, and account associations.
REPO_SETTINGS_DIRECTORY_MODE = 0o700
REPO_SETTINGS_FILE_MODE = 0o600

# RepoSettingsStore owns reposettings.json while SettingsStore owns general app settings.
class RepoSettingsStore:
    """Persist durable repository and local project metadata outside auth-coupled settings."""

    # Prepares the platform config path without touching the file until load/save requires it.
    def __init__(self) -> None:
        self.config_path = app_config_path() / "reposettings.json"

    # Returns an empty but fully-shaped repository settings payload.
    def defaults(self) -> dict[str, Any]:
        """Return the default repository settings payload."""

        return {
            "schema_version": REPO_SETTINGS_SCHEMA_VERSION,
            "managed_repositories": {},
            "active_repository_by_account": {},
            "repository_categories": {},
            "local_projects": [],
            "local_project_categories": [],
            "sync_chains": [],
        }

    # Converts raw JSON into the sanitized registry shape used by the app.
    def clean(self, raw_settings: Any) -> dict[str, Any]:
        """Return sanitized repository settings from raw JSON data."""

        return clean_registry_settings(raw_settings)

    # Loads reposettings.json and rewrites it into the current sanitized shape.
    def load(self) -> dict[str, Any]:
        """Return durable repository settings from reposettings.json."""

        with APP_STORAGE_LOCK:
            if not self.config_path.exists():
                return self.defaults()

            try:
                with self.config_path.open("r", encoding="utf-8") as settings_file:
                    raw_settings = json.load(settings_file)
            except OSError as error:
                raise AppError("Unable to read repository settings.", "REPO_SETTINGS_READ_FAILED") from error
            except json.JSONDecodeError:
                backup_path = self.preserve_invalid_json()
                settings = self.recovered_settings_from_backup(backup_path) or self.defaults()
                if registry_has_metadata(settings):
                    mark_backup_recovered(backup_path)
                self.write(settings)
                return settings

            settings = self.clean(raw_settings)
            settings = self.recover_invalid_backup_settings(settings)
            if raw_settings != settings:
                self.write(settings)
            return settings

    # Recovers sanitized metadata from one malformed backup when the JSON object is still extractable.
    def recovered_settings_from_backup(self, backup_path: Path) -> dict[str, Any] | None:
        """Return sanitized settings recovered from one invalid backup path."""

        raw_settings = load_recoverable_json(backup_path)
        if raw_settings is None:
            return None
        settings = self.clean(raw_settings)
        return settings if registry_has_metadata(settings) else None

    # Imports preserved invalid backups once so prior recoverable metadata is not stranded.
    def recover_invalid_backup_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Return settings merged with any recoverable invalid backup metadata."""

        recovered_settings = settings
        for backup_path in invalid_json_backup_candidates(self.config_path):
            backup_settings = self.recovered_settings_from_backup(backup_path)
            if backup_settings is None:
                continue
            recovered_settings = self.clean(
                merge_recovered_registry_settings(recovered_settings, backup_settings)
            )
            mark_backup_recovered(backup_path)
        return recovered_settings

    # Preserves malformed repository settings before the app recreates a clean registry.
    def preserve_invalid_json(self) -> Path:
        """Copy invalid reposettings.json to a sibling backup file and return that backup path."""

        backup_path = invalid_json_backup_path(self.config_path)
        try:
            atomic_write_private_bytes(backup_path, self.config_path.read_bytes(),
                                       REPO_SETTINGS_DIRECTORY_MODE, REPO_SETTINGS_FILE_MODE)
        except OSError as error:
            raise AppError(
                "Repository settings are not valid JSON and could not be backed up.",
                "REPO_SETTINGS_INVALID_JSON",
            ) from error
        return backup_path

    # Writes the repository registry with owner-only permissions.
    def write(self, settings: dict[str, Any]) -> None:
        """Persist sanitized repository settings to reposettings.json."""

        saved_settings = self.clean(settings)
        try:
            atomic_write_private_json(
                self.config_path,
                saved_settings,
                REPO_SETTINGS_DIRECTORY_MODE,
                REPO_SETTINGS_FILE_MODE,
            )
        except OSError as error:
            raise AppError("Unable to save repository settings.", "REPO_SETTINGS_WRITE_FAILED") from error

    # Saves only repository-registry keys and returns the complete sanitized registry.
    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Persist repository setting updates and return the complete registry."""

        with APP_STORAGE_LOCK:
            settings = self.load()
            for key in (
                "managed_repositories",
                "active_repository_by_account",
                "repository_categories",
                "local_projects",
                "local_project_categories",
                "sync_chains",
            ):
                if key in updates:
                    settings[key] = updates[key]
            self.write(settings)
            return self.clean(settings)

    # Migrates old settings.json repository keys into reposettings.json without duplicating records.
    def migrate_from_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Merge legacy settings.json repository metadata into reposettings.json."""

        with APP_STORAGE_LOCK:
            if not isinstance(settings, dict):
                return self.load()

            current = self.load()
            merged = merge_legacy_registry_settings(current, settings)
            if merged != current:
                self.write(merged)
            return merged

    # Returns a user-facing path for diagnostics without exposing credentials.
    def location(self) -> str:
        """Return the absolute path to the repository settings file."""

        return str(self.config_path)
