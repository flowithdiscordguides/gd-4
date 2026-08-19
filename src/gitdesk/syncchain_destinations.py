"""Destination sanitation and path safety for repository and local-folder Sync Chain stages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gitdesk.errors import AppError
from gitdesk.managedrepos import clean_repository_map


def clean_stage(value: Any) -> dict[str, Any] | None:
    """Return one sanitized repository or local-folder stage reference."""

    if not isinstance(value, dict):
        return None
    repository_path = str(value.get("repository_path") or "").strip()
    if not repository_path:
        return None
    if value.get("local_only") is True:
        return {"local_only": True, "repository_path": repository_path}
    account_login = str(value.get("account_login") or "").strip()
    if not account_login:
        return None
    return {
        "local_only": False,
        "account_login": account_login,
        "repository_path": repository_path,
    }


def stage_is_local(stage: dict[str, Any] | None) -> bool:
    """Return whether stage represents a chooser-authorized ordinary local folder."""

    return bool(stage and stage.get("local_only") is True)


def require_managed_repository(
    settings: dict[str, Any],
    account_login: str,
    repository_path: str,
) -> dict[str, Any]:
    """Return an exact managed repository record or reject an unregistered destination."""

    login = str(account_login or "").strip()
    path = str(repository_path or "").strip()
    repositories = clean_repository_map(settings.get("managed_repositories"))
    record = next((item for item in repositories.get(login, []) if item["path"] == path), None)
    if not record:
        raise AppError("Choose a repository already saved in GitDesk.", "SYNC_REPOSITORY_NOT_MANAGED")
    return record


def require_local_folder(folder_path: str) -> str:
    """Return one existing canonical directory selected through the native folder chooser."""

    candidate = Path(str(folder_path or "").strip()).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise AppError("Choose an existing local destination folder.", "SYNC_LOCAL_FOLDER_INVALID") from error
    if not resolved.is_dir():
        raise AppError("Choose an existing local destination folder.", "SYNC_LOCAL_FOLDER_INVALID")
    return str(resolved)


def paths_overlap(left_value: str, right_value: str) -> bool:
    """Return whether either resolved path is the same as or nested inside the other."""

    left = Path(str(left_value or "")).expanduser().resolve()
    right = Path(str(right_value or "")).expanduser().resolve()
    try:
        left.relative_to(right)
        return True
    except ValueError:
        pass
    try:
        right.relative_to(left)
        return True
    except ValueError:
        return False


def validate_distinct_chain_paths(
    project_path: str,
    stages: dict[str, dict[str, Any]],
    stage_labels: dict[str, str],
) -> None:
    """Reject same or nested source and destination folders before save or execution."""

    paths = [("Local project", project_path)]
    paths.extend((stage_labels[name], stage["repository_path"]) for name, stage in stages.items())
    for index, (left_label, left_path) in enumerate(paths):
        for right_label, right_path in paths[index + 1:]:
            if paths_overlap(left_path, right_path):
                message = f"{left_label} and {right_label} must use separate, non-nested folders."
                raise AppError(message, "SYNC_CHAIN_PATH_OVERLAP")
