"""Repo Mode destination handoff for completed working-tree Sync Chain edges."""

from __future__ import annotations

from typing import Any

from gitdesk.managedrepos import repository_settings_update


# Builds the destination selection and fresh Repo Mode state after a repository-to-repository mirror.
def destination_repository_handoff(
    controller: Any,
    settings: dict[str, Any],
    context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return destination settings updates and the fresh state needed to open Repo Mode Overview."""

    account_login = str(context["destination_account_login"])
    destination_path = str(context["destination_path"])
    summary = controller.git_service.repository_summary(destination_path)
    updates = {
        **repository_settings_update(settings, account_login, summary),
        "active_account": account_login,
        "workspace_mode": "repo",
    }
    handoff = {
        "account_login": account_login,
        "destination_label": str(context["destination_label"]),
        "repository": summary,
        "status": controller.git_service.status(destination_path),
        "branches": controller.git_service.branches(destination_path),
    }
    return updates, handoff
