"""Native bridge actions for opening and permanently deleting Local Mode versions."""

from __future__ import annotations

from pathlib import Path
import shutil
from typing import Any, Callable
from uuid import uuid4

from gitdesk.errors import AppError
from gitdesk import localactivity
from gitdesk import localfeatures
from gitdesk import localprojects
from gitdesk import localversions
from gitdesk.localproject_records import clean_local_project_list
from gitdesk.sharedresource_store import SharedResourceStore
from gitdesk.storage import APP_STORAGE_LOCK


# Keeps destructive and native-opening version actions outside the near-limit project bridge.
def local_version_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return native actions for opening and deleting physical Local Mode versions."""

    return {
        "deleteLocalVersion": lambda payload: handle_delete_local_version(controller, payload),
        "openLocalVersionFolder": lambda payload: handle_open_local_folder(controller, payload),
        "openLocalVersionInVSCode": lambda payload: handle_open_local_vscode(controller, payload),
    }


# Reads a requested version path before falling back to the saved active version.
def active_local_version(controller: Any, payload: dict[str, Any]) -> str:
    """Return the requested or saved active local version path."""

    settings = controller.settings_store.load()
    return str(payload.get("version_path") or settings.get("active_local_version") or "")


# Opens the selected local version in the platform file manager.
def handle_open_local_folder(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Open the selected local version folder."""

    return localversions.open_local_folder(active_local_version(controller, payload))


# Opens the selected local version in the saved code editor.
def handle_open_local_vscode(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Open the selected local version folder in the chosen code editor."""

    settings = controller.settings_store.load()
    return localversions.open_local_vscode(
        str(payload.get("version_path") or settings.get("active_local_version") or ""),
        settings.get("editor_preferences"),
    )


# Compares possibly stale metadata with one canonical physical version path.
def path_matches(candidate: Any, version_path: Path) -> bool:
    """Return whether candidate resolves to version_path."""

    try:
        return Path(str(candidate or "")).expanduser().resolve() == version_path
    except (OSError, RuntimeError):
        return False


# Preflights ownership and prepares the selection that remains after deletion.
def version_deletion_plan(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Return validated paths and settings updates for one version deletion."""

    project_path = localfeatures.normalize_project_directory(
        payload.get("project_path") or settings.get("active_local_project"),
    )
    saved_project = next(
        (
            record
            for record in clean_local_project_list(settings.get("local_projects"))
            if path_matches(record["path"], project_path)
        ),
        None,
    )
    if not saved_project:
        raise AppError("Select a saved local project first.", "LOCAL_PROJECT_NOT_FOUND")
    feature_path = localfeatures.normalize_feature_directory(
        project_path,
        payload.get("feature_path") or settings.get("active_local_feature"),
    )
    version_path = localfeatures.validate_version_for_feature(
        project_path,
        feature_path,
        payload.get("version_path"),
    )
    versions = localversions.list_versions(
        str(feature_path),
        "LOCAL_FEATURE_PATH_EMPTY",
        "LOCAL_FEATURE_PATH_INVALID",
    )
    remaining = [version for version in versions if not path_matches(version["path"], version_path)]
    active_version = next(
        (
            version["path"]
            for version in remaining
            if path_matches(settings.get("active_local_version"), Path(version["path"]))
        ),
        remaining[-1]["path"] if remaining else "",
    )
    updates = localprojects.local_project_settings_update(
        settings,
        str(project_path),
        str(feature_path),
        active_version,
    )
    updates["local_version_statuses"] = {
        path: status
        for path, status in (settings.get("local_version_statuses") or {}).items()
        if not path_matches(path, version_path)
    }
    return {
        "project_path": project_path,
        "feature_path": feature_path,
        "version_path": version_path,
        "updates": updates,
    }


# Restores every reversible surface when deletion cannot finish.
def rollback_version_deletion(
    controller: Any,
    plan: dict[str, Any],
    staging_path: Path,
    original_settings: dict[str, Any],
    settings_attempted: bool,
    resource_store: SharedResourceStore,
    resource_records: dict[str, Any] | None,
    activity_store: Any,
    activity_snapshot: dict[str, Any] | None,
) -> list[str]:
    """Restore the physical version and private metadata, returning rollback errors."""

    errors = []
    version_path = plan["version_path"]
    try:
        if staging_path.exists() and not version_path.exists():
            staging_path.rename(version_path)
    except OSError as error:
        errors.append(f"version folder: {error}")
    if not version_path.exists():
        errors.append("version folder could not be restored")
        return errors
    if settings_attempted:
        try:
            controller.settings_store.save(original_settings)
        except Exception as error:
            errors.append(f"settings: {error}")
    try:
        resource_store.restore_version_installations(str(version_path), resource_records or {})
    except Exception as error:
        errors.append(f"Shared Resources: {error}")
    try:
        activity_store.restore_version_snapshot(str(version_path), activity_snapshot)
    except Exception as error:
        errors.append(f"Local Activity: {error}")
    return errors


# Permanently removes one validated version folder and its live private metadata.
def handle_delete_local_version(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Delete one physical version and return the refreshed Local Mode state."""

    with APP_STORAGE_LOCK:
        return delete_local_version_locked(controller, payload)


# Performs the physical and private-metadata transaction while all app storage is isolated from background scans.
def delete_local_version_locked(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Delete one version while the shared private-storage transaction lock is held."""

    original_settings = controller.settings_store.load()
    plan = version_deletion_plan(original_settings, payload)
    version_path = plan["version_path"]
    staging_path = version_path.with_name(f".gitdesk-delete-{uuid4().hex}")
    resource_store = SharedResourceStore()
    activity_store = localactivity.activity_store(controller.settings_store.config_path)
    resource_records = None
    activity_snapshot = None
    settings_attempted = False
    try:
        version_path.rename(staging_path)
        resource_records = resource_store.remove_version_installations(str(version_path))
        activity_snapshot = activity_store.remove_version_snapshot(str(version_path))
        settings_attempted = True
        saved_settings = controller.settings_store.save(plan["updates"])
        local_state = localprojects.local_projects_state(saved_settings)
        shutil.rmtree(staging_path)
    except Exception as error:
        rollback_errors = rollback_version_deletion(
            controller,
            plan,
            staging_path,
            original_settings,
            settings_attempted,
            resource_store,
            resource_records,
            activity_store,
            activity_snapshot,
        )
        if rollback_errors:
            raise AppError(
                "Version deletion failed and GitDesk could not completely restore it.",
                "LOCAL_VERSION_DELETE_ROLLBACK_FAILED",
                {"rollback_errors": rollback_errors},
            ) from error
        if isinstance(error, AppError):
            raise error
        raise AppError(
            "GitDesk could not permanently delete the selected version.",
            "LOCAL_VERSION_DELETE_FAILED",
        ) from error
    return {
        "deleted": {"path": str(version_path), "name": version_path.name},
        "settings": saved_settings,
        "local": local_state,
    }
