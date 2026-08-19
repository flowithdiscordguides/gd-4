"""Exact Git metadata recovery for app-cloned repositories damaged by interrupted sync transactions."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
from typing import Any

from git import GitCommandError, Repo

from gitdesk.errors import AppError
from gitdesk.gitauth import git_auth_environment
from gitdesk.gitops import normalize_repository_path, open_repository, origin_remote_url
from gitdesk.giturls import normalize_github_clone_url, parse_github_remote
from gitdesk.synctransaction import git_metadata_exists, recover_destination_transaction


# Confirms a temporary metadata clone belongs to the exact managed GitHub repository record.
def validate_repair_clone(repo: Repo, owner: str, repository: str) -> None:
    """Reject metadata cloned from any remote other than the saved repository identity."""

    remote = parse_github_remote(origin_remote_url(repo))
    if remote["owner"].lower() != owner.lower() or remote["repo"].lower() != repository.lower():
        raise AppError("Cloned recovery metadata does not match the saved repository.", "REPOSITORY_REPAIR_MISMATCH")


# Restores only .git from the saved origin; existing working-tree files are never replaced.
def repair_cloned_repository_metadata(
    path_value: str,
    record: dict[str, Any],
    auth_login: str | None,
) -> dict[str, str]:
    """Restore missing Git metadata for an exact app-cloned managed repository."""

    repository_path = normalize_repository_path(path_value)
    recover_destination_transaction(str(repository_path))
    try:
        repaired = open_repository(str(repository_path))
        repaired.close()
        return {"path": str(repository_path), "method": "transaction_recovery"}
    except AppError as error:
        if error.code != "REPOSITORY_INVALID":
            raise

    if git_metadata_exists(repository_path):
        raise AppError(
            "The repository has Git metadata, but it is unreadable and was not overwritten.",
            "REPOSITORY_METADATA_CORRUPT",
        )

    owner = str(record.get("owner") or "").strip()
    repository = str(record.get("repo") or "").strip()
    if record.get("source") != "cloned" or not owner or not repository:
        raise AppError(
            "Git metadata can only be restored automatically for a repository cloned by GitDesk.",
            "REPOSITORY_REPAIR_UNAVAILABLE",
        )

    clone_url = normalize_github_clone_url(f"https://github.com/{owner}/{repository}.git")
    temporary_path = Path(tempfile.mkdtemp(prefix=".gitdesk-repair-", dir=str(repository_path.parent)))
    cloned_repo = None
    try:
        cloned_repo = Repo.clone_from(clone_url, temporary_path, env=git_auth_environment(auth_login))
        validate_repair_clone(cloned_repo, owner, repository)
        cloned_repo.close()
        cloned_repo = None
        (temporary_path / ".git").rename(repository_path / ".git")
        repaired = open_repository(str(repository_path))
        repaired.close()
        return {"path": str(repository_path), "method": "origin_clone"}
    except GitCommandError as error:
        raise AppError(
            "Git could not restore the cloned repository metadata from its saved GitHub origin.",
            "REPOSITORY_REPAIR_CLONE_FAILED",
        ) from error
    except OSError as error:
        raise AppError(
            "GitDesk could not install the recovered repository metadata.",
            "REPOSITORY_REPAIR_INSTALL_FAILED",
        ) from error
    finally:
        if cloned_repo is not None:
            cloned_repo.close()
        shutil.rmtree(temporary_path, ignore_errors=True)
