"""Saved Local Mode project authorization for Sync Chain sources."""

from __future__ import annotations

from gitdesk.errors import AppError
from gitdesk.localprojects import clean_local_project_list


def require_saved_project(settings: dict, project_path: str) -> dict[str, str]:
    """Return an exact saved Local Mode project or reject a Finder-only folder."""

    cleaned_path = str(project_path or "").strip()
    project = next(
        (item for item in clean_local_project_list(settings.get("local_projects")) if item["path"] == cleaned_path),
        None,
    )
    if not project:
        raise AppError("Choose a Local Mode project already saved in GitDesk.", "SYNC_PROJECT_NOT_MANAGED")
    return project
