"""Project Hub publishing workflows for local versions, Pages, and releases."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from git import GitCommandError

from gitdesk import pages
from gitdesk.errors import AppError
from gitdesk.githubapi import GitHubApiClient
from gitdesk.giterrors import git_error_details, git_failure_message
from gitdesk.gitidentity import actor_from_account, configure_repository_identity
from gitdesk.gitops import GitService, active_branch_name, open_repository
from gitdesk.localversions import normalize_version_directory


# Initial publish commits need a clear default because local versions may have no Git history yet.
DEFAULT_INITIAL_COMMIT = "Publish current project version"


# Opens a repository at a version path, initializing Git when the folder is still local-only.
def ensure_version_repository(version_path_value: str, account: dict[str, Any] | None) -> Any:
    """Return a Git repository for a local version folder, creating one when needed."""

    version_path = normalize_version_directory(version_path_value)
    try:
        repo = open_repository(str(version_path))
    except AppError as error:
        if error.code != "REPOSITORY_INVALID":
            raise
        repo = GitService().init_repository(str(version_path))
        repo = open_repository(repo["path"])
    configure_repository_identity(repo, account)
    return repo


# Adds or updates the origin remote to point at the GitHub repository selected in Project Hub.
def ensure_origin_remote(repo: Any, clone_url: str) -> None:
    """Ensure the repository origin remote points at the GitHub HTTPS clone URL."""

    if not clone_url:
        raise AppError("GitHub did not return a clone URL for the repository.", "PUBLISH_CLONE_URL_EMPTY")
    try:
        if any(remote.name == "origin" for remote in repo.remotes):
            repo.git.remote("set-url", "origin", clone_url)
        else:
            repo.git.remote("add", "origin", clone_url)
    except GitCommandError as error:
        message = git_failure_message("Git could not configure the origin remote.", error)
        raise AppError(message, "GIT_ORIGIN_CONFIG_FAILED", git_error_details(error)) from error


# Creates a commit from all current version-folder changes when there is anything to commit.
def commit_all_changes(repo: Any, message_value: str, account: dict[str, Any] | None) -> dict[str, Any]:
    """Commit all working-tree changes and return commit metadata, or skipped when clean."""

    message = str(message_value or DEFAULT_INITIAL_COMMIT).strip() or DEFAULT_INITIAL_COMMIT
    try:
        repo.git.add("-A")
        staged_names = repo.git.diff("--cached", "--name-only")
    except GitCommandError as error:
        message_text = git_failure_message("Git could not stage the current version.", error)
        raise AppError(message_text, "GIT_STAGE_FAILED", git_error_details(error)) from error
    if not staged_names.strip():
        return {"created": False, "message": "No changes to commit."}

    try:
        actor = actor_from_account(account)
        commit = repo.index.commit(message, author=actor, committer=actor)
    except GitCommandError as error:
        message_text = git_failure_message("Git could not commit the current version.", error)
        raise AppError(message_text, "GIT_COMMIT_FAILED", git_error_details(error)) from error
    return {
        "created": True,
        "hexsha": commit.hexsha,
        "short_sha": commit.hexsha[:7],
        "message": commit.message.strip(),
    }


# Creates or reuses a GitHub repository and pushes the local version to it.
def promote_version_to_repo(
    version_path: str,
    owner: str,
    repo_name: str,
    private: bool,
    account: dict[str, Any],
    github_client: GitHubApiClient,
    git_service: GitService,
) -> dict[str, Any]:
    """Promote a local version folder into a GitHub-backed repository."""

    repo = ensure_version_repository(version_path, account)
    repository = github_client.ensure_repository(owner, repo_name, private)
    ensure_origin_remote(repo, repository.get("clone_url", ""))
    commit = commit_all_changes(repo, DEFAULT_INITIAL_COMMIT, account)
    push = git_service.push(str(repo.working_tree_dir or version_path), account["login"])
    summary = git_service.repository_summary(str(repo.working_tree_dir or version_path))
    return {
        "repository": repository,
        "local_repository": summary,
        "commit": commit,
        "push": push,
        "branch": active_branch_name(repo),
    }


# Publishes the current version as GitHub Pages using the existing Pages workflow generator.
def publish_version_pages(
    version_path: str,
    owner: str,
    repo_name: str,
    private: bool,
    branch: str,
    source_folder: str,
    page_file: str,
    account: dict[str, Any],
    github_client: GitHubApiClient,
    git_service: GitService,
) -> dict[str, Any]:
    """Configure Pages, write the workflow, commit it, push, and return Pages status."""

    repo = ensure_version_repository(version_path, account)
    repository = github_client.ensure_repository(owner, repo_name, private)
    ensure_origin_remote(repo, repository.get("clone_url", ""))
    content_commit = commit_all_changes(repo, DEFAULT_INITIAL_COMMIT, account)
    active_branch = active_branch_name(repo)
    selected_branch = str(branch or active_branch).strip() or active_branch
    prepared = pages.prepare_pages_settings(
        str(repo.working_tree_dir or version_path),
        selected_branch,
        source_folder,
        page_file,
    )
    remote = github_client.configure_pages_workflow(owner, repo_name)
    saved_pages = pages.write_prepared_pages_workflow(str(repo.working_tree_dir or version_path), prepared)
    workflow_commit = commit_all_changes(repo, "Publish GitHub Pages workflow", account)
    push = git_service.push(str(repo.working_tree_dir or version_path), account["login"])
    return {
        "repository": repository,
        "local_repository": git_service.repository_summary(str(repo.working_tree_dir or version_path)),
        "pages": saved_pages,
        "remote": remote,
        "content_commit": content_commit,
        "commit": workflow_commit,
        "push": push,
        "status": git_service.status(str(repo.working_tree_dir or version_path)),
    }


# Builds a default release body tied to the selected local version path.
def release_body_template(version_path: str, body_value: str = "") -> str:
    """Return release notes for a local version when the user did not provide custom notes."""

    custom_body = str(body_value or "").strip()
    if custom_body:
        return custom_body
    version_name = Path(version_path).name if version_path else "current version"
    return f"Published from Project Hub local version: {version_name}"


# Creates a GitHub release connected to a local version and returns the remote release URL.
def create_release_for_version(
    owner: str,
    repo_name: str,
    version_path: str,
    release_data: dict[str, Any],
    github_client: GitHubApiClient,
) -> dict[str, Any]:
    """Create a GitHub release for the selected local version."""

    tag_name = str(release_data.get("tag_name") or "").strip()
    title = str(release_data.get("title") or tag_name or Path(version_path).name).strip()
    payload = {
        "tag_name": tag_name,
        "title": title,
        "target_commitish": str(release_data.get("target_commitish") or "").strip(),
        "body": release_body_template(version_path, str(release_data.get("body") or "")),
        "draft": bool(release_data.get("draft", False)),
        "prerelease": bool(release_data.get("prerelease", False)),
        "generate_release_notes": bool(release_data.get("generate_release_notes", False)),
    }
    return github_client.create_release(owner, repo_name, payload)
