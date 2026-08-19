"""Validation and response shaping helpers for GitHub REST API payloads."""

from __future__ import annotations

from typing import Any
import re

from gitdesk.errors import AppError


# GitHub owner and repository path segments are constrained to prevent malformed API paths.
OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")

# Tag names are sent inside refs/tags/<name>, so reject ambiguous or path-breaking input early.
TAG_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")

# GitHub commit history returns SHA-1 values for the Git database endpoints used here.
COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


# Validates owner/repo inputs before they become path segments in GitHub API URLs.
def clean_repository_pair(owner: str, repo: str) -> tuple[str, str]:
    """Return sanitized owner and repo names for GitHub REST path construction."""

    clean_owner = str(owner or "").strip()
    clean_repo = str(repo or "").strip()
    if not clean_owner or not clean_repo:
        raise AppError("GitHub owner and repository name are required.", "GITHUB_REPOSITORY_EMPTY")
    if not OWNER_PATTERN.match(clean_owner) or not REPO_PATTERN.match(clean_repo):
        raise AppError("GitHub owner or repository name contains invalid characters.", "GITHUB_REPOSITORY_INVALID")
    return clean_owner, clean_repo


# Sanitizes a user-entered tag before it becomes a fully qualified Git ref.
def clean_tag_name(value: str) -> str:
    """Return a safe tag name for GitHub's refs/tags namespace."""

    tag_name = str(value or "").strip()
    invalid_parts = tag_name.startswith("/") or tag_name.endswith(("/", "."))
    invalid_parts = invalid_parts or ".." in tag_name or "@{" in tag_name
    invalid_parts = invalid_parts or tag_name.endswith(".lock") or "//" in tag_name
    if not tag_name or invalid_parts or not TAG_NAME_PATTERN.match(tag_name):
        raise AppError("Tag name contains invalid Git ref characters.", "TAG_NAME_INVALID")
    return tag_name


# Checks commit target input before creating a remote tag object.
def clean_commit_sha(value: str) -> str:
    """Return a normalized 40-character commit SHA."""

    clean_sha = str(value or "").strip()
    if not COMMIT_SHA_PATTERN.match(clean_sha):
        raise AppError("A valid commit SHA is required for the tag.", "TAG_TARGET_INVALID")
    return clean_sha.lower()


# Condenses GitHub's repository schema into fields needed by the clone picker.
def serialize_repository(repository: dict[str, Any]) -> dict[str, Any]:
    """Return a compact repository record for frontend clone selection."""

    owner = repository.get("owner") or {}
    return {
        "id": repository.get("id"),
        "name": repository.get("name", ""),
        "full_name": repository.get("full_name", ""),
        "owner": owner.get("login", ""),
        "owner_type": owner.get("type", ""),
        "private": bool(repository.get("private", False)),
        "fork": bool(repository.get("fork", False)),
        "archived": bool(repository.get("archived", False)),
        "description": repository.get("description") or "",
        "clone_url": repository.get("clone_url", ""),
        "ssh_url": repository.get("ssh_url", ""),
        "html_url": repository.get("html_url", ""),
        "default_branch": repository.get("default_branch", ""),
        "updated_at": repository.get("updated_at", ""),
    }


# Condenses a GitHub Pages response into the fields shown in the Pages panel.
def serialize_pages_site(site: dict[str, Any]) -> dict[str, Any]:
    """Return compact GitHub Pages configuration details."""

    source = site.get("source") or {}
    return {
        "configured": True,
        "status": site.get("status", ""),
        "html_url": site.get("html_url", ""),
        "build_type": site.get("build_type", ""),
        "source": {
            "branch": source.get("branch", ""),
            "path": source.get("path", ""),
        },
    }


# Condenses the large workflow run schema into the fields the dashboard needs.
def serialize_workflow_run(run: dict[str, Any]) -> dict[str, Any]:
    """Return a compact workflow run record for frontend rendering."""

    actor = run.get("actor") or {}
    head_commit = run.get("head_commit") or {}
    return {
        "id": run.get("id"),
        "name": run.get("name") or run.get("display_title") or "Workflow run",
        "display_title": run.get("display_title", ""),
        "status": run.get("status", ""),
        "conclusion": run.get("conclusion", ""),
        "event": run.get("event", ""),
        "branch": run.get("head_branch", ""),
        "sha": run.get("head_sha", ""),
        "message": head_commit.get("message", ""),
        "run_number": run.get("run_number"),
        "created_at": run.get("created_at", ""),
        "run_started_at": run.get("run_started_at", ""),
        "updated_at": run.get("updated_at", ""),
        "html_url": run.get("html_url", ""),
        "actor": actor.get("login", ""),
    }


# Condenses a commit record for the history modal.
def serialize_commit(commit: dict[str, Any]) -> dict[str, Any]:
    """Return a compact commit history record."""

    detail = commit.get("commit") or {}
    author = detail.get("author") or {}
    user = commit.get("author") or {}
    message = str(detail.get("message") or "")
    return {
        "sha": commit.get("sha", ""),
        "short_sha": str(commit.get("sha", ""))[:7],
        "message": message.splitlines()[0] if message else "",
        "author": user.get("login") or author.get("name", ""),
        "date": author.get("date", ""),
        "html_url": commit.get("html_url", ""),
    }


# Condenses the release schema into stable display fields for the releases manager.
def serialize_release_asset(asset: dict[str, Any]) -> dict[str, Any]:
    """Return a compact release asset record for draft review and publish screens."""

    uploader = asset.get("uploader") or {}
    return {
        "id": asset.get("id"),
        "name": asset.get("name", ""),
        "label": asset.get("label") or "",
        "state": asset.get("state", ""),
        "size": int(asset.get("size") or 0),
        "download_count": int(asset.get("download_count") or 0),
        "created_at": asset.get("created_at", ""),
        "updated_at": asset.get("updated_at", ""),
        "browser_download_url": asset.get("browser_download_url", ""),
        "uploader": uploader.get("login", ""),
    }


# Condenses the release schema into stable display fields for the releases manager.
def serialize_release(release: dict[str, Any]) -> dict[str, Any]:
    """Return a compact release record for frontend rendering."""

    author = release.get("author") or {}
    assets = release.get("assets") or []
    return {
        "id": release.get("id"),
        "tag_name": release.get("tag_name", ""),
        "target_commitish": release.get("target_commitish", ""),
        "name": release.get("name", ""),
        "body": release.get("body", ""),
        "draft": bool(release.get("draft", False)),
        "prerelease": bool(release.get("prerelease", False)),
        "created_at": release.get("created_at", ""),
        "published_at": release.get("published_at", ""),
        "html_url": release.get("html_url", ""),
        "author": author.get("login", ""),
        "assets": [serialize_release_asset(asset) for asset in assets if isinstance(asset, dict)],
    }


# Returns the remote tag details needed by the UI after the ref is published.
def serialize_tag_result(
    owner: str,
    repo: str,
    tag_name: str,
    target_sha: str,
    created_ref: dict[str, Any],
) -> dict[str, Any]:
    """Return a compact tag creation result."""

    return {
        "tag": tag_name,
        "target": target_sha,
        "ref": created_ref.get("ref", f"refs/tags/{tag_name}"),
        "html_url": f"https://github.com/{owner}/{repo}/releases/new?tag={tag_name}",
    }
