"""Bridge handler for factual Git and Local Mode Project Activity."""

from __future__ import annotations

from datetime import date
from typing import Any, Callable

from gitdesk import activity_tracker
from gitdesk import localactivity


# Keeps activity scanning out of the central bridge controller and Project Hub state refresh.
def activity_tracker_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return the native action used to load factual project activity."""

    return {"projectActivity": lambda payload: handle_project_activity(controller, payload)}


# Persists a stable first-use boundary once, then returns the requested activity range.
def handle_project_activity(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return aggregated activity for known Local Mode and managed Repo Mode projects."""

    settings = controller.settings_store.load()
    current_day = date.today()
    first_use = activity_tracker.recover_first_use_date(
        settings.get("activity_tracker_started_on"),
        [controller.settings_store.config_path, controller.settings_store.repo_settings_store.config_path],
        current_day,
    )
    if settings.get("activity_tracker_started_on") != first_use.isoformat():
        settings = controller.settings_store.save({"activity_tracker_started_on": first_use.isoformat()})
    payload = activity_tracker.activity_snapshot(
        settings,
        payload.get("preset"),
        payload.get("start"),
        first_use,
        current_day,
    )
    return localactivity.enrich_activity(
        settings,
        payload,
        controller.settings_store.config_path,
        current_day,
    )
