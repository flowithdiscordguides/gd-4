"""Latency-sensitive bridge handlers for Local Mode project selection."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk import localprojects


# Keeps the acknowledgement path separate from the read-only hierarchy refresh that follows it.
def local_project_selection_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for acknowledged and refreshed Local project selection."""

    return {
        "selectLocalProject": lambda payload: handle_select_local_project(controller, payload),
        "localProjectSelectionState": lambda payload: handle_local_project_selection_state(controller, payload),
    }


# Persists only bounded, validated cached paths so the click response never waits for a hierarchy scan.
def handle_select_local_project(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Acknowledge one saved Local project and its cached child selection."""

    project_path = str(payload.get("project_path") or "")
    settings = controller.settings_store.load()
    update = localprojects.local_project_selection_update(
        settings,
        project_path,
        str(payload.get("feature_path") or ""),
        str(payload.get("version_path") or ""),
    )
    settings = controller.settings_store.save(update)
    return {"settings": settings, "local_selection": localprojects.selection_fields(settings)}


# Refreshes one acknowledged selection without putting its hierarchy scan back in the click response.
def handle_local_project_selection_state(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return refreshed state only when the requested project is still active."""

    settings = controller.settings_store.load()
    project_path = str(payload.get("project_path") or "")
    if project_path != str(settings.get("active_local_project") or ""):
        return {"settings": settings, "stale": True}
    return {
        "settings": settings,
        "local_selection": localprojects.local_project_selection_state(settings, project_path),
    }
