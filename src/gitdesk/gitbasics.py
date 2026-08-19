"""Additional safe Git basics used by Project Hub workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from git import GitCommandError

from gitdesk.errors import AppError
from gitdesk.giterrors import git_error_details, git_failure_message
from gitdesk.gitops import active_branch_name, open_repository, validate_relative_git_path


# Stash messages are prefixed so Project Hub safety snapshots are recognizable in normal Git tools.
SAFETY_STASH_PREFIX = "GitDesk safety snapshot"


# Returns recent stash entries from the selected repository.
def list_stashes(path_value: str) -> dict[str, Any]:
    """Return recent Git stash entries for a repository."""

    repo = open_repository(path_value)
    try:
        output = repo.git.stash("list")
    except GitCommandError as error:
        raise AppError("Git could not list stashes.", "GIT_STASH_LIST_FAILED") from error

    stashes = []
    for line in output.splitlines():
        if not line.strip():
            continue
        name, _, message = line.partition(": ")
        stashes.append({"name": name.strip(), "message": message.strip()})
    return {"stashes": stashes}


# Creates a stash including untracked files before risky pull/publish actions.
def create_safety_stash(path_value: str, reason: str = "") -> dict[str, Any]:
    """Create a Git stash safety snapshot and return the refreshed stash list."""

    repo = open_repository(path_value)
    message = f"{SAFETY_STASH_PREFIX}: {str(reason or 'manual').strip()}"
    try:
        output = repo.git.stash("push", "--include-untracked", "-m", message)
    except GitCommandError as error:
        raise AppError("Git could not create a safety snapshot.", "GIT_STASH_CREATE_FAILED") from error
    return {"message": output, **list_stashes(path_value)}


# Applies a selected stash entry without deleting it so recovery remains possible.
def apply_stash(path_value: str, stash_name: str) -> dict[str, Any]:
    """Apply a stash entry and keep it in the stash list."""

    repo = open_repository(path_value)
    cleaned_name = str(stash_name or "").strip()
    if not cleaned_name.startswith("stash@{"):
        raise AppError("Select a valid stash entry to apply.", "GIT_STASH_INVALID")
    try:
        output = repo.git.stash("apply", cleaned_name)
    except GitCommandError as error:
        message = git_failure_message("Git could not apply the selected stash.", error)
        raise AppError(message, "GIT_STASH_APPLY_FAILED", git_error_details(error)) from error
    return {"message": output}


# Resolves a safe repository-relative path to an absolute working-tree path.
def working_tree_file(root: Path, file_path: str) -> Path:
    """Return an absolute file path inside the repository working tree."""

    safe_path = validate_relative_git_path(file_path)
    candidate = (root / safe_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise AppError("Selected file must stay inside the repository.", "GIT_FILE_PATH_INVALID") from error
    return candidate


# Restores selected tracked files and removes selected untracked files.
def restore_files(path_value: str, file_paths: list[str]) -> dict[str, Any]:
    """Discard selected working-tree file changes."""

    if not file_paths:
        raise AppError("Select at least one file to restore.", "GIT_RESTORE_EMPTY")
    repo = open_repository(path_value)
    root = Path(repo.working_tree_dir or path_value).resolve()
    safe_paths = [validate_relative_git_path(path) for path in file_paths]
    untracked = set(repo.untracked_files)
    tracked_paths = [path for path in safe_paths if path not in untracked]
    untracked_paths = [path for path in safe_paths if path in untracked]

    try:
        if tracked_paths:
            repo.git.restore("--worktree", "--staged", "--", *tracked_paths)
        for relative_path in untracked_paths:
            target = working_tree_file(root, relative_path)
            if target.is_dir():
                raise AppError("Folder restore is not supported for untracked directories.", "GIT_RESTORE_DIR")
            if target.exists():
                target.unlink()
    except AppError:
        raise
    except (GitCommandError, OSError) as error:
        raise AppError("Git could not restore the selected files.", "GIT_RESTORE_FAILED") from error

    return {"restored": safe_paths}


# Renames the active or selected branch using Git's branch command.
def rename_branch(path_value: str, old_name: str, new_name: str) -> dict[str, str]:
    """Rename a local branch and return the new branch name."""

    repo = open_repository(path_value)
    old_branch = str(old_name or active_branch_name(repo)).strip()
    new_branch = str(new_name or "").strip()
    if not old_branch or old_branch == "DETACHED":
        raise AppError("Select a local branch to rename.", "GIT_BRANCH_RENAME_INVALID")
    if not new_branch:
        raise AppError("New branch name is required.", "GIT_BRANCH_RENAME_EMPTY")
    try:
        repo.git.check_ref_format("--branch", new_branch)
        repo.git.branch("-m", old_branch, new_branch)
    except GitCommandError as error:
        message = git_failure_message("Git could not rename the branch.", error)
        raise AppError(message, "GIT_BRANCH_RENAME_FAILED", git_error_details(error)) from error
    return {"old": old_branch, "new": new_branch}


# Deletes a non-active local branch.
def delete_branch(path_value: str, branch_name: str, force: bool = False) -> dict[str, str]:
    """Delete a local branch that is not currently checked out."""

    repo = open_repository(path_value)
    cleaned_name = str(branch_name or "").strip()
    if not cleaned_name:
        raise AppError("Branch name is required.", "GIT_BRANCH_DELETE_EMPTY")
    if cleaned_name == active_branch_name(repo):
        raise AppError("Cannot delete the currently checked-out branch.", "GIT_BRANCH_DELETE_ACTIVE")
    try:
        repo.git.branch("-D" if force else "-d", cleaned_name)
    except GitCommandError as error:
        message = git_failure_message("Git could not delete the branch.", error)
        raise AppError(message, "GIT_BRANCH_DELETE_FAILED", git_error_details(error)) from error
    return {"deleted": cleaned_name}


# Lists local tags for release and timeline workflows.
def list_tags(path_value: str) -> dict[str, list[dict[str, str]]]:
    """Return local Git tags with their target commit when available."""

    repo = open_repository(path_value)
    tags = []
    for tag in repo.tags:
        try:
            target = tag.commit.hexsha
        except ValueError:
            target = ""
        tags.append({"name": tag.name, "target": target})
    return {"tags": sorted(tags, key=lambda item: item["name"].lower())}
