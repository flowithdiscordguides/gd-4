"""Sanitization and migration rules for GitDesk repository registry metadata."""

from __future__ import annotations

from typing import Any

from gitdesk.accounts import clean_login
from gitdesk.categorynames import clean_category_name
from gitdesk.errors import AppError
from gitdesk.localprojects import clean_local_project_list
from gitdesk.managedrepos import clean_active_repository_map, clean_repository_map
from gitdesk.syncchains import clean_sync_chains


# Version four records whether each Local Mode project already lives inside its category folder.
REPO_SETTINGS_SCHEMA_VERSION = 4


# Cleans category lists loaded from disk while preserving first-seen order.
def clean_category_list(value: Any) -> list[str]:
    """Return valid category labels loaded from repository settings."""

    if not isinstance(value, list):
        return []
    categories = []
    for raw_category in value:
        try:
            category = clean_category_name(raw_category)
        except AppError:
            continue
        if category and category not in categories:
            categories.append(category)
    return categories


# Sanitizes account-to-category mappings without requiring an active token.
def clean_repository_category_map(value: Any) -> dict[str, list[str]]:
    """Return category labels grouped by GitHub login."""

    if not isinstance(value, dict):
        return {}
    category_map = {}
    for raw_login, raw_categories in value.items():
        try:
            login = clean_login(str(raw_login or ""))
        except AppError:
            continue
        categories = clean_category_list(raw_categories)
        if categories:
            category_map[login] = categories
    return category_map


# Finds categories embedded in repository records for compatibility with older registry files.
def category_map_from_repositories(repositories: dict[str, list[dict[str, Any]]]) -> dict[str, list[str]]:
    """Return account categories discovered from managed repository records."""

    category_map = {}
    for login, records in repositories.items():
        categories = []
        for record in records:
            category = str(record.get("category") or "").strip()
            if category and category not in categories:
                categories.append(category)
        if categories:
            category_map[login] = categories
    return category_map


# Finds categories embedded in Local Mode project records.
def categories_from_local_projects(projects: list[dict[str, str]]) -> list[str]:
    """Return local project categories discovered from project records."""

    categories = []
    for project in projects:
        category = str(project.get("category") or "").strip()
        if category and category not in categories:
            categories.append(category)
    return categories


# Clears invalid categories stored directly on repository and project records.
def clean_record_categories(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return records with sanitized category fields."""

    cleaned_records = []
    for record in records:
        try:
            category = clean_category_name(record.get("category"))
        except AppError:
            category = ""
        cleaned_records.append({**record, "category": category})
    return cleaned_records


# Builds the complete safe registry shape used by both normal loads and recovery.
def clean_registry_settings(raw_settings: Any) -> dict[str, Any]:
    """Return sanitized repository, Local Mode, category, and Sync Chain metadata."""

    defaults = {
        "schema_version": REPO_SETTINGS_SCHEMA_VERSION,
        "managed_repositories": {},
        "active_repository_by_account": {},
        "repository_categories": {},
        "local_projects": [],
        "local_project_categories": [],
        "sync_chains": [],
    }
    if not isinstance(raw_settings, dict):
        return defaults
    repositories = {
        login: clean_record_categories(records)
        for login, records in clean_repository_map(raw_settings.get("managed_repositories")).items()
    }
    active_paths = clean_active_repository_map(raw_settings.get("active_repository_by_account"), repositories)
    repository_categories = clean_repository_category_map(raw_settings.get("repository_categories"))
    for login, categories in category_map_from_repositories(repositories).items():
        existing = repository_categories.get(login, [])
        repository_categories[login] = existing + [item for item in categories if item not in existing]
    local_projects = clean_record_categories(clean_local_project_list(raw_settings.get("local_projects")))
    local_categories = clean_category_list(raw_settings.get("local_project_categories"))
    local_categories.extend(
        item for item in categories_from_local_projects(local_projects) if item not in local_categories
    )
    return {
        **defaults,
        "managed_repositories": repositories,
        "active_repository_by_account": active_paths,
        "repository_categories": repository_categories,
        "local_projects": local_projects,
        "local_project_categories": local_categories,
        "sync_chains": clean_sync_chains(raw_settings.get("sync_chains")),
    }


# Merges ordered values without duplicating current metadata.
def merge_category_lists(current: list[str], incoming: list[str]) -> list[str]:
    """Return current category values plus unseen incoming values."""

    merged = list(current)
    merged.extend(item for item in incoming if item not in merged)
    return merged


# Merges repository maps by local path while keeping current records authoritative.
def merge_repository_maps(
    current: dict[str, list[dict[str, Any]]],
    incoming: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Return account repository records with current entries taking precedence."""

    merged = {login: list(records) for login, records in current.items()}
    for login, records in incoming.items():
        account_records = list(merged.get(login, []))
        seen_paths = {record["path"] for record in account_records}
        account_records.extend(record for record in records if record["path"] not in seen_paths)
        if account_records:
            merged[login] = sorted(account_records, key=lambda item: item["full_name"].lower())
    return merged


# Merges account category arrays while preserving current order.
def merge_repository_category_maps(
    current: dict[str, list[str]],
    incoming: dict[str, list[str]],
) -> dict[str, list[str]]:
    """Return category arrays grouped by account login."""

    merged = {login: list(categories) for login, categories in current.items()}
    for login, categories in incoming.items():
        merged[login] = merge_category_lists(merged.get(login, []), categories)
    return merged


# Merges Local Mode project records by path without replacing current category assignments.
def merge_local_project_lists(
    current: list[dict[str, str]],
    incoming: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Return Local Mode projects with current records taking precedence."""

    merged = list(current)
    seen_paths = {record["path"] for record in merged}
    merged.extend(record for record in incoming if record["path"] not in seen_paths)
    return sorted(merged, key=lambda item: item["name"].lower())


# Merges legacy settings.json metadata into the current versioned registry.
def merge_legacy_registry_settings(current_value: Any, incoming_value: Any) -> dict[str, Any]:
    """Return a cleaned registry merge with current settings taking precedence."""

    current = clean_registry_settings(current_value)
    incoming = clean_registry_settings(incoming_value)
    repositories = merge_repository_maps(current["managed_repositories"], incoming["managed_repositories"])
    active_paths = dict(incoming["active_repository_by_account"])
    active_paths.update(current["active_repository_by_account"])
    active_paths = clean_active_repository_map(active_paths, repositories)
    current_chain_projects = {chain["project_path"] for chain in current["sync_chains"]}
    sync_chains = current["sync_chains"] + [
        chain for chain in incoming["sync_chains"] if chain["project_path"] not in current_chain_projects
    ]
    return clean_registry_settings({
        "managed_repositories": repositories,
        "active_repository_by_account": active_paths,
        "repository_categories": merge_repository_category_maps(
            current["repository_categories"], incoming["repository_categories"]
        ),
        "local_projects": merge_local_project_lists(current["local_projects"], incoming["local_projects"]),
        "local_project_categories": merge_category_lists(
            current["local_project_categories"], incoming["local_project_categories"]
        ),
        "sync_chains": sync_chains,
    })
