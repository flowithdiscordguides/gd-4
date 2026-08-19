"""Non-secret settings storage for the GitDesk desktop application."""

from __future__ import annotations

# Standard-library JSON, path, and typing helpers sanitize private settings.
import json
from pathlib import Path
from typing import Any

# GitDesk cleaners validate each owned settings domain before persistence.
from gitdesk.accounts import account_credential_configured, clean_account_metadata
from gitdesk.aiskills import clean_category_selection
from gitdesk.editor_preferences import clean_editor_preferences, default_editor_preferences
from gitdesk.errors import AppError
from gitdesk.localpermissions import clean_local_permission_grants
from gitdesk.localprojects import clean_local_parent_favorites, clean_local_project_list, clean_workspace_mode
from gitdesk.localversions import clean_cleanup_paths
from gitdesk.managedrepos import clean_active_repository_map, clean_repository_map, migrate_legacy_repository
from gitdesk.reposettings import RepoSettingsStore
from gitdesk.reposettings_recovery import invalid_json_backup_candidates, invalid_json_backup_path
from gitdesk.reposettings_recovery import load_recoverable_json, mark_backup_recovered
from gitdesk.settings_preferences import DATE_SETTINGS, clean_date_setting, clean_theme_colors
from gitdesk.settings_preferences import default_theme_colors
from gitdesk.storage import APP_STORAGE_LOCK, app_config_path, atomic_write_private_bytes, atomic_write_private_json
from gitdesk.syncchains import clean_sync_chains
from gitdesk.theme_gradients import clean_theme_gradients, default_theme_gradients
from gitdesk.theme_profiles import clean_theme_profiles

# Settings are intentionally limited to non-secret values; PATs live in the operating system credential store.
DEFAULT_SETTINGS: dict[str, Any] = {
    "repository_path": "",
    "github_owner": "",
    "github_repo": "",
    "active_account": "",
    "github_accounts": [],
    "managed_repositories": {},
    "active_repository_by_account": {},
    "repository_categories": {},
    "active_ai_skill_categories": [],
    "workspace_mode": "repo",
    "theme_colors": default_theme_colors(),
    "theme_gradients": default_theme_gradients(),
    "theme_profiles": [],
    "editor_preferences": default_editor_preferences(),
    "create_categories_as_folders": False,
    "local_projects": [],
    "local_project_categories": [],
    "sync_chains": [],
    "local_parent_favorites": [],
    "active_local_project": "",
    "active_local_feature": "",
    "active_local_version": "",
    "local_cleanup_paths": [],
    "local_permission_grants": {},
    "local_permission_app_version": "",
    "local_version_statuses": {},
    "project_timeline": [],
    "activity_tracker_started_on": "",
}
STRING_SETTINGS = {
    "repository_path",
    "github_owner",
    "github_repo",
    "active_account",
    "active_local_project",
    "active_local_feature",
    "active_local_version",
}

# These durable non-secret registry keys live in reposettings.json, not auth-coupled settings.json.
REPOSITORY_SETTING_KEYS = {
    "managed_repositories",
    "active_repository_by_account",
    "repository_categories",
    "local_projects",
    "local_project_categories",
    "sync_chains",
}

SETTINGS_DIRECTORY_MODE = 0o700

SETTINGS_FILE_MODE = 0o600

VERSION_STATUS_VALUES = {"current", "archived", "published"}

MAX_PROJECT_TIMELINE_EVENTS = 250


# Cleans the persisted account list so malformed settings cannot poison account selection.
def clean_account_list(value: Any) -> list[dict[str, Any]]:
    """Return valid non-secret GitHub account metadata loaded from settings."""

    if not isinstance(value, list):
        return []

    accounts = []
    seen_logins = set()
    for raw_account in value:
        account = clean_account_metadata(raw_account)
        account_key = account["login"].lower() if account else ""
        if account and account_key not in seen_logins:
            accounts.append(account)
            seen_logins.add(account_key)
    return accounts


# Cleans saved version-state badges without requiring version folders to exist.
def clean_local_version_statuses(value: Any) -> dict[str, str]:
    """Return valid local version status values keyed by version path."""

    if not isinstance(value, dict):
        return {}

    statuses = {}
    for raw_path, raw_status in value.items():
        path = str(raw_path or "").strip()
        status = str(raw_status or "").strip()
        if path and status in VERSION_STATUS_VALUES:
            statuses[path] = status
    return statuses


# Cleans one Project Hub timeline entry loaded from disk or import JSON.
def clean_timeline_event(value: Any) -> dict[str, str] | None:
    """Return a sanitized Project Hub timeline event, or None for malformed values."""

    if not isinstance(value, dict):
        return None

    title = str(value.get("title") or "").strip()
    if not title:
        return None
    return {
        "timestamp": str(value.get("timestamp") or "").strip()[:40],
        "type": str(value.get("type") or "event").strip()[:64],
        "title": title[:160],
        "detail": str(value.get("detail") or "").strip()[:320],
        "project_path": str(value.get("project_path") or "").strip(),
        "feature_path": str(value.get("feature_path") or "").strip(),
        "version_path": str(value.get("version_path") or "").strip(),
        "status": str(value.get("status") or "info").strip()[:32],
    }


# Keeps timeline imports bounded and drops malformed entries.
def clean_project_timeline(value: Any) -> list[dict[str, str]]:
    """Return a bounded list of valid Project Hub timeline events."""

    if not isinstance(value, list):
        return []

    events = []
    for raw_event in value:
        event = clean_timeline_event(raw_event)
        if event:
            events.append(event)
    return events[:MAX_PROJECT_TIMELINE_EVENTS]


# Keeps persisted account data to the minimum needed to recover identity defaults after restart.
def persistable_account_metadata(account: dict[str, Any]) -> dict[str, Any]:
    """Return the minimal account metadata shape written to the settings file."""

    return {
        "login": account["login"],
        "id": str(account.get("id") or "").strip(),
        "authenticated_login": str(account.get("authenticated_login") or account["login"]).strip(),
        "resource_owner_type": str(account.get("resource_owner_type") or "User").strip(),
        "credential_configured": account_credential_configured(account),
        "token_expires_at": str(account.get("token_expires_at") or "").strip(),
    }


# SettingsStore reads and writes non-secret UI preferences in the current user's config directory.
class SettingsStore:
    """Persist non-secret application settings outside source-controlled files."""

    # Prepares the platform-specific config path without creating files until a save is requested.
    def __init__(self) -> None:
        self.config_path = app_config_path() / "settings.json"
        self.repo_settings_store = RepoSettingsStore()

    # Extracts only the keys owned by reposettings.json from a complete settings dictionary.
    def repository_payload(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Return the repository-registry subset of a complete settings dictionary."""

        return {key: settings.get(key, DEFAULT_SETTINGS[key]) for key in REPOSITORY_SETTING_KEYS}

    # Preserves a malformed settings file before replacing it with a recovered or clean payload.
    def preserve_invalid_json(self) -> Path:
        """Return the backup path containing the current unreadable settings file."""

        backup_path = invalid_json_backup_path(self.config_path)
        try:
            atomic_write_private_bytes(
                backup_path,
                self.config_path.read_bytes(),
                SETTINGS_DIRECTORY_MODE,
                SETTINGS_FILE_MODE,
            )
        except OSError as error:
            raise AppError(
                "Application settings are invalid and could not be preserved.",
                "SETTINGS_INVALID_JSON",
            ) from error
        return backup_path

    # Loads normal settings JSON or salvages the first complete object from a preserved malformed file.
    def load_raw_settings(self) -> dict[str, Any]:
        """Return a recoverable raw settings object without blocking repository metadata loading."""

        if not self.config_path.exists():
            return self.recover_invalid_backup_settings({})
        preserved_invalid = False
        try:
            with self.config_path.open("r", encoding="utf-8") as settings_file:
                loaded_settings = json.load(settings_file)
        except OSError as error:
            raise AppError("Unable to read application settings.", "SETTINGS_READ_FAILED") from error
        except json.JSONDecodeError:
            self.preserve_invalid_json()
            preserved_invalid = True
            loaded_settings = {}

        # Valid non-object JSON cannot provide settings, but repository metadata must still remain available.
        if not isinstance(loaded_settings, dict):
            if not preserved_invalid:
                self.preserve_invalid_json()
            loaded_settings = {}
        return self.recover_invalid_backup_settings(loaded_settings)

    # Imports preserved settings backups once, filling only values absent from the current settings file.
    def recover_invalid_backup_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Return current settings enriched by recoverable invalid backup values."""

        recovered_settings = dict(settings)
        for backup_path in invalid_json_backup_candidates(self.config_path):
            backup_settings = load_recoverable_json(backup_path)
            if backup_settings is None:
                continue
            for key, value in backup_settings.items():
                if key not in recovered_settings or not recovered_settings[key]:
                    recovered_settings[key] = value
            mark_backup_recovered(backup_path)
        return recovered_settings

    # Builds the minimized non-secret object that is allowed to persist in settings.json.
    def persistable_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Return the owner-only settings.json payload without repository registry fields."""

        saved_settings = {
            key: value
            for key, value in settings.items()
            if key not in REPOSITORY_SETTING_KEYS
        }
        saved_settings["github_accounts"] = [
            persistable_account_metadata(account)
            for account in settings["github_accounts"]
        ]
        return saved_settings

    # Loads settings from disk and fills missing keys with safe defaults.
    def load(self) -> dict[str, Any]:
        """Return the current settings dictionary with defaults for missing values."""

        with APP_STORAGE_LOCK:
            raw_settings = self.load_raw_settings()

            settings = dict(DEFAULT_SETTINGS)
            for key, value in raw_settings.items():
                if key in REPOSITORY_SETTING_KEYS:
                    continue
                if key in STRING_SETTINGS:
                    settings[key] = str(value or "")
                elif key in DATE_SETTINGS:
                    settings[key] = clean_date_setting(value)
                elif key == "github_accounts":
                    settings[key] = clean_account_list(value)
                elif key == "active_ai_skill_categories":
                    settings[key] = clean_category_selection(value)
                elif key == "workspace_mode":
                    settings[key] = clean_workspace_mode(value)
                elif key == "theme_colors":
                    settings[key] = clean_theme_colors(value)
                elif key == "theme_gradients":
                    settings[key] = clean_theme_gradients(value)
                elif key == "theme_profiles":
                    settings[key] = clean_theme_profiles(value)
                elif key == "editor_preferences": settings[key] = clean_editor_preferences(value)
                elif key == "create_categories_as_folders":
                    settings[key] = value is True
                elif key == "local_cleanup_paths":
                    settings[key] = clean_cleanup_paths(value)
                elif key == "local_parent_favorites":
                    settings[key] = clean_local_parent_favorites(value)
                elif key == "local_permission_grants":
                    settings[key] = clean_local_permission_grants(value)
                elif key == "local_permission_app_version":
                    settings[key] = str(value or "")
                elif key == "local_version_statuses":
                    settings[key] = clean_local_version_statuses(value)
                elif key == "project_timeline":
                    settings[key] = clean_project_timeline(value)
            settings.update(self.repo_settings_store.migrate_from_settings(raw_settings))
            settings = migrate_legacy_repository(settings)
            repository_settings = self.repo_settings_store.clean(self.repository_payload(settings))
            settings.update(repository_settings)
            if raw_settings != self.persistable_settings(settings):
                self.write_settings_file(settings)
            return settings

    # Writes minimized settings with owner-only permissions for local privacy protection.
    def write_settings_file(self, settings: dict[str, Any]) -> None:
        """Persist sanitized settings without storing unnecessary account metadata."""

        saved_settings = self.persistable_settings(settings)

        try:
            atomic_write_private_json(
                self.config_path,
                saved_settings,
                SETTINGS_DIRECTORY_MODE,
                SETTINGS_FILE_MODE,
            )
        except OSError as error:
            raise AppError("Unable to save application settings.", "SETTINGS_WRITE_FAILED") from error

    # Saves only known non-secret settings so arbitrary frontend payload keys cannot be persisted.
    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Persist allowed setting updates and return the complete saved settings object."""

        with APP_STORAGE_LOCK:
            settings = self.load()
            for key in STRING_SETTINGS:
                if key in updates:
                    settings[key] = str(updates[key] or "")
            for key in DATE_SETTINGS:
                if key in updates:
                    settings[key] = clean_date_setting(updates[key])
            if "github_accounts" in updates:
                settings["github_accounts"] = clean_account_list(updates["github_accounts"])
            if "managed_repositories" in updates:
                settings["managed_repositories"] = clean_repository_map(updates["managed_repositories"])
            if "active_repository_by_account" in updates:
                settings["active_repository_by_account"] = clean_active_repository_map(
                    updates["active_repository_by_account"],
                    settings["managed_repositories"],
                )
            if "repository_categories" in updates:
                settings["repository_categories"] = updates["repository_categories"]
            if "active_ai_skill_categories" in updates:
                settings["active_ai_skill_categories"] = clean_category_selection(
                    updates["active_ai_skill_categories"]
                )
            if "workspace_mode" in updates:
                settings["workspace_mode"] = clean_workspace_mode(updates["workspace_mode"])
            if "theme_colors" in updates:
                settings["theme_colors"] = clean_theme_colors(updates["theme_colors"])
            if "theme_gradients" in updates:
                settings["theme_gradients"] = clean_theme_gradients(updates["theme_gradients"])
            if "theme_profiles" in updates:
                settings["theme_profiles"] = clean_theme_profiles(updates["theme_profiles"])
            if "editor_preferences" in updates:
                settings["editor_preferences"] = clean_editor_preferences(updates["editor_preferences"])
            if "create_categories_as_folders" in updates:
                settings["create_categories_as_folders"] = updates["create_categories_as_folders"] is True
            if "local_projects" in updates:
                settings["local_projects"] = clean_local_project_list(updates["local_projects"])
            if "local_project_categories" in updates:
                settings["local_project_categories"] = updates["local_project_categories"]
            if "sync_chains" in updates:
                settings["sync_chains"] = clean_sync_chains(updates["sync_chains"])
            if "local_parent_favorites" in updates:
                settings["local_parent_favorites"] = clean_local_parent_favorites(
                    updates["local_parent_favorites"]
                )
            if "local_permission_grants" in updates:
                settings["local_permission_grants"] = clean_local_permission_grants(
                    updates["local_permission_grants"]
                )
            if "local_permission_app_version" in updates:
                settings["local_permission_app_version"] = str(updates["local_permission_app_version"] or "")
            if "local_cleanup_paths" in updates:
                settings["local_cleanup_paths"] = clean_cleanup_paths(updates["local_cleanup_paths"])
            if "local_version_statuses" in updates:
                settings["local_version_statuses"] = clean_local_version_statuses(updates["local_version_statuses"])
            if "project_timeline" in updates:
                settings["project_timeline"] = clean_project_timeline(updates["project_timeline"])

            if any(key in updates for key in REPOSITORY_SETTING_KEYS):
                repository_settings = self.repo_settings_store.save(self.repository_payload(settings))
                settings.update(repository_settings)
            self.write_settings_file(settings)
            return settings

    # Returns a user-facing path so the settings location can be inspected without exposing secrets.
    def location(self) -> str:
        """Return the absolute path to the non-secret settings file."""

        return str(self.config_path)
