"""Feature-neutral bridge handlers for Local Mode version comparison and copying."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk import localprojects, projecthub, versioncompare


# Registers comparison actions independently from Project Hub so Local Mode owns the frontend workflow.
def version_compare_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return native actions for comparing and copying local versions."""

    return {
        "compareLocalVersions": lambda payload: handle_compare_local_versions(payload),
        "copyComparedVersionFiles": lambda payload: handle_copy_compared_version_files(controller, payload),
    }


# Compares two validated version folders without modifying either folder.
def handle_compare_local_versions(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a folder-to-folder comparison for two local versions."""

    return versioncompare.compare_versions(
        str(payload.get("left_path") or ""),
        str(payload.get("right_path") or ""),
    )


# Copies selected paths and returns fresh Local Mode state after recording the operation.
def handle_copy_compared_version_files(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Copy selected compared files from a source version into a target version."""

    paths = payload.get("paths") or []
    if not isinstance(paths, list):
        paths = []
    result = versioncompare.copy_compared_files(
        str(payload.get("source_path") or ""),
        str(payload.get("target_path") or ""),
        [str(path) for path in paths],
    )
    settings = controller.settings_store.load()
    updates = projecthub.timeline_update(
        settings,
        projecthub.timeline_event(
            "version_files_copied",
            "Copied files between versions",
            f"{len(result['copied'])} file path(s) copied into the target version.",
            str(settings.get("active_local_project") or ""),
            str(settings.get("active_local_feature") or ""),
            result["target"],
            "success",
        ),
    )
    saved_settings = controller.settings_store.save(updates)
    return {
        "copy": result,
        "settings": saved_settings,
        "local": localprojects.local_projects_state(saved_settings),
    }
