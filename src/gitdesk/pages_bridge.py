"""Bridge handlers for GitHub Pages setup and commit-history tagging."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk import pages
from gitdesk import githubpages
from gitdesk.errors import AppError
from gitdesk import tagops
from gitdesk.githubserializers import clean_repository_pair


# Keeps Pages and history actions out of the main BridgeController class.
def pages_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return bridge actions for GitHub Pages and commit history workflows."""

    return {
        "pagesState": lambda payload: handle_pages_state(controller, payload),
        "savePagesSettings": lambda payload: handle_save_pages_settings(controller, payload),
        "listCommitHistory": lambda payload: handle_commit_history(controller, payload),
        "suggestNextTag": lambda payload: handle_suggest_next_tag(controller, payload),
        "createTagForCommit": lambda payload: handle_create_tag(controller, payload),
    }


# Reads local workflow state plus the current GitHub Pages remote configuration.
def handle_pages_state(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return local and remote Pages state for the active repository."""

    path = controller.repository_path_from_payload(payload)
    owner, repo = controller.github_pair_from_payload(payload)
    client = controller.github_client(payload)
    remote = client.pages_site(owner, repo)
    return {
        "local": pages.pages_state(path),
        "remote": remote,
        "deployment": githubpages.latest_pages_status(client, owner, repo, remote),
    }


# Configures GitHub Pages first so permission failures do not create misleading local changes.
def handle_save_pages_settings(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Configure branch or Actions publishing without replacing repository-owned workflows."""

    path = controller.repository_path_from_payload(payload)
    owner, repo = controller.github_pair_from_payload(payload)
    build_type = githubpages.clean_build_type(payload.get("build_type"))
    settings = {"branch": "", "source_folder": "/"}
    # Legacy mode needs a real source; workflow mode intentionally leaves every existing YAML file untouched.
    if build_type == "legacy":
        settings = pages.prepare_pages_source(
            path,
            str(payload.get("branch") or ""),
            str(payload.get("source_folder") or "/"),
        )
    client = controller.github_client(payload)
    remote = githubpages.configure_pages_site(
        client,
        owner,
        repo,
        build_type,
        settings["branch"],
        settings["source_folder"],
    )
    return {
        "local": pages.pages_state(path),
        "remote": remote,
        "deployment": githubpages.latest_pages_status(client, owner, repo, remote),
        "status": controller.git_service.status(path),
        "branches": controller.git_service.branches(path),
    }


# Loads recent remote commit history for the selected branch.
def next_tag_from_names(tag_names: list[str]) -> str:
    """Return the next normalized version tag from existing GitHub tag names."""

    versions = [version for version in (tagops.parse_version_tag(name) for name in tag_names) if version is not None]
    next_parts = tagops.bump_version(max(versions)) if versions else (0, 0, 1)
    return tagops.format_version_tag(next_parts)


# Loads repository tags from GitHub's already-peeled tag listing so annotated tags do not cause N+1 requests.
def github_tag_context(client: Any, owner: str, repo: str) -> dict[str, Any]:
    """Return GitHub tag names grouped by target commit SHA."""

    clean_owner, clean_repo = clean_repository_pair(owner, repo)
    page = 1
    page_size = 100
    tag_names: list[str] = []
    tags_by_commit: dict[str, list[str]] = {}
    # Read every page so next-version suggestions remain correct for repositories with long tag histories.
    while True:
        tags = client.request(
            "GET",
            f"/repos/{clean_owner}/{clean_repo}/tags",
            params={"per_page": page_size, "page": page},
        )
        if not isinstance(tags, list):
            raise AppError("GitHub returned an unexpected repository tags response.", "GITHUB_RESPONSE_INVALID")

        # Each repository-tag row points directly at its commit, regardless of lightweight or annotated storage.
        for tag in tags:
            commit = tag.get("commit") if isinstance(tag, dict) else None
            tag_name = str(tag.get("name") or "") if isinstance(tag, dict) else ""
            commit_sha = str(commit.get("sha") or "").lower() if isinstance(commit, dict) else ""
            if not tag_name or not commit_sha:
                continue
            tag_names.append(tag_name)
            tags_by_commit.setdefault(commit_sha, []).append(tag_name)

        # GitHub returns fewer than page_size rows only on the final page.
        if len(tags) < page_size:
            break
        page += 1

    for tags in tags_by_commit.values():
        tags.sort(key=lambda name: tagops.parse_version_tag(name) or (-1, -1, -1))
    return {"by_commit": tags_by_commit, "next_tag": next_tag_from_names(tag_names)}


# Adds tag labels and the next suggested version to recent commit history rows.
def commits_with_tag_context(commits: list[dict[str, Any]], tag_context: dict[str, Any]) -> list[dict[str, Any]]:
    """Return commit history rows enriched with tag labels."""

    tags_by_commit = tag_context.get("by_commit") if isinstance(tag_context, dict) else {}
    next_tag = str(tag_context.get("next_tag") or "") if isinstance(tag_context, dict) else ""
    enriched = []
    for index, commit in enumerate(commits):
        row = dict(commit)
        commit_sha = str(row.get("sha") or "").lower()
        tags = tags_by_commit.get(commit_sha, []) if isinstance(tags_by_commit, dict) else []
        row["tags"] = tags
        row["tag_label"] = ", ".join(tags) if tags else (f"Next {next_tag}" if index == 0 and next_tag else "No tag")
        enriched.append(row)
    return enriched


# Returns the selected local branch when a repository path is available, falling back to payload state.
def history_branch(controller: Any, payload: dict[str, Any]) -> str:
    """Return the branch that History should request from GitHub."""

    payload_branch = str(payload.get("branch") or "").strip()
    try:
        path = controller.repository_path_from_payload(payload)
        branches = controller.git_service.branches(path) if path else {}
    except AppError:
        return payload_branch

    local_branch = str(branches.get("current") or "").strip() if isinstance(branches, dict) else ""
    return local_branch if local_branch and local_branch != "DETACHED" else payload_branch


# Prepends a freshly pushed commit when GitHub's branch commit list has not caught up yet.
def commits_with_expected_sha(
    client: Any,
    owner: str,
    repo: str,
    branch: str,
    expected_sha: str,
) -> list[dict[str, Any]]:
    """Return recent commits while guaranteeing an expected pushed SHA is present."""

    commits = client.commits(owner, repo, branch)
    cleaned_sha = str(expected_sha or "").strip().lower()
    if not cleaned_sha or any(str(commit.get("sha") or "").lower() == cleaned_sha for commit in commits):
        return commits

    expected_commit = client.commit(owner, repo, cleaned_sha)
    return [expected_commit] + [
        commit for commit in commits if str(commit.get("sha") or "").lower() != cleaned_sha
    ]


# Loads recent remote commit history for the selected branch.
def handle_commit_history(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return recent commits for the configured GitHub repository."""

    owner, repo = controller.github_pair_from_payload(payload)
    branch = history_branch(controller, payload)
    client = controller.github_client(payload)
    commits = commits_with_expected_sha(client, owner, repo, branch, str(payload.get("expected_sha") or ""))
    tag_context = github_tag_context(client, owner, repo)
    return {
        "branch": branch,
        "commits": commits_with_tag_context(commits, tag_context),
        "tags": tag_context,
    }


# Creates and publishes an annotated tag for a selected commit.
def handle_suggest_next_tag(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Return the next release tag suggestion for the selected repository."""

    return tagops.suggest_next_tag(
        controller.repository_path_from_payload(payload),
        controller.optional_auth_login(payload),
    )


# Creates and publishes an annotated tag for a selected commit.
def handle_create_tag(controller: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a remote tag for a commit selected in the history modal."""

    tag = payload.get("tag") or {}
    if not isinstance(tag, dict):
        raise AppError("Tag payload must be a JSON object.", "TAG_PAYLOAD_INVALID")
    return tagops.create_and_push_tag(
        controller.repository_path_from_payload(payload),
        str(tag.get("tag") or ""),
        str(tag.get("sha") or ""),
        str(tag.get("message") or ""),
        controller.optional_auth_login(payload),
    )
