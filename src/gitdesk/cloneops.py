"""Repository cloning operations for GitDesk."""

from __future__ import annotations

from pathlib import Path

from git import GitCommandError, Repo

from gitdesk.errors import AppError
from gitdesk.gitauth import git_auth_environment
from gitdesk.giturls import default_clone_folder_name, normalize_clone_folder_name, normalize_github_clone_url


# Resolves and validates the parent directory that will receive the cloned repository folder.
def normalize_clone_parent(parent_path: str) -> Path:
    """Return an existing destination parent directory for clone operations."""

    cleaned_path = str(parent_path or "").strip()
    if not cleaned_path:
        raise AppError("Destination folder is required.", "CLONE_DESTINATION_EMPTY")

    destination_parent = Path(cleaned_path).expanduser().resolve()
    if not destination_parent.exists() or not destination_parent.is_dir():
        raise AppError("Destination folder must be an existing directory.", "CLONE_DESTINATION_INVALID")
    return destination_parent


# Combines the destination parent and local folder name while refusing to overwrite existing work.
def resolve_clone_target(parent_path: str, clone_url: str, folder_name: str) -> Path:
    """Return a safe clone target path that is absent or empty."""

    destination_parent = normalize_clone_parent(parent_path)
    local_folder = (
        normalize_clone_folder_name(folder_name)
        if folder_name.strip()
        else default_clone_folder_name(clone_url)
    )
    target_path = (destination_parent / local_folder).resolve()

    if target_path.parent != destination_parent:
        raise AppError("Clone target must stay inside the destination folder.", "CLONE_TARGET_INVALID")
    if target_path.exists() and not target_path.is_dir():
        raise AppError("Clone target already exists and is not a folder.", "CLONE_TARGET_INVALID")
    if target_path.exists() and any(target_path.iterdir()):
        raise AppError("Clone target folder already exists and is not empty.", "CLONE_TARGET_NOT_EMPTY")
    return target_path


# Clones a GitHub repository through GitPython and returns an opened Repo instance.
def clone_github_repository(
    clone_url: str,
    parent_path: str,
    folder_name: str = "",
    auth_login: str | None = None,
) -> Repo:
    """Clone a GitHub repository into a destination folder and return the cloned repository."""

    normalized_url = normalize_github_clone_url(clone_url)
    target_path = resolve_clone_target(parent_path, normalized_url, folder_name)
    credential_login = auth_login if normalized_url.startswith("https://") else None

    try:
        return Repo.clone_from(normalized_url, target_path, env=git_auth_environment(credential_login))
    except GitCommandError as error:
        raise AppError("Git could not clone the repository.", "GIT_CLONE_FAILED") from error
