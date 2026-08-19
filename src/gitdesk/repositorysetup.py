"""Repository creation and registration helpers for GitDesk."""

from __future__ import annotations

# Standard-library imports provide filesystem paths and typed payloads for repository setup.
from pathlib import Path
from typing import Any

# GitDesk modules provide Shared Resources, GitHub setup, Git initialization, and remote configuration.
from gitdesk.cloneops import normalize_clone_parent
from gitdesk.errors import AppError
from gitdesk.githubapi import GitHubApiClient
from gitdesk.gitidentity import configure_repository_identity
from gitdesk.gitops import GitService, initialize_repository
from gitdesk.giturls import normalize_clone_folder_name
from gitdesk.publishops import ensure_origin_remote
from gitdesk import sharedresources


# Reads metadata for a user-selected Git repository without changing the working tree.
def existing_repository_summary(git_service: GitService, path_value: str) -> dict[str, Any]:
    """Return repository metadata for an existing local Git repository."""

    return git_service.repository_summary(path_value)


# Installs selected Shared Resources into a newly created repository folder.
def copy_ai_categories(category_names: list[str], target_path: Path) -> int:
    """Merge Shared Resources into a new repository and return the copied file count."""

    copied_files = 0
    for category_name in category_names:
        result = sharedresources.install_resource(str(category_name or ""), str(target_path))
        copied_files += int(result.get("file_count") or 0)
    return copied_files


# Builds and validates the folder that will receive a new Git repository.
def resolve_new_repository_target(parent_path: str, folder_name: str) -> Path:
    """Return an empty or absent child folder suitable for repository initialization."""

    destination_parent = normalize_clone_parent(parent_path)
    local_folder = normalize_clone_folder_name(folder_name)
    target_path = (destination_parent / local_folder).resolve()

    if target_path.parent != destination_parent:
        raise AppError("New repository must stay inside the selected parent folder.", "REPOSITORY_TARGET_INVALID")
    if target_path.exists() and not target_path.is_dir():
        raise AppError("New repository target already exists and is not a folder.", "REPOSITORY_TARGET_INVALID")
    if target_path.exists() and any(target_path.iterdir()):
        raise AppError("New repository target folder already exists and is not empty.", "REPOSITORY_TARGET_NOT_EMPTY")
    return target_path


# Creates the GitHub repository, then creates/configures the matching local checkout folder.
def create_new_repository(
    git_service: GitService,
    parent_path: str,
    folder_name: str,
    account: dict[str, Any] | None = None,
    github_client: GitHubApiClient | None = None,
    owner: str = "",
    repo_name: str = "",
    private: bool = False,
    ai_categories: list[str] | None = None,
) -> dict[str, Any]:
    """Create a GitHub repository and matching local Git repository."""

    target_path = resolve_new_repository_target(parent_path, folder_name)
    selected_resources = sharedresources.validate_resource_selection(ai_categories or [])
    if github_client is None:
        raise AppError("Create New requires a GitHub account token.", "GITHUB_ACCOUNT_REQUIRED")

    remote_owner = str(owner or (account or {}).get("login") or "").strip()
    remote_name = str(repo_name or target_path.name).strip()
    github_repository = github_client.create_repository(remote_owner, remote_name, private)

    target_path.mkdir(parents=True, exist_ok=True)
    repo = initialize_repository(str(target_path))
    configure_repository_identity(repo, account)
    ensure_origin_remote(repo, str(github_repository.get("clone_url") or ""))

    copied_resource_files = copy_ai_categories(selected_resources, target_path)
    return {
        "repository": git_service.repository_summary(str(target_path)),
        "github_repository": github_repository,
        "copied_shared_resource_files": copied_resource_files,
        "copied_ai_files": copied_resource_files,
    }
