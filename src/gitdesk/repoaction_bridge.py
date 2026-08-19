"""Bridge handlers for repository diff, fetch, and desktop open actions."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk import repoactions


# Keeps repository utility actions out of the main BridgeController class.
def repository_action_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for Overview repository utilities."""

    return {
        "fileDiff": lambda payload: handle_file_diff(controller, payload),
        "ignoreFile": lambda payload: handle_ignore_file(controller, payload),
        "fetch": lambda payload: handle_fetch(controller, payload),
        "syncStatus": lambda payload: handle_sync_status(controller, payload),
        "openInFileManager": lambda payload: handle_open_in_file_manager(controller, payload),
        "openInVSCode": lambda payload: handle_open_in_vscode(controller, payload),
        "openRepositoryOnGitHub": lambda payload: handle_open_on_github(controller, payload),
        "openGitHubUrl": lambda payload: handle_open_github_url(controller, payload),
        "openExternalUrl": lambda payload: handle_open_external_url(controller, payload),
    }


# Returns a unified diff for one selected changed file.
def handle_file_diff(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return a selected file diff after validating the active repository path."""

    return repoactions.file_diff(
        controller.repository_path_from_payload(payload),
        str(payload.get("file_path") or ""),
    )


# Adds one file path to .gitignore and returns refreshed status.
def handle_ignore_file(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Add one changed file path to .gitignore."""

    path = controller.repository_path_from_payload(payload)
    result = repoactions.add_path_to_gitignore(path, str(payload.get("file_path") or ""))
    result["status"] = controller.git_service.status(path)
    return result


# Fetches origin and returns refreshed local status and branches.
def handle_fetch(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Fetch origin for the active repository."""

    path = controller.repository_path_from_payload(payload)
    fetch_result = repoactions.fetch_repository(path, controller.optional_auth_login(payload))
    return {
        "fetch": fetch_result,
        "status": controller.git_service.status(path),
        "branches": controller.git_service.branches(path),
    }


# Returns local ahead/behind state from the latest fetched upstream ref.
def handle_sync_status(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return active branch sync state for the selected repository."""

    return repoactions.sync_status(controller.repository_path_from_payload(payload))


# Opens the active repository folder in the platform file manager.
def handle_open_in_file_manager(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Open the active repository folder in the native file manager."""

    return repoactions.open_in_file_manager(controller.repository_path_from_payload(payload))


# Opens the active repository folder in the saved code editor.
def handle_open_in_vscode(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Open the active repository folder in the selected code editor."""

    preferences = controller.settings_store.load().get("editor_preferences")
    return repoactions.open_in_vscode(controller.repository_path_from_payload(payload), preferences)


# Opens the active repository's GitHub page in the default browser.
def handle_open_on_github(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Open the active repository's GitHub page."""

    return repoactions.open_on_github(controller.repository_path_from_payload(payload))


# Opens an app-provided GitHub URL in the default browser.
def handle_open_github_url(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Open a validated GitHub URL."""

    return repoactions.open_github_url(str(payload.get("url") or ""))


# Opens a validated published-site URL in the user's default browser.
def handle_open_external_url(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Open a validated external website URL."""

    return repoactions.open_external_url(str(payload.get("url") or ""))
