"""Bridge handlers for account-scoped managed repository workflows."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk.errors import AppError
from gitdesk.githubapi import GitHubApiClient
from gitdesk.githubcatalog import organization_memberships
from gitdesk.managedrepos import repositories_for_account, repository_settings_update
from gitdesk.reposettings import clean_category_name


# Managed repository handlers are plugged into BridgeController without growing the main class.
def managed_repository_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for the managed repository picker and GitHub catalog."""

    return {
        "managedRepositoriesState": lambda payload: managed_repositories_state(controller, payload),
        "listGitHubRepositories": lambda payload: list_github_repositories(controller, payload),
        "selectManagedRepository": lambda payload: select_managed_repository(controller, payload),
        "cloneManagedRepository": lambda payload: clone_managed_repository(controller, payload),
    }


# Returns only repositories belonging to the selected account.
def managed_repositories_state(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return managed repository state for the requested or active account."""

    account = controller.account_from_payload(payload, required=False)
    settings = controller.settings_store.load()
    login = account["login"] if account else ""
    repositories = repositories_for_account(settings, login) if login else []
    return {
        "settings": settings,
        "account_login": login,
        "repositories": repositories,
    }


# Reads the GitHub repository catalog visible to the active account's token.
def list_github_repositories(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return GitHub repositories visible to the selected account."""

    account = controller.account_from_payload(payload, required=True)
    token = controller.token_for_account(account)
    client = GitHubApiClient(token)
    repositories = client.repositories()
    memberships = organization_memberships(client)
    return {
        "account_login": account["login"],
        "repositories": repositories,
        "organizations": memberships["organizations"],
        "organization_access": memberships["access"],
    }


# Switches the app to a managed local repository only when it belongs to the active account.
def select_managed_repository(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Select one account-owned managed repository and return its fresh local state."""

    account = controller.account_from_payload(payload, required=True)
    path = str(payload.get("path") or "").strip()
    settings = controller.settings_store.load()
    if not any(record["path"] == path for record in repositories_for_account(settings, account["login"])):
        raise AppError("That repository is not managed by the active account.", "MANAGED_REPOSITORY_FORBIDDEN")

    repository_state = controller.git_service.repository_selection_state(path)
    summary = repository_state["repository"]
    settings = controller.settings_store.save(repository_settings_update(settings, account["login"], summary))
    return {
        **repository_state,
        "settings": settings,
    }


# Clones a selected GitHub repository and registers it under its exact resource-owner profile.
def clone_managed_repository(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Clone one GitHub repository and add it to the matching resource-owner profile."""

    owner = str(payload.get("repository_owner") or "").strip()
    account = controller.account_for_owner(owner, payload, required=True)
    clone_url = str(payload.get("clone_url") or payload.get("url") or "").strip()
    parent_path = str(payload.get("parent_path") or "").strip()
    folder_name = str(payload.get("folder_name") or "").strip()
    category = clean_category_name(payload.get("category"))
    auth_login = account["login"] if clone_url.startswith("https://") else None
    summary = controller.git_service.clone_repository(clone_url, parent_path, folder_name, auth_login, account)
    updates = repository_settings_update(
        controller.settings_store.load(), account["login"], summary, "cloned", category
    )
    settings = controller.settings_store.save({**updates, "active_account": account["login"]})
    return {
        "auth": controller.auth_state(settings),
        "repository": summary,
        "settings": settings,
        "status": controller.git_service.status(summary["path"]),
        "branches": controller.git_service.branches(summary["path"]),
    }
