"""Recovery helpers for malformed GitDesk repository metadata JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# Registry keys are the durable metadata fields that make a recovered payload useful.
REGISTRY_METADATA_KEYS = {
    "managed_repositories",
    "active_repository_by_account",
    "repository_categories",
    "local_projects",
    "local_project_categories",
    "sync_chains",
}


# Returns the first unused backup path for a repository settings file that cannot be parsed.
def invalid_json_backup_path(path: Path) -> Path:
    """Return a sibling path where invalid repository settings can be preserved."""

    backup_path = path.with_name(f"{path.name}.invalid")
    if not backup_path.exists():
        return backup_path

    # Keep every corrupted copy instead of replacing the previous backup.
    backup_index = 1
    while True:
        candidate = path.with_name(f"{path.name}.invalid-{backup_index}")
        if not candidate.exists():
            return candidate
        backup_index += 1


# Sorts invalid backups newest-first so the most recent user metadata is recovered first.
def backup_sort_key(path: Path) -> tuple[float, str]:
    """Return a deterministic sort key for one invalid repository settings backup."""

    try:
        modified_time = path.stat().st_mtime
    except OSError:
        modified_time = 0.0
    return (modified_time, path.name)


# Lists preserved invalid backup files for a reposettings.json path.
def invalid_json_backup_candidates(path: Path) -> list[Path]:
    """Return existing invalid repository settings backups sorted newest first."""

    if not path.parent.exists():
        return []

    backup_prefix = f"{path.name}.invalid"
    try:
        children = list(path.parent.iterdir())
    except OSError:
        return []

    candidates = []
    for candidate in children:
        try:
            recovered_backup = ".recovered" in candidate.name[len(backup_prefix):]
            is_invalid_backup = (
                candidate.name == backup_prefix
                or candidate.name.startswith(f"{backup_prefix}-")
            )
            if candidate.is_file() and is_invalid_backup and not recovered_backup:
                candidates.append(candidate)
        except OSError:
            continue
    return sorted(candidates, key=backup_sort_key, reverse=True)


# Returns the first unused recovered-backup path so a consumed backup is still preserved.
def recovered_backup_path(path: Path) -> Path:
    """Return a sibling path for an invalid backup that has already been recovered."""

    recovered_path = path.with_name(f"{path.name}.recovered")
    if not recovered_path.exists():
        return recovered_path

    recovered_index = 1
    while True:
        candidate = path.with_name(f"{path.name}.recovered-{recovered_index}")
        if not candidate.exists():
            return candidate
        recovered_index += 1


# Renames a successfully recovered invalid backup so it is not imported repeatedly.
def mark_backup_recovered(path: Path) -> Path:
    """Rename a recovered invalid backup and return the final preserved path."""

    target_path = recovered_backup_path(path)
    try:
        path.rename(target_path)
        return target_path
    except OSError:
        return path


# Recovers the first complete JSON object from text that may contain trailing corruption.
def first_json_object(text: str) -> dict[str, Any] | None:
    """Return the first complete JSON object embedded in text, or None if none exists."""

    decoder = json.JSONDecoder()
    for start_index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _end_index = decoder.raw_decode(text[start_index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


# Parses normal JSON first, then falls back to extracting the first complete object.
def recover_json_payload(text: str) -> dict[str, Any] | None:
    """Return a JSON object recovered from repository settings text."""

    cleaned_text = text.lstrip("\ufeff").strip()
    if not cleaned_text:
        return None

    try:
        payload = json.loads(cleaned_text)
    except json.JSONDecodeError:
        return first_json_object(cleaned_text)
    return payload if isinstance(payload, dict) else None


# Loads a recoverable JSON object from a settings or backup path.
def load_recoverable_json(path: Path) -> dict[str, Any] | None:
    """Return a recoverable JSON object from disk, or None when recovery fails."""

    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    return recover_json_payload(text)


# Detects whether a sanitized settings object contains user registry metadata.
def registry_has_metadata(settings: dict[str, Any]) -> bool:
    """Return whether settings contains repository or Local Mode project metadata."""

    return any(bool(settings.get(key)) for key in REGISTRY_METADATA_KEYS)


# Merges ordered list values without duplicating existing entries.
def merge_unique_list(current: list[Any], incoming: list[Any]) -> list[Any]:
    """Return current list values plus incoming values that are not already present."""

    merged = list(current)
    for item in incoming:
        if item not in merged:
            merged.append(item)
    return merged


# Merges record lists by local path so current metadata wins over recovered backups.
def merge_records_by_path(current: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return record lists merged by path with current records taking precedence."""

    merged = list(current)
    seen_paths = {str(record.get("path") or "") for record in merged}
    for record in incoming:
        path = str(record.get("path") or "")
        if path and path not in seen_paths:
            merged.append(record)
            seen_paths.add(path)
    return merged


# Merges account-scoped repository records without replacing current account records.
def merge_repository_records(
    current: dict[str, list[dict[str, Any]]],
    incoming: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Return account repository maps merged with current records taking precedence."""

    merged = {login: list(records) for login, records in current.items()}
    for login, records in incoming.items():
        merged[login] = merge_records_by_path(merged.get(login, []), records)
    return merged


# Merges Sync Chains by stable id and project path so current configuration remains authoritative.
def merge_sync_chain_records(current: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return recovered Sync Chains without duplicating a current chain or Local Mode project."""

    merged = list(current)
    seen_ids = {str(chain.get("id") or "") for chain in merged}
    seen_projects = {str(chain.get("project_path") or "") for chain in merged}
    for chain in incoming:
        chain_id = str(chain.get("id") or "")
        project_path = str(chain.get("project_path") or "")
        if chain_id and project_path and chain_id not in seen_ids and project_path not in seen_projects:
            merged.append(chain)
            seen_ids.add(chain_id)
            seen_projects.add(project_path)
    return merged


# Merges account-scoped category arrays while preserving current category order.
def merge_category_records(current: dict[str, list[str]], incoming: dict[str, list[str]]) -> dict[str, list[str]]:
    """Return account category maps merged with current categories taking precedence."""

    merged = {login: list(categories) for login, categories in current.items()}
    for login, categories in incoming.items():
        merged[login] = merge_unique_list(merged.get(login, []), categories)
    return merged


# Merges recovered registry metadata into the current sanitized registry without overwriting current choices.
def merge_recovered_registry_settings(
    current: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    """Return registry settings enriched by recovered metadata while preserving current values."""

    merged = dict(current)
    merged["managed_repositories"] = merge_repository_records(
        current.get("managed_repositories") or {},
        incoming.get("managed_repositories") or {},
    )
    merged["active_repository_by_account"] = {
        **(incoming.get("active_repository_by_account") or {}),
        **(current.get("active_repository_by_account") or {}),
    }
    merged["repository_categories"] = merge_category_records(
        current.get("repository_categories") or {},
        incoming.get("repository_categories") or {},
    )
    merged["local_projects"] = merge_records_by_path(
        current.get("local_projects") or [],
        incoming.get("local_projects") or [],
    )
    merged["local_project_categories"] = merge_unique_list(
        current.get("local_project_categories") or [],
        incoming.get("local_project_categories") or [],
    )
    merged["sync_chains"] = merge_sync_chain_records(
        current.get("sync_chains") or [],
        incoming.get("sync_chains") or [],
    )
    return merged
