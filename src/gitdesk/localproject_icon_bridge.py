"""Native bridge actions for reading, choosing, validating, saving, and clearing Local Mode project icons."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk.dialogs import choose_file
from gitdesk import localproject_icons
from gitdesk import localprojects


# Image suffixes are passed to native pickers for discoverability; backend validation remains authoritative.
PROJECT_ICON_PATTERNS = tuple(f"*{suffix}" for suffix in localproject_icons.ICON_MIME_TYPES)


# Keeps project-icon actions isolated from the already-full Local Mode bridge module.
def local_project_icon_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for reading previews and changing active-project icon metadata."""

    return {
        "chooseLocalProjectIcon": lambda payload: handle_choose_local_project_icon(controller, payload),
        "clearLocalProjectIcon": lambda payload: handle_clear_local_project_icon(controller, payload),
        "localProjectIconPreviews": lambda payload: handle_local_project_icon_previews(controller),
    }


# Returns canonical settings and derived Local Mode state after an icon action.
def icon_response(controller: Any, settings: dict[str, Any], cancelled: bool = False) -> dict[str, Any]:
    """Return the standard Local Mode response plus whether the native picker was cancelled."""

    return {
        "settings": settings,
        "local": localprojects.local_projects_state(settings),
        "cancelled": cancelled,
    }


# Opens inside the active project and persists only a validated in-project image path.
def handle_choose_local_project_icon(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Choose and save artwork for the requested or active Local Mode project."""

    settings = controller.settings_store.load()
    project_path = str(payload.get("project_path") or settings.get("active_local_project") or "")
    selected_path = choose_file(
        project_path,
        "Choose a project icon from this project folder",
        PROJECT_ICON_PATTERNS,
    )
    if not selected_path:
        return icon_response(controller, settings, True)
    updates = localproject_icons.local_project_icon_update(settings, project_path, selected_path)
    return icon_response(controller, controller.settings_store.save(updates))


# Clears only the saved override so automatic app artwork or the packaged folder can resume.
def handle_clear_local_project_icon(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Remove custom artwork metadata for the requested or active Local Mode project."""

    settings = controller.settings_store.load()
    project_path = str(payload.get("project_path") or settings.get("active_local_project") or "")
    updates = localproject_icons.local_project_icon_update(settings, project_path, "")
    return icon_response(controller, controller.settings_store.save(updates))


# Reads validated custom or current-version previews only when All Projects asks for its visual library.
def handle_local_project_icon_previews(controller: Any) -> dict[str, list[dict[str, str]]]:
    """Return safe priority-resolved artwork previews for all saved Local Mode projects."""

    settings = controller.settings_store.load()
    return {"projects": localproject_icons.project_icon_previews(settings.get("local_projects"))}
