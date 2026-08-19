"""Bridge handlers for GitHub release listing, creation, and draft publishing."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk.errors import AppError


# Keeps release-specific GitHub API actions out of the already-large main bridge controller.
def release_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for release management workflows."""

    return {
        "listReleases": lambda payload: handle_list_releases(controller, payload),
        "publishRelease": lambda payload: handle_publish_release(controller, payload),
    }


# Fetches releases for the configured owner/repo pair.
def handle_list_releases(controller: Any, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return GitHub releases for the configured repository."""

    owner, repo = controller.github_pair_from_payload(payload)
    return controller.github_client(payload).releases(owner, repo)


# Creates a new release or publishes an existing draft release through GitHub's release API.
def handle_publish_release(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Publish a new release or update an existing draft release."""

    owner, repo = controller.github_pair_from_payload(payload)
    release = payload.get("release") or {}
    if not isinstance(release, dict):
        raise AppError("Release payload must be a JSON object.", "RELEASE_PAYLOAD_INVALID")

    release_id = release.get("id")
    if release_id:
        try:
            clean_release_id = int(release_id)
        except (TypeError, ValueError) as error:
            raise AppError("A valid release id is required.", "RELEASE_ID_INVALID") from error
        return controller.github_client(payload).update_release(owner, repo, clean_release_id, release)
    return controller.github_client(payload).create_release(owner, repo, release)
