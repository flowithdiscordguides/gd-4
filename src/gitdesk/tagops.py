"""Local Git tag creation, version suggestion, and authenticated tag pushing."""

from __future__ import annotations

import re
from typing import Any

from git import GitCommandError

from gitdesk.errors import AppError
from gitdesk.gitauth import git_auth_environment, git_remote_argument
from gitdesk.giterrors import git_error_details, git_failure_message
from gitdesk.githubserializers import clean_commit_sha, clean_tag_name
from gitdesk.gitops import auth_login_for_origin, open_repository, origin_remote_url


# Release tags in Xander's workflow use v-prefixed numeric triplets, sometimes with a legacy v. prefix.
VERSION_TAG_PATTERN = re.compile(r"^[vV]\.?(\d+)\.(\d+)\.(\d+)$")

# GitDesk's requested release cadence rolls patch 9 into the next minor version.
VERSION_PART_MAX = 9


# Parses supported version tags while normalizing the legacy v.0.0.8 spelling to v0.0.8 semantics.
def parse_version_tag(tag_name: str) -> tuple[int, int, int] | None:
    """Return numeric version parts for a supported release tag, or None when it is unrelated."""

    match = VERSION_TAG_PATTERN.match(str(tag_name or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


# Advances the version using the single-digit patch rollover Xander requested for this app.
def bump_version(parts: tuple[int, int, int]) -> tuple[int, int, int]:
    """Return the next release version tuple after applying patch/minor rollover rules."""

    major, minor, patch = parts
    if patch < VERSION_PART_MAX:
        return major, minor, patch + 1
    if minor < VERSION_PART_MAX:
        return major, minor + 1, 0
    return major + 1, 0, 0


# Formats suggested versions consistently even when older tags used the legacy v. prefix.
def format_version_tag(parts: tuple[int, int, int]) -> str:
    """Return a normalized v-prefixed tag name for a version tuple."""

    return f"v{parts[0]}.{parts[1]}.{parts[2]}"


# Reads local tags from the repository object without requiring a network call.
def local_tag_names(repo: Any) -> list[str]:
    """Return tag names that are already present in the selected local repository."""

    return [tag.name for tag in repo.tags]


# Maps local tags to their peeled commit SHA so history rows can display version context.
def local_tag_commit_map(repo: Any) -> dict[str, list[str]]:
    """Return local tags grouped by the commit SHA they identify."""

    tags_by_commit: dict[str, list[str]] = {}
    for tag in repo.tags:
        try:
            target = tag.commit.hexsha.lower()
        except ValueError:
            continue
        tags_by_commit.setdefault(target, []).append(tag.name)
    return tags_by_commit


# Reads remote tag names from origin when possible so suggestions do not miss tags not fetched locally.
def remote_tag_names(repo: Any, auth_login: str | None = None) -> list[str]:
    """Return tag names advertised by origin, or an empty list when no origin is configured."""

    origin_url = origin_remote_url(repo)
    if not origin_url:
        return []

    git_login = auth_login_for_origin(repo, auth_login)
    try:
        output = repo.git.ls_remote(
            "--tags",
            git_remote_argument(origin_url, git_login),
            env=git_auth_environment(git_login),
        )
    except GitCommandError as error:
        message = git_failure_message("Git could not read origin tags.", error)
        raise AppError(message, "GIT_TAG_LIST_REMOTE_FAILED", git_error_details(error)) from error

    names: list[str] = []
    for line in output.splitlines():
        _, _, ref_name = line.partition("refs/tags/")
        if ref_name and not ref_name.endswith("^{}"):
            names.append(ref_name)
    return names


# Reads remote tag refs and peeled annotated-tag targets so history can show pushed tag versions.
def remote_tag_commit_map(repo: Any, auth_login: str | None = None) -> dict[str, list[str]]:
    """Return origin tags grouped by peeled commit SHA."""

    origin_url = origin_remote_url(repo)
    if not origin_url:
        return {}

    git_login = auth_login_for_origin(repo, auth_login)
    try:
        output = repo.git.ls_remote(
            "--tags",
            git_remote_argument(origin_url, git_login),
            env=git_auth_environment(git_login),
        )
    except GitCommandError as error:
        message = git_failure_message("Git could not read origin tags.", error)
        raise AppError(message, "GIT_TAG_LIST_REMOTE_FAILED", git_error_details(error)) from error

    direct_refs: dict[str, str] = {}
    peeled_refs: dict[str, str] = {}
    for line in output.splitlines():
        sha, _, ref_path = line.partition("\t")
        _, _, ref_name = ref_path.partition("refs/tags/")
        if not sha or not ref_name:
            continue
        if ref_name.endswith("^{}"):
            peeled_refs[ref_name[:-3]] = sha.lower()
        else:
            direct_refs[ref_name] = sha.lower()

    tags_by_commit: dict[str, list[str]] = {}
    for tag_name, direct_sha in direct_refs.items():
        target_sha = peeled_refs.get(tag_name, direct_sha)
        tags_by_commit.setdefault(target_sha, []).append(tag_name)
    return tags_by_commit


# Merges local and remote tag context for commit history rendering.
def history_tag_context(path_value: str, auth_login: str | None = None) -> dict[str, Any]:
    """Return commit-to-tag mappings and the next suggested release tag."""

    repo = open_repository(path_value)
    tags_by_commit = local_tag_commit_map(repo)
    tag_error = ""
    try:
        remote_tags = remote_tag_commit_map(repo, auth_login)
    except AppError as error:
        remote_tags = {}
        tag_error = error.message
    for commit_sha, tag_names in remote_tags.items():
        existing = tags_by_commit.setdefault(commit_sha, [])
        for tag_name in tag_names:
            if tag_name not in existing:
                existing.append(tag_name)

    for tag_names in tags_by_commit.values():
        tag_names.sort(key=lambda name: parse_version_tag(name) or (-1, -1, -1))
    all_tag_names = [tag_name for tag_names in tags_by_commit.values() for tag_name in tag_names]
    versions = [version for version in (parse_version_tag(name) for name in all_tag_names) if version is not None]
    next_parts = bump_version(max(versions)) if versions else (0, 0, 1)
    return {
        "by_commit": tags_by_commit,
        "next_tag": format_version_tag(next_parts),
        "tag_error": tag_error,
    }


# Chooses the highest numeric release tag before applying the requested next-version rule.
def suggest_next_tag(path_value: str, auth_login: str | None = None) -> dict[str, Any]:
    """Return the next normalized release tag for the selected repository."""

    repo = open_repository(path_value)
    tag_names = set(local_tag_names(repo))
    tag_names.update(remote_tag_names(repo, auth_login))
    versions = [version for version in (parse_version_tag(name) for name in tag_names) if version is not None]
    next_parts = bump_version(max(versions)) if versions else (0, 0, 1)
    return {"tag": format_version_tag(next_parts), "source_count": len(tag_names)}


# Creates one local annotated tag at the selected commit before pushing that exact tag to origin.
def create_and_push_tag(
    path_value: str,
    tag_name: str,
    target_sha: str,
    message: str,
    auth_login: str | None = None,
) -> dict[str, Any]:
    """Create a local annotated tag for a commit and push it to origin."""

    repo = open_repository(path_value)
    clean_tag = clean_tag_name(tag_name)
    clean_sha = clean_commit_sha(target_sha)
    clean_message = str(message or clean_tag).strip() or clean_tag
    origin_url = origin_remote_url(repo)
    if not origin_url:
        raise AppError("No origin remote is configured for this repository.", "GIT_ORIGIN_MISSING")
    if clean_tag in local_tag_names(repo):
        raise AppError("That tag already exists locally.", "GIT_TAG_EXISTS")

    try:
        repo.git.tag("-a", clean_tag, clean_sha, "-m", clean_message)
    except GitCommandError as error:
        message_text = git_failure_message("Git could not create the local tag.", error)
        raise AppError(message_text, "GIT_TAG_CREATE_FAILED", git_error_details(error)) from error

    git_login = auth_login_for_origin(repo, auth_login)
    try:
        output = repo.git.push(
            git_remote_argument(origin_url, git_login),
            clean_tag,
            env=git_auth_environment(git_login),
        )
    except GitCommandError as error:
        message_text = git_failure_message(f"Tag {clean_tag} was created locally, but push failed.", error)
        raise AppError(message_text, "GIT_TAG_PUSH_FAILED", git_error_details(error)) from error

    return {
        "tag": clean_tag,
        "target": clean_sha,
        "message": clean_message,
        "command": f"git push origin {clean_tag}",
        "messages": [output] if output else [],
    }
