"""Durable Project Hub timeline events for successful Local Mode lifecycle actions."""

from __future__ import annotations

# Paths provide factual version names while typed payloads document bridge contracts.
from pathlib import Path
from typing import Any

# Project Hub owns timestamp formatting, sanitization, and bounded timeline history.
from gitdesk import projecthub


# Prepends one or more lifecycle events to the bounded Project Hub timeline in a settings update.
def lifecycle_update(
    settings: dict[str, Any],
    updates: dict[str, Any],
    events: list[dict[str, str]],
) -> dict[str, Any]:
    """Return updates containing the new lifecycle events and all prior timeline history."""

    timeline = [*events, *(settings.get("project_timeline") or [])]
    return {**updates, "project_timeline": timeline[:projecthub.MAX_TIMELINE_EVENTS]}


# Records the project, initial feature, and initial version created by one successful Local Mode action.
def project_creation_update(
    settings: dict[str, Any],
    updates: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Return settings updates containing factual new-project hierarchy events."""

    project = result["project"]
    feature = result["feature"]
    version = result["version"]
    events = [
        projecthub.timeline_event(
            "version_created", f"Created {version['name']}", "Initial project version created.",
            project["path"], feature["path"], version["path"], "success",
        ),
        projecthub.timeline_event(
            "feature_created", f"Created {feature['name']}", "Initial project feature created.",
            project["path"], feature["path"], version["path"], "success",
        ),
        projecthub.timeline_event(
            "project_created", f"Created {project['name']}", "Local Mode project created.",
            project["path"], feature["path"], version["path"], "success",
        ),
    ]
    return lifecycle_update(settings, updates, events)


# Records one successful feature creation and its initial physical version.
def feature_creation_update(
    settings: dict[str, Any],
    updates: dict[str, Any],
    project_path: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Return settings updates containing new-feature and initial-version events."""

    feature = result["feature"]
    version = result["version"]
    events = [
        projecthub.timeline_event(
            "version_created", f"Created {version['name']}", "Initial feature version created.",
            project_path, feature["path"], version["path"], "success",
        ),
        projecthub.timeline_event(
            "feature_created", f"Created {feature['name']}", "Local Mode feature created.",
            project_path, feature["path"], version["path"], "success",
        ),
    ]
    return lifecycle_update(settings, updates, events)


# Records one successful next-version duplication without counting copied files as edits.
def version_creation_update(
    settings: dict[str, Any],
    updates: dict[str, Any],
    project_path: str,
    feature_path: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """Return settings updates containing one factual version-created event."""

    detail = f"Duplicated from {Path(result['source']).name}; moved {len(result['moved_paths'])} selected paths."
    event = projecthub.timeline_event(
        "version_created",
        f"Created {Path(result['target']).name}",
        detail,
        project_path,
        feature_path,
        result["target"],
        "success",
    )
    return lifecycle_update(settings, updates, [event])
