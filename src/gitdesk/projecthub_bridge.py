"""Bridge handlers for Project Hub state, import, timeline, and backup workflows."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk.authrecovery import settings_with_token_accounts
from gitdesk.dialogs import choose_directory
from gitdesk import projecthub


# Project Hub handlers are registered with BridgeController without growing its core class.
def project_hub_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for Project Hub workflows."""

    return {
        "projectHubState": lambda payload: handle_project_hub_state(controller, payload),
        "chooseExistingProject": lambda payload: handle_choose_existing_project(controller, payload),
        "scanExistingProject": lambda payload: handle_scan_existing_project(controller, payload),
        "importExistingProject": lambda payload: handle_import_existing_project(controller, payload),
        "exportProjectHubSettings": lambda payload: handle_export_project_hub_settings(controller, payload),
        "importProjectHubSettings": lambda payload: handle_import_project_hub_settings(controller, payload),
        "repairMissingProjects": lambda payload: handle_repair_missing_projects(controller, payload),
    }


# Returns Project Hub state from sanitized settings and filesystem-derived Local Mode state.
def handle_project_hub_state(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return the current Project Hub payload."""

    settings = settings_with_token_accounts(controller.settings_store, controller.token_store)
    return {"settings": settings, "hub": projecthub.project_hub_state(settings)}


# Opens a folder picker for importing an existing local project.
def handle_choose_existing_project(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Return a selected project folder path, or an empty path when cancelled."""

    initial_path = str(payload.get("initial_path") or "")
    return {"path": choose_directory(initial_path, "Choose existing project folder")}


# Scans an existing folder without registering it.
def handle_scan_existing_project(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return a non-mutating import scan for the requested project path."""

    return projecthub.scan_existing_project(str(payload.get("project_path") or ""))


# Registers an existing folder as a Local Mode project and records a timeline event.
def handle_import_existing_project(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Import an existing project folder into Project Hub."""

    settings = controller.settings_store.load()
    updates = projecthub.import_existing_project(settings, str(payload.get("project_path") or ""))
    saved_settings = controller.settings_store.save(updates)
    return {"settings": saved_settings, "hub": projecthub.project_hub_state(saved_settings)}


# Exports non-secret project metadata as a JSON string the frontend can copy.
def handle_export_project_hub_settings(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return a non-secret Project Hub settings backup."""

    settings = settings_with_token_accounts(controller.settings_store, controller.token_store)
    return projecthub.export_project_hub_settings(settings)


# Imports non-secret project metadata from a previous Project Hub export.
def handle_import_project_hub_settings(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Import Project Hub settings from a JSON string."""

    updates = projecthub.import_project_hub_settings(str(payload.get("json") or ""))
    saved_settings = controller.settings_store.save(updates)
    return {"settings": saved_settings, "hub": projecthub.project_hub_state(saved_settings)}


# Removes stale saved project records whose folders no longer exist.
def handle_repair_missing_projects(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Remove missing local project records from settings."""

    settings = controller.settings_store.load()
    updates = projecthub.repair_missing_projects(settings)
    updates.update(
        projecthub.timeline_update(
            {**settings, **updates},
            projecthub.timeline_event(
                "projects_repaired",
                "Repaired project index",
                "Missing project folders were removed from the Project Hub index.",
                status="success",
            ),
        )
    )
    saved_settings = controller.settings_store.save(updates)
    return {"settings": saved_settings, "hub": projecthub.project_hub_state(saved_settings)}
