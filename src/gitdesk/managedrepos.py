"""Account-scoped managed repository settings for GitDesk."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gitdesk.accounts import clean_login
from gitdesk.errors import AppError


# Managed repositories are non-secret local metadata, partitioned by GitHub login.
ManagedRepositoryMap = dict[str, list[dict[str, Any]]]
ActiveRepositoryMap = dict[str, str]


# Normalizes a persisted repository record without touching the filesystem during settings load.
def clean_repository_record(value: Any) -> dict[str, Any] | None:
    """Return a frontend-safe managed repository record, or None for malformed settings."""

    if not isinstance(value, dict):
        return None

    path = str(value.get("path") or "").strip()
    if not path:
        return None

    owner = str(value.get("owner") or value.get("github_owner") or "").strip()
    repo = str(value.get("repo") or value.get("github_repo") or "").strip()
    name = str(value.get("name") or repo or Path(path).name).strip()
    full_name = str(value.get("full_name") or "").strip()
    if not full_name:
        full_name = f"{owner}/{repo}" if owner and repo else name
    source = str(value.get("source") or "added").strip()
    if source not in {"added", "cloned", "created", "published"}:
        source = "added"

    return {
        "path": path,
        "name": name,
        "owner": owner,
        "repo": repo,
        "full_name": full_name,
        "branch": str(value.get("branch") or "").strip(),
        "private": bool(value.get("private", False)),
        "source": source,
        "category": str(value.get("category") or "").strip(),
    }


# Sanitizes the account-to-repositories mapping and de-duplicates each account by local path.
def clean_repository_map(value: Any) -> ManagedRepositoryMap:
    """Return valid managed repositories grouped by GitHub account login."""

    if not isinstance(value, dict):
        return {}

    cleaned: ManagedRepositoryMap = {}
    for raw_login, raw_records in value.items():
        try:
            login = clean_login(str(raw_login or ""))
        except AppError:
            continue
        if not isinstance(raw_records, list):
            continue

        seen_paths = set()
        records = []
        for raw_record in raw_records:
            record = clean_repository_record(raw_record)
            if record and record["path"] not in seen_paths:
                records.append(record)
                seen_paths.add(record["path"])
        if records:
            cleaned[login] = records
    return cleaned


# Keeps active selections only when the selected path belongs to that same account.
def clean_active_repository_map(value: Any, repositories: ManagedRepositoryMap) -> ActiveRepositoryMap:
    """Return active repository paths that are valid for their account buckets."""

    if not isinstance(value, dict):
        return {}

    active_paths: ActiveRepositoryMap = {}
    for raw_login, raw_path in value.items():
        try:
            login = clean_login(str(raw_login or ""))
        except AppError:
            continue
        path = str(raw_path or "").strip()
        if path and any(record["path"] == path for record in repositories.get(login, [])):
            active_paths[login] = path
    return active_paths


# Builds the persisted managed-repository shape from Git metadata returned by GitService.
def record_from_summary(
    summary: dict[str, Any],
    existing: dict[str, Any] | None = None,
    source: str = "",
    category: str = "",
) -> dict[str, Any]:
    """Return a managed repository record from a GitService repository summary."""

    path = str(summary.get("path") or "").strip()
    if not path:
        raise AppError("Repository path is required.", "REPOSITORY_PATH_EMPTY")

    owner = str(summary.get("github_owner") or "").strip()
    repo = str(summary.get("github_repo") or "").strip()
    name = repo or Path(path).name
    existing_record = existing or {}
    saved_source = str(source or existing_record.get("source") or "added").strip()
    if saved_source not in {"added", "cloned", "created", "published"}:
        saved_source = "added"
    return {
        "path": path,
        "name": name,
        "owner": owner,
        "repo": repo,
        "full_name": f"{owner}/{repo}" if owner and repo else name,
        "branch": str(summary.get("branch") or "").strip(),
        "private": bool(summary.get("private", existing_record.get("private", False))),
        "source": saved_source,
        "category": str(category or existing_record.get("category") or "").strip(),
    }


# Returns the managed repositories visible to a single signed-in account.
def repositories_for_account(settings: dict[str, Any], login: str) -> list[dict[str, Any]]:
    """Return managed repositories for one account without exposing other accounts."""

    cleaned_login = clean_login(login)
    return clean_repository_map(settings.get("managed_repositories")).get(cleaned_login, [])


# Finds the active repository record for one account, or None when that account has no selection.
def active_repository_for_account(settings: dict[str, Any], login: str) -> dict[str, Any] | None:
    """Return the active managed repository record for one account."""

    cleaned_login = clean_login(login)
    repositories = clean_repository_map(settings.get("managed_repositories"))
    active_paths = clean_active_repository_map(settings.get("active_repository_by_account"), repositories)
    active_path = active_paths.get(cleaned_login, "")
    return next((record for record in repositories.get(cleaned_login, []) if record["path"] == active_path), None)


# Updates compatibility fields so older backend actions operate on the active account's repository only.
def account_context_settings_update(settings: dict[str, Any], login: str) -> dict[str, Any]:
    """Return repository_path/owner/repo fields for the selected account context."""

    repository = active_repository_for_account(settings, login)
    if not repository:
        return {"repository_path": "", "github_owner": "", "github_repo": ""}
    return {
        "repository_path": repository["path"],
        "github_owner": repository["owner"],
        "github_repo": repository["repo"],
    }


# Merges or refreshes a repository under one account and marks it active for that account.
def repository_settings_update(
    settings: dict[str, Any],
    login: str,
    summary: dict[str, Any],
    source: str = "",
    category: str = "",
) -> dict[str, Any]:
    """Return settings updates that add a repository to one account and make it active."""

    cleaned_login = clean_login(login)
    repositories = clean_repository_map(settings.get("managed_repositories"))
    active_paths = clean_active_repository_map(settings.get("active_repository_by_account"), repositories)
    summary_path = str(summary.get("path") or "").strip()
    existing = next((item for item in repositories.get(cleaned_login, []) if item["path"] == summary_path), None)
    record = record_from_summary(summary, existing, source, category)
    account_records = [item for item in repositories.get(cleaned_login, []) if item["path"] != record["path"]]
    account_records.append(record)
    account_records.sort(key=lambda item: item["full_name"].lower())
    repositories[cleaned_login] = account_records
    active_paths[cleaned_login] = record["path"]

    return {
        "managed_repositories": repositories,
        "active_repository_by_account": active_paths,
        "repository_path": record["path"],
        "github_owner": record["owner"],
        "github_repo": record["repo"],
    }


# Registers a repository for Sync Chain setup without changing the user's active Repo Mode selection.
def repository_registry_update(
    settings: dict[str, Any],
    login: str,
    summary: dict[str, Any],
    source: str = "",
    category: str = "",
) -> dict[str, Any]:
    """Return registry-only updates that add or refresh a managed repository record."""

    cleaned_login = clean_login(login)
    repositories = clean_repository_map(settings.get("managed_repositories"))
    summary_path = str(summary.get("path") or "").strip()
    existing = next((item for item in repositories.get(cleaned_login, []) if item["path"] == summary_path), None)
    record = record_from_summary(summary, existing, source, category)
    account_records = [item for item in repositories.get(cleaned_login, []) if item["path"] != record["path"]]
    account_records.append(record)
    repositories[cleaned_login] = sorted(account_records, key=lambda item: item["full_name"].lower())
    return {"managed_repositories": repositories}


# Removes one repository record from the app registry without deleting the local folder.
def remove_repository_settings(settings: dict[str, Any], login: str, path: str) -> dict[str, Any]:
    """Return settings updates that remove one account-owned repository record."""

    cleaned_login = clean_login(login)
    cleaned_path = str(path or "").strip()
    repositories = clean_repository_map(settings.get("managed_repositories"))
    active_paths = clean_active_repository_map(settings.get("active_repository_by_account"), repositories)
    account_records = [record for record in repositories.get(cleaned_login, []) if record["path"] != cleaned_path]
    if account_records:
        repositories[cleaned_login] = account_records
    else:
        repositories.pop(cleaned_login, None)
    if active_paths.get(cleaned_login) == cleaned_path:
        active_paths.pop(cleaned_login, None)
    selected = next((record for record in account_records if record["path"] == active_paths.get(cleaned_login)), None)
    return {
        "managed_repositories": repositories,
        "active_repository_by_account": active_paths,
        "repository_path": selected["path"] if selected else "",
        "github_owner": selected["owner"] if selected else "",
        "github_repo": selected["repo"] if selected else "",
    }


# Updates one repository category while leaving the record in its current account bucket.
def repository_category_update(settings: dict[str, Any], login: str, path: str, category: str) -> dict[str, Any]:
    """Return settings updates that assign a category to one repository record."""

    cleaned_login = clean_login(login)
    cleaned_path = str(path or "").strip()
    repositories = clean_repository_map(settings.get("managed_repositories"))
    account_records = repositories.get(cleaned_login, [])
    for record in account_records:
        if record["path"] == cleaned_path:
            record["category"] = str(category or "").strip()
            break
    repositories[cleaned_login] = account_records
    return {"managed_repositories": repositories}


# Preserves old single-repository settings by assigning them to the current active account once.
def migrate_legacy_repository(settings: dict[str, Any]) -> dict[str, Any]:
    """Return settings with legacy repository_path copied into the active account bucket."""

    login = str(settings.get("active_account") or "").strip()
    path = str(settings.get("repository_path") or "").strip()
    if not login or not path:
        return settings

    try:
        clean_login(login)
    except AppError:
        return settings

    repositories = clean_repository_map(settings.get("managed_repositories"))
    if any(record["path"] == path for record in repositories.get(login, [])):
        active_paths = clean_active_repository_map(settings.get("active_repository_by_account"), repositories)
        if not active_paths.get(login):
            active_paths[login] = path
            settings["active_repository_by_account"] = active_paths
        return settings

    summary = {
        "path": path,
        "github_owner": settings.get("github_owner", ""),
        "github_repo": settings.get("github_repo", ""),
    }
    settings.update(repository_settings_update(settings, login, summary))
    return settings
