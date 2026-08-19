"""Native bridge workflow for category-folder settings and whole-project migration."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from gitdesk.dialogs import choose_directory
from gitdesk.errors import AppError
from gitdesk import localactivity
from gitdesk import localcategoryfolders
from gitdesk import localcategoryscan
from gitdesk import localprojects
from gitdesk import sharedresources
from gitdesk import syncchain_lifecycle
from gitdesk.syncignore_store import SyncIgnoreStore


# Keeps category-folder actions isolated from the Local Mode bridge file-size ceiling.
def local_category_folder_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for the preference, candidate list, and Apply workflow."""

    return {
        "categoryFolderSettingsState": lambda payload: handle_category_folder_state(controller, payload),
        "saveCreateCategoriesAsFolders": lambda payload: handle_save_category_folder_setting(controller, payload),
        "applyCategoryFolderMigration": lambda payload: handle_apply_category_folder_migration(controller, payload),
        "scanLocalCategories": lambda payload: handle_scan_local_categories(controller, payload),
    }


# Prefers a favorite parent's canonical categories child when opening the scan picker.
def category_scan_initial_path(path_value: Any) -> str:
    """Return the best existing folder at which to open the native category scan dialog."""

    initial_path = Path(str(path_value or "").strip()).expanduser()
    if not str(path_value or "").strip():
        return ""
    categories_path = initial_path / localcategoryscan.CATEGORY_CONTAINER_NAME
    if initial_path.name != localcategoryscan.CATEGORY_CONTAINER_NAME and categories_path.is_dir():
        return str(categories_path)
    return str(initial_path)


# Opens the categories-folder picker and reconciles only private metadata after read-only discovery.
def handle_scan_local_categories(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Scan one selected categories folder, or return cancellation without changing metadata."""

    initial_path = category_scan_initial_path(payload.get("initial_path"))
    selected_path = choose_directory(initial_path, "Choose the categories folder to scan")
    if not selected_path:
        return {"cancelled": True}
    return localcategoryscan.reconcile_category_scan(controller, selected_path)


# Returns the current preference and live migration candidates.
def handle_category_folder_state(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return category-folder User settings state."""

    settings = controller.settings_store.load()
    return {
        "settings": settings,
        "migration": localcategoryfolders.category_folder_migration_state(settings),
    }


# Persists only an explicit boolean preference and returns the matching migration list.
def handle_save_category_folder_setting(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Save whether future Local Mode projects should use category folders."""

    settings = controller.settings_store.save({
        "create_categories_as_folders": payload.get("enabled") is True,
    })
    return {
        "settings": settings,
        "migration": localcategoryfolders.category_folder_migration_state(settings),
    }


# Converts one completed plan into a JSON-safe response record.
def moved_project_result(plan: dict[str, Any]) -> dict[str, str]:
    """Return the source, target, project name, and category for a completed move."""

    return {
        "name": plan["name"],
        "category": plan["category"],
        "source": plan["source"],
        "target": plan["target"],
    }


# Restores private path registries and physical folders in reverse completion order.
def rollback_completed_moves(
    completed: list[dict[str, Any]],
    activity_store: Any,
    sync_ignore_store: SyncIgnoreStore,
    original_sync_ignore: dict[str, Any],
) -> list[str]:
    """Reverse completed migration work and return any rollback error messages."""

    rollback_errors = []
    for completed_move in reversed(completed):
        plan = completed_move["plan"]
        source = plan["source_path"]
        target = plan["target_path"]
        if completed_move["activity_remapped"]:
            try:
                activity_store.remap_paths(target, source)
            except Exception as error:
                rollback_errors.append(f"Local Activity {target}: {error}")
        if completed_move["resources_remapped"]:
            try:
                sharedresources.remap_installations(target, source)
            except Exception as error:
                rollback_errors.append(f"Shared Resources {target}: {error}")
        try:
            localcategoryfolders.rollback_project_root(plan, completed_move["created_folders"])
        except Exception as error:
            rollback_errors.append(f"Project folder {target}: {error}")
    try:
        sync_ignore_store.write(original_sync_ignore)
    except Exception as error:
        rollback_errors.append(f"Sync Ignore registry: {error}")
    return rollback_errors


# Raises the original structured error, or converts an unexpected failure into a safe migration error.
def raise_migration_error(error: Exception) -> None:
    """Raise a structured error for a failed migration whose rollback completed."""

    if isinstance(error, AppError):
        raise error
    raise AppError(
        "GitDesk could not complete the selected category-folder migration.",
        "CATEGORY_FOLDER_MIGRATION_FAILED",
    ) from error


# Applies a preflighted batch as one logical migration with compensating rollback.
def handle_apply_category_folder_migration(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Move selected complete project roots and remap every dependent private path."""

    settings = controller.settings_store.load()
    if settings.get("create_categories_as_folders") is not True:
        raise AppError(
            "Turn on Create categories as folders before moving existing projects.",
            "CATEGORY_FOLDER_SETTING_DISABLED",
        )

    plans = localcategoryfolders.project_migration_plans(settings, payload.get("project_paths"))
    working_settings = dict(settings)
    completed = []
    save_started = False
    activity_store = localactivity.activity_store(controller.settings_store.config_path)
    sync_ignore_path = Path(controller.settings_store.config_path).with_name("sync-ignore.json")
    sync_ignore_store = SyncIgnoreStore(sync_ignore_path)
    original_sync_ignore = sync_ignore_store.load()
    try:
        for plan in plans:
            source = Path(plan["source"])
            target = Path(plan["target"])
            completed_move = {
                "plan": plan,
                "created_folders": localcategoryfolders.move_project_root(plan),
                "resources_remapped": False,
                "activity_remapped": False,
            }
            completed.append(completed_move)
            sharedresources.remap_installations(source, target)
            completed_move["resources_remapped"] = True
            activity_store.remap_paths(source, target)
            completed_move["activity_remapped"] = True
            sync_ignore_store.remap_project_path(source, target)

            updates = localprojects.remap_settings_paths(working_settings, source, target)
            updates["workspace_mode"] = working_settings.get("workspace_mode", "repo")
            updates["sync_chains"] = syncchain_lifecycle.remap_project_chains(
                working_settings,
                source,
                target,
            )
            updates["local_projects"] = localcategoryfolders.mark_project_category_foldered(
                updates["local_projects"],
                target,
            )
            working_settings.update(updates)

        save_started = True
        saved_settings = controller.settings_store.save(working_settings)
    except Exception as error:
        rollback_errors = rollback_completed_moves(
            completed,
            activity_store,
            sync_ignore_store,
            original_sync_ignore,
        )
        if save_started:
            try:
                controller.settings_store.save(settings)
            except Exception as restore_error:
                rollback_errors.append(f"settings: {restore_error}")
        if rollback_errors:
            raise AppError(
                "Category-folder migration failed and GitDesk could not completely restore every moved path.",
                "CATEGORY_FOLDER_ROLLBACK_FAILED",
                {"rollback_errors": rollback_errors},
            ) from error
        raise_migration_error(error)

    return {
        "moved": [moved_project_result(plan) for plan in plans],
        "settings": saved_settings,
        "local": localprojects.local_projects_state(saved_settings),
        "migration": localcategoryfolders.category_folder_migration_state(saved_settings),
    }
