"""Bridge handlers for adding, creating, categorizing, and removing repositories."""

from __future__ import annotations

# Standard-library imports define bridge payload typing and action callables.
from typing import Any, Callable

# GitDesk modules provide native folder selection, GitHub clients, registry updates, and setup helpers.
from gitdesk.dialogs import choose_directory
from gitdesk.githubapi import GitHubApiClient
from gitdesk.managedrepos import remove_repository_settings, repository_category_update
from gitdesk.managedrepos import repository_settings_update
from gitdesk.repositorysetup import create_new_repository, existing_repository_summary
from gitdesk.reposettings import clean_category_name
from gitdesk.syncchain_lifecycle import detach_repository


# Repository setup handlers are separate so the main bridge stays under the project file limit.
def repository_setup_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for repository creation and registry maintenance."""

    return {
        "chooseExistingRepository": lambda payload: handle_choose_existing_repository(controller, payload),
        "addExistingRepository": lambda payload: handle_add_existing_repository(controller, payload),
        "chooseNewRepositoryParent": lambda payload: handle_choose_new_repository_parent(controller, payload),
        "createNewRepository": lambda payload: handle_create_new_repository(controller, payload),
        "removeManagedRepository": lambda payload: handle_remove_managed_repository(controller, payload),
        "setManagedRepositoryCategory": lambda payload: handle_set_managed_repository_category(controller, payload),
    }


# Opens a folder picker for a local repository that should be registered under the active account.
def handle_choose_existing_repository(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return the chosen path and its inferred GitHub remote metadata, or empty values when cancelled."""

    initial_path = str(payload.get("initial_path") or "")
    path = choose_directory(initial_path, "Choose existing Git repository folder")
    if not path:
        return {"path": "", "repository": {}}
    return {
        "path": path,
        "repository": existing_repository_summary(controller.git_service, path),
    }


# Opens a folder picker for the parent folder used by create-new-repository.
def handle_choose_new_repository_parent(controller: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Return the selected parent folder for a new repository, or empty when cancelled."""

    initial_path = str(payload.get("initial_path") or "")
    return {"path": choose_directory(initial_path, "Choose new repository parent folder")}


# Adds an existing local Git repository to the active account without cloning or moving it.
def handle_add_existing_repository(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Register an existing repository under the active account and open it."""

    category = clean_category_name(payload.get("category"))
    summary = existing_repository_summary(controller.git_service, str(payload.get("path") or ""))
    account = controller.account_for_owner(summary.get("github_owner", ""), payload, required=True)
    updates = repository_settings_update(
        controller.settings_store.load(),
        account["login"],
        summary,
        "added",
        category,
    )
    settings = controller.settings_store.save({**updates, "active_account": account["login"]})
    return {
        "auth": controller.auth_state(settings),
        "repository": summary,
        "settings": settings,
        "status": controller.git_service.status(summary["path"]),
        "branches": controller.git_service.branches(summary["path"]),
    }


# Creates a new GitHub repository, creates the matching local folder, and registers it.
def handle_create_new_repository(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a new repository for the active account and open it."""

    owner = str(payload.get("owner") or "").strip()
    account = controller.account_for_owner(owner, payload, required=True)
    category = clean_category_name(payload.get("category"))
    resources = payload.get("shared_resources") or payload.get("ai_categories") or []
    # Malformed frontend payloads are treated as no Shared Resources instead of blocking repository creation.
    if not isinstance(resources, list):
        resources = []
    client = GitHubApiClient(controller.token_for_account(account))
    result = create_new_repository(
        controller.git_service,
        str(payload.get("parent_path") or ""),
        str(payload.get("folder_name") or ""),
        account,
        client,
        owner or account["login"],
        str(payload.get("repo") or ""),
        bool(payload.get("private", False)),
        [str(resource) for resource in resources],
    )
    summary = result["repository"]
    updates = repository_settings_update(
        controller.settings_store.load(),
        account["login"],
        summary,
        "created",
        category,
    )
    settings = controller.settings_store.save({**updates, "active_account": account["login"]})
    return {
        "auth": controller.auth_state(settings),
        "created": result,
        "repository": summary,
        "settings": settings,
        "status": controller.git_service.status(summary["path"]),
        "branches": controller.git_service.branches(summary["path"]),
    }


# Removes one repository from the app registry without deleting its local folder or remote repository.
def handle_remove_managed_repository(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Remove one saved repository record for the active account."""

    account = controller.account_for_repository(payload, required=True)
    current = controller.settings_store.load()
    repository_path = str(payload.get("path") or "")
    updates = remove_repository_settings(current, account["login"], repository_path)
    updates["sync_chains"] = detach_repository(current, account["login"], repository_path)
    settings = controller.settings_store.save(updates)
    return {"settings": settings}


# Assigns a category label to one saved repository record.
def handle_set_managed_repository_category(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Update a managed repository category label."""

    account = controller.account_for_repository(payload, required=True)
    category = clean_category_name(payload.get("category"))
    settings = controller.settings_store.save(
        repository_category_update(
            controller.settings_store.load(),
            account["login"],
            str(payload.get("path") or ""),
            category,
        )
    )
    return {"settings": settings}
