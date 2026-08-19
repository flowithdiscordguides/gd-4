"""Bridge handlers for GitDesk Local Mode physical folder versioning."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from gitdesk.dialogs import choose_directory
from gitdesk import localfeatures
from gitdesk import localactivity
from gitdesk import localactivity_lifecycle
from gitdesk import localcategoryfolders
from gitdesk import localpermissions
from gitdesk.localcategory_bridge import local_category_folder_handlers
from gitdesk.localnote_bridge import local_note_handlers
from gitdesk.localproject_icon_bridge import local_project_icon_handlers
from gitdesk.localproject_selection_bridge import local_project_selection_handlers
from gitdesk.localversion_bridge import local_version_handlers
from gitdesk import localprojects
from gitdesk import localversions
from gitdesk.reposettings import clean_category_name
from gitdesk import sharedresources
from gitdesk import syncchains
from gitdesk import syncchain_lifecycle
from gitdesk.syncignore_store import SyncIgnoreStore


# Local project handlers are plugged into BridgeController without growing the main class.
def local_project_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for Local Mode project and version workflows."""

    return {
        **local_category_folder_handlers(controller),
        **local_note_handlers(controller),
        **local_project_icon_handlers(controller),
        **local_project_selection_handlers(controller),
        **local_version_handlers(controller),
        "localProjectsState": lambda payload: handle_local_projects_state(controller, payload),
        "requestLocalModePermissions": lambda payload: handle_request_local_mode_permissions(controller, payload),
        "saveWorkspaceMode": lambda payload: handle_save_workspace_mode(controller, payload),
        "chooseLocalParent": lambda payload: handle_choose_local_parent(controller, payload),
        "saveLocalParentFavorite": lambda payload: handle_save_local_parent_favorite(controller, payload),
        "createLocalProject": lambda payload: handle_create_local_project(controller, payload),
        "removeLocalProject": lambda payload: handle_remove_local_project(controller, payload),
        "setLocalProjectCategory": lambda payload: handle_set_local_project_category(controller, payload),
        "createLocalFeature": lambda payload: handle_create_local_feature(controller, payload),
        "renameLocalProject": lambda payload: handle_rename_local_project(controller, payload),
        "selectLocalFeature": lambda payload: handle_select_local_feature(controller, payload),
        "selectLocalVersion": lambda payload: handle_select_local_version(controller, payload),
        "localVersionTree": lambda payload: handle_local_version_tree(controller, payload),
        "duplicateLocalVersion": lambda payload: handle_duplicate_local_version(controller, payload),
        "nameLocalV1Version": lambda payload: handle_name_local_v1_version(controller, payload),
    }


# Returns the current Local Mode settings and filesystem-derived version lists.
def handle_local_projects_state(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return Local Mode state for the frontend."""

    settings = controller.settings_store.load()
    return {
        "settings": settings,
        "local": localprojects.local_projects_state(settings),
    }


# Verifies saved-folder access and atomically activates Local Mode after every permission check succeeds.
def handle_request_local_mode_permissions(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Verify Local Mode folder permission, activate the workspace, and return refreshed state."""

    settings = controller.settings_store.load()
    updates = localpermissions.local_permission_settings_update(settings)
    verified_paths = updates.pop("local_permission_verified_paths", [])
    missing_paths = updates.pop("local_permission_missing_paths", [])
    updates["workspace_mode"] = "local"
    saved_settings = controller.settings_store.save(updates)
    return {
        "settings": saved_settings,
        "local": localprojects.local_projects_state(saved_settings),
        "permissions": {
            "verified": verified_paths,
            "missing": missing_paths,
            "app_version": localpermissions.LOCAL_PERMISSION_CURRENT_VERSION,
        },
    }


# Saves the active workspace mode while limiting values to Repo, Local, or Media.
def handle_save_workspace_mode(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist the selected workspace mode without scanning Local Mode folders."""

    mode = localprojects.clean_workspace_mode(payload.get("mode"))
    settings = controller.settings_store.save({"workspace_mode": mode})
    return {"settings": settings}


# Opens the native folder picker for Local Mode project parent selection.
def handle_choose_local_parent(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Return a selected local parent folder path, or an empty path when cancelled."""

    initial_path = str(payload.get("initial_path") or "")
    return {"path": choose_directory(initial_path, "Choose local project parent folder")}


# Saves a validated Local Mode parent folder as a quick-access favorite.
def handle_save_local_parent_favorite(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist one local project parent favorite and return refreshed Local Mode state."""

    settings = controller.settings_store.load()
    updates = localprojects.local_parent_favorite_update(settings, str(payload.get("path") or ""))
    saved_settings = controller.settings_store.save(updates)
    return {"settings": saved_settings, "local": localprojects.local_projects_state(saved_settings)}


# Creates a project folder, creates 01 init/v1 project-name, copies starter files, and saves it active.
def handle_create_local_project(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a Local Mode project and return authoritative state for that project."""

    resources = payload.get("shared_resources") or payload.get("ai_categories") or []
    if not isinstance(resources, list):
        resources = []
    current_settings = controller.settings_store.load()
    category = clean_category_name(payload.get("category"))
    if current_settings.get("create_categories_as_folders") is True:
        localcategoryfolders.validate_new_project_destination(
            payload.get("parent_path"),
            category,
            payload.get("name"),
            current_settings,
        )
    result = localprojects.create_local_project(
        str(payload.get("parent_path") or ""),
        str(payload.get("name") or ""),
        [str(resource) for resource in resources],
        category,
        current_settings.get("create_categories_as_folders") is True,
    )
    updates = localprojects.local_project_settings_update(
        current_settings,
        result["project"]["path"],
        result["feature"]["path"],
        result["version"]["path"],
        category,
        result["project"].get("category_foldered") is True,
    )
    updates = localactivity_lifecycle.project_creation_update(current_settings, updates, result)
    settings = controller.settings_store.save(updates)
    selection = localprojects.local_project_selection_state(
        settings,
        result["project"]["path"],
        [result["feature"]],
    )
    return {"created": result, "settings": settings, "local_selection": selection}


# Removes a local project from the app registry without deleting any folders.
def handle_remove_local_project(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Remove one Local Mode project record and return refreshed state."""

    settings = controller.settings_store.load()
    updates = localprojects.remove_local_project_settings(
        settings,
        str(payload.get("project_path") or ""),
    )
    remaining_paths = {record["path"] for record in updates["local_projects"]}
    updates["sync_chains"] = syncchain_lifecycle.remove_project_chains(settings, remaining_paths)
    saved_settings = controller.settings_store.save(updates)
    return {"settings": saved_settings, "local": localprojects.local_projects_state(saved_settings)}


# Assigns a category label to one saved Local Mode project.
def handle_set_local_project_category(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Update a Local Mode project category label."""

    settings = controller.settings_store.load()
    updates = localprojects.local_project_category_update(
        settings,
        str(payload.get("project_path") or ""),
        clean_category_name(payload.get("category")),
    )
    saved_settings = controller.settings_store.save(updates)
    return {"settings": saved_settings, "local": localprojects.local_projects_state(saved_settings)}


# Creates a new feature folder from the active/latest prior version.
def handle_create_local_feature(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a Local Mode feature and return refreshed state."""

    resources = payload.get("shared_resources") or payload.get("ai_categories") or []
    if not isinstance(resources, list):
        resources = []
    settings = controller.settings_store.load()
    project_path = str(payload.get("project_path") or settings.get("active_local_project") or "")
    source_version_path = str(payload.get("source_version_path") or settings.get("active_local_version") or "")
    result = localfeatures.create_local_feature(
        project_path,
        str(payload.get("name") or ""),
        [str(resource) for resource in resources],
        source_version_path,
    )
    updates = localprojects.local_project_settings_update(
        settings,
        project_path,
        result["feature"]["path"],
        result["version"]["path"],
    )
    updates = localactivity_lifecycle.feature_creation_update(settings, updates, project_path, result)
    saved_settings = controller.settings_store.save(updates)
    return {"created": result, "settings": saved_settings, "local": localprojects.local_projects_state(saved_settings)}


# Renames the selected project folder and updates every saved path rooted inside it.
def handle_rename_local_project(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Rename the active Local Mode project folder and return refreshed state."""

    settings = controller.settings_store.load()
    project_path = str(payload.get("project_path") or settings.get("active_local_project") or "")
    result = localprojects.rename_local_project(settings, project_path, str(payload.get("name") or ""))
    sharedresources.remap_installations(Path(result["source"]), Path(result["target"]))
    result["updates"]["sync_chains"] = syncchain_lifecycle.remap_project_chains(
        settings,
        Path(result["source"]),
        Path(result["target"]),
    )
    localactivity.activity_store(controller.settings_store.config_path).remap_paths(
        Path(result["source"]), Path(result["target"])
    )
    sync_ignore_path = Path(controller.settings_store.config_path).with_name("sync-ignore.json")
    SyncIgnoreStore(sync_ignore_path).remap_project_path(result["source"], result["target"])
    saved_settings = controller.settings_store.save(result["updates"])
    return {"renamed": result, "settings": saved_settings, "local": localprojects.local_projects_state(saved_settings)}


# Selects a feature folder under the active local project.
def handle_select_local_feature(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Select one Local Mode feature and its latest available version."""

    settings = controller.settings_store.load()
    project_path = str(payload.get("project_path") or settings.get("active_local_project") or "")
    feature = choose_feature(project_path, payload.get("feature_path"), settings)
    version_path = choose_version(feature, payload.get("version_path"), settings)
    settings = controller.settings_store.save(
        localprojects.local_project_settings_update(
            settings,
            project_path,
            feature["path"] if feature else "",
            version_path,
        )
    )
    return {"settings": settings, "local": localprojects.local_projects_state(settings)}


# Selects one version folder under the active local feature.
def handle_select_local_version(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Select a physical version folder for Local Mode actions."""

    settings = controller.settings_store.load()
    project_path = str(payload.get("project_path") or settings.get("active_local_project") or "")
    feature_path = str(payload.get("feature_path") or settings.get("active_local_feature") or "")
    version_path = str(payload.get("version_path") or "")
    settings = controller.settings_store.save(
        localprojects.local_project_settings_update(settings, project_path, feature_path, version_path)
    )
    return {"settings": settings, "local": localprojects.local_projects_state(settings)}


# Returns the checkbox tree used by duplicate-with-cleanup.
def handle_local_version_tree(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return a cleanup-selection tree for the requested local version."""

    settings = controller.settings_store.load()
    version_path = str(payload.get("version_path") or settings.get("active_local_version") or "")
    return localversions.local_version_tree(version_path, settings.get("local_cleanup_paths", []))


# Duplicates the active version and saves selected move paths as the next cleanup preset.
def handle_duplicate_local_version(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Duplicate a local version using copy for unchecked paths and move for checked paths."""

    settings = controller.settings_store.load()
    source_path = str(payload.get("source_path") or settings.get("active_local_version") or "")
    move_paths = payload.get("move_paths") or []
    if not isinstance(move_paths, list):
        move_paths = []
    result = localversions.duplicate_local_version(source_path, str(payload.get("label") or ""), move_paths)
    target_path = Path(result["target"])
    updates = localprojects.local_project_settings_update(
        settings,
        str(settings.get("active_local_project") or ""),
        str(target_path.parent),
        result["target"],
    )
    updates["local_cleanup_paths"] = localversions.clean_cleanup_paths(move_paths)
    updates = localactivity_lifecycle.version_creation_update(
        settings,
        updates,
        str(settings.get("active_local_project") or ""),
        str(target_path.parent),
        result,
    )
    saved_settings = controller.settings_store.save(updates)
    return {
        "duplicate": result,
        "settings": saved_settings,
        "local": localprojects.local_projects_state(saved_settings),
    }


# Renames a legacy selected v1 folder to include the active project name.
def handle_name_local_v1_version(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Rename a bare v1 local version folder and return refreshed state."""

    settings = controller.settings_store.load()
    project_path = Path(str(payload.get("project_path") or settings.get("active_local_project") or ""))
    source_path = str(payload.get("version_path") or settings.get("active_local_version") or "")
    result = localversions.rename_bare_v1_to_project(source_path, project_path.name)
    sharedresources.remap_installations(Path(result["source"]), Path(result["target"]))
    updates = localprojects.remap_settings_paths(settings, Path(result["source"]), Path(result["target"]))
    working_settings = {**settings, **updates}
    updates.update(localprojects.local_project_settings_update(
        working_settings,
        str(working_settings.get("active_local_project") or project_path),
        str(Path(result["target"]).parent),
        result["target"],
    ))
    localactivity.activity_store(controller.settings_store.config_path).remap_paths(
        Path(result["source"]), Path(result["target"])
    )
    saved_settings = controller.settings_store.save(updates)
    return {"renamed": result, "settings": saved_settings, "local": localprojects.local_projects_state(saved_settings)}


# Matches a possibly stale path string against current feature or version records.
def path_matches(candidate_path: Any, saved_path: str) -> bool:
    """Return whether a frontend/backend path value resolves to a saved path."""

    try:
        return str(Path(str(candidate_path or "")).expanduser().resolve()) == saved_path
    except OSError:
        return False


# Chooses a feature from the requested path, saved settings, init fallback, or first feature.
def choose_feature(
    project_path: str,
    requested_path: Any,
    settings: dict[str, Any],
    available_features: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return the feature record that should become active for a project."""

    features = available_features if available_features is not None else localfeatures.list_features(project_path)
    candidates = [requested_path, settings.get("active_local_feature")]
    for candidate in candidates:
        for feature in features:
            if path_matches(candidate, feature["path"]):
                return feature
    for feature in features:
        if feature["name"] == localfeatures.INIT_FEATURE_NAME:
            return feature
    return features[0] if features else None


# Chooses a version from the requested path, saved settings, or latest feature version.
def choose_version(feature: dict[str, Any] | None, requested_path: Any, settings: dict[str, Any]) -> str:
    """Return the version path that should become active for a selected feature."""

    versions = feature.get("versions", []) if feature else []
    candidates = [requested_path, settings.get("active_local_version")]
    for candidate in candidates:
        for version in versions:
            if path_matches(candidate, version["path"]):
                return version["path"]
    return versions[-1]["path"] if versions else ""
