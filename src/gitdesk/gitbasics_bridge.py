"""Bridge handlers for Project Hub Git safety and branch basics."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk import gitbasics
from gitdesk import projecthub


# Registers Git safety handlers without expanding BridgeController itself.
def git_basic_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for safety snapshots, restore, branches, stashes, and tags."""

    return {
        "listStashes": lambda payload: handle_list_stashes(controller, payload),
        "createSafetyStash": lambda payload: handle_create_safety_stash(controller, payload),
        "applyStash": lambda payload: handle_apply_stash(controller, payload),
        "restoreFiles": lambda payload: handle_restore_files(controller, payload),
        "renameBranch": lambda payload: handle_rename_branch(controller, payload),
        "deleteBranch": lambda payload: handle_delete_branch(controller, payload),
        "listTags": lambda payload: handle_list_tags(controller, payload),
    }


# Reads current stash entries for recovery UI.
def handle_list_stashes(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return Git stash entries for the active repository."""

    return gitbasics.list_stashes(controller.repository_path_from_payload(payload))


# Creates a stash safety snapshot before risky workflows.
def handle_create_safety_stash(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a safety stash and record the snapshot in Project Hub timeline."""

    path = controller.repository_path_from_payload(payload)
    result = gitbasics.create_safety_stash(path, str(payload.get("reason") or "manual"))
    settings = controller.settings_store.load()
    updates = projecthub.timeline_update(
        settings,
        projecthub.timeline_event(
            "safety_snapshot",
            "Created safety snapshot",
            result.get("message", ""),
            str(settings.get("active_local_project") or ""),
            str(settings.get("active_local_feature") or ""),
            str(settings.get("active_local_version") or ""),
            "success",
        ),
    )
    saved_settings = controller.settings_store.save(updates)
    return {"stash": result, "settings": saved_settings, "hub": projecthub.project_hub_state(saved_settings)}


# Applies a stash without dropping it.
def handle_apply_stash(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Apply a selected stash and return refreshed status."""

    path = controller.repository_path_from_payload(payload)
    result = gitbasics.apply_stash(path, str(payload.get("stash") or ""))
    return {"stash": result, "status": controller.git_service.status(path)}


# Restores selected files and refreshes status.
def handle_restore_files(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Discard selected working-tree changes."""

    files = payload.get("files") or []
    if not isinstance(files, list):
        files = []
    path = controller.repository_path_from_payload(payload)
    result = gitbasics.restore_files(path, [str(file_path) for file_path in files])
    settings = controller.settings_store.load()
    updates = projecthub.timeline_update(
        settings,
        projecthub.timeline_event(
            "files_restored",
            "Restored selected files",
            f"{len(result['restored'])} file path(s) restored.",
            str(settings.get("active_local_project") or ""),
            str(settings.get("active_local_feature") or ""),
            str(settings.get("active_local_version") or ""),
            "warning",
        ),
    )
    saved_settings = controller.settings_store.save(updates)
    return {"restore": result, "status": controller.git_service.status(path), "settings": saved_settings}


# Renames a local branch and refreshes branch data.
def handle_rename_branch(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Rename a local branch."""

    path = controller.repository_path_from_payload(payload)
    result = gitbasics.rename_branch(path, str(payload.get("old_name") or ""), str(payload.get("new_name") or ""))
    return {"rename": result, "branches": controller.git_service.branches(path)}


# Deletes a local branch and refreshes branch data.
def handle_delete_branch(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Delete a local branch."""

    path = controller.repository_path_from_payload(payload)
    result = gitbasics.delete_branch(path, str(payload.get("branch") or ""), bool(payload.get("force", False)))
    return {"delete": result, "branches": controller.git_service.branches(path)}


# Lists local tags for releases and history flows.
def handle_list_tags(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return local Git tags for the active repository."""

    return gitbasics.list_tags(controller.repository_path_from_payload(payload))
