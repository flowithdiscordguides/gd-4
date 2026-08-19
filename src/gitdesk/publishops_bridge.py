"""Bridge handlers for Project Hub publish, Pages, and release workflows."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk import projecthub, publishops
from gitdesk.errors import AppError
from gitdesk.githubapi import GitHubApiClient
from gitdesk.managedrepos import repository_settings_update


# Publish handlers stay outside BridgeController because they combine GitHub, Git, and Local Mode state.
def publish_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for Project Hub publish workflows."""

    return {
        "promoteVersionToRepo": lambda payload: handle_promote_version_to_repo(controller, payload),
        "publishVersionPages": lambda payload: handle_publish_version_pages(controller, payload),
        "createReleaseForVersion": lambda payload: handle_create_release_for_version(controller, payload),
    }


# Builds the account, GitHub client, owner, repo, and version path shared by publish actions.
def publish_context(controller: Any, payload: dict[str, Any]) -> tuple[dict[str, str], GitHubApiClient, str, str, str]:
    """Return validated shared context for a Project Hub publish request."""

    owner = str(payload.get("owner") or "").strip()
    account = controller.account_for_owner(owner, payload, required=True)
    owner = owner or account["login"]
    client = GitHubApiClient(controller.token_for_account(account))
    repo_name = str(payload.get("repo") or "").strip()
    version_path = str(payload.get("version_path") or "").strip()
    if not version_path:
        raise AppError("Select a local version before publishing.", "PUBLISH_VERSION_REQUIRED")
    return account, client, owner, repo_name, version_path


# Adds the published repository and a timeline event to the saved settings.
def save_publish_result(
    controller: Any,
    account: dict[str, str],
    local_repository: dict[str, Any],
    event: dict[str, Any],
    version_path: str = "",
    status: str = "",
) -> dict[str, Any]:
    """Save repository metadata, optional version status, and timeline history."""

    settings = controller.settings_store.load()
    updates = repository_settings_update(settings, account["login"], local_repository, "published")
    if status and version_path:
        statuses = dict(settings.get("local_version_statuses") or {})
        statuses[version_path] = status
        updates["local_version_statuses"] = statuses
    updates.update(projecthub.timeline_update({**settings, **updates}, event))
    saved_settings = controller.settings_store.save(updates)
    return {"settings": saved_settings, "hub": projecthub.project_hub_state(saved_settings)}


# Promotes a local version folder into a GitHub repository and marks it as the active managed repo.
def handle_promote_version_to_repo(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create or reuse a GitHub repository, commit the version folder, and push it."""

    account, client, owner, repo_name, version_path = publish_context(controller, payload)
    result = publishops.promote_version_to_repo(
        version_path,
        owner,
        repo_name,
        bool(payload.get("private", False)),
        account,
        client,
        controller.git_service,
    )
    state = save_publish_result(
        controller,
        account,
        result["local_repository"],
        projecthub.timeline_event(
            "version_promoted",
            "Promoted version to GitHub",
            f"{owner}/{repo_name} is now connected to this local version.",
            version_path=version_path,
            status="success",
        ),
        version_path,
        "current",
    )
    return {"publish": result, **state}


# Publishes a local version through GitHub Pages and stores the repository as managed.
def handle_publish_version_pages(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Configure Pages for a local version and push the generated workflow."""

    account, client, owner, repo_name, version_path = publish_context(controller, payload)
    result = publishops.publish_version_pages(
        version_path,
        owner,
        repo_name,
        bool(payload.get("private", False)),
        str(payload.get("branch") or ""),
        str(payload.get("source_folder") or "/"),
        str(payload.get("page_file") or "index.html"),
        account,
        client,
        controller.git_service,
    )
    state = save_publish_result(
        controller,
        account,
        result["local_repository"],
        projecthub.timeline_event(
            "pages_published",
            "Published version to Pages",
            f"{owner}/{repo_name} has a Pages workflow for this version.",
            version_path=version_path,
            status="success",
        ),
        version_path,
        "published",
    )
    return {"publish": result, **state}


# Creates a GitHub release for the selected version and marks the version as published.
def handle_create_release_for_version(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a GitHub release tied to a Project Hub local version."""

    account, client, owner, repo_name, version_path = publish_context(controller, payload)
    release = payload.get("release") or {}
    if not isinstance(release, dict):
        raise AppError("Release payload must be a JSON object.", "RELEASE_PAYLOAD_INVALID")
    result = publishops.create_release_for_version(owner, repo_name, version_path, release, client)
    settings = controller.settings_store.load()
    statuses = dict(settings.get("local_version_statuses") or {})
    if version_path:
        statuses[version_path] = "published"
    updates = {
        "local_version_statuses": statuses,
        **projecthub.timeline_update(
            settings,
            projecthub.timeline_event(
                "release_created",
                "Created GitHub release",
                f"{owner}/{repo_name} release {result.get('tag_name', '')} was created.",
                version_path=version_path,
                status="success",
            ),
        ),
    }
    saved_settings = controller.settings_store.save(updates)
    return {"release": result, "settings": saved_settings, "hub": projecthub.project_hub_state(saved_settings)}
