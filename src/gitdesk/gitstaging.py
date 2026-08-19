"""Selected-path staging safeguards for GitDesk commits."""

from __future__ import annotations

from functools import wraps
from threading import RLock
from typing import Any

from git import GitCommandError

from gitdesk.errors import AppError
from gitdesk.giterrors import git_error_details, git_failure_message
from gitdesk.gitstatus import parse_porcelain_status


# One process-wide lock keeps repository index mutations serialized across WebUI worker threads.
GIT_COMMIT_LOCK = RLock()
# Keep dynamic path arguments well below platform command-line limits while retaining targeted work for normal commits.
MAX_GIT_PATH_ARGUMENT_BYTES = 8_192


# Serializes commit requests so repeated clicks cannot stage against an index changed by an earlier request.
def serialized_git_commit(operation: Any) -> Any:
    """Run one GitService commit operation at a time."""

    @wraps(operation)
    def synchronized(*args: Any, **kwargs: Any) -> Any:
        with GIT_COMMIT_LOCK:
            return operation(*args, **kwargs)

    return synchronized


# Normalizes Git-returned and frontend-returned paths for exact ignored-path comparison.
def normalized_git_path(path_value: str) -> str:
    """Return one slash-normalized Git-relative comparison key."""

    return str(path_value or "").replace("\\", "/").rstrip("/")


# Estimates command-line space for Git paths using the UTF-8 form already accepted by the bridge.
def git_path_argument_bytes(paths: list[str]) -> int:
    """Return the encoded path bytes plus one separator byte per command argument."""

    return sum(len(path.encode("utf-8")) + 1 for path in paths)


# Splits path arguments into bounded batches without separating or rewriting any individual path.
def batched_git_paths(paths: list[str]) -> list[list[str]]:
    """Return ordered path batches that stay within the command-line byte budget."""

    batches: list[list[str]] = []
    current_batch: list[str] = []
    current_bytes = 0
    for path in paths:
        path_bytes = len(path.encode("utf-8")) + 1
        # Start a new command before adding a path that would exceed the conservative argument budget.
        if current_batch and current_bytes + path_bytes > MAX_GIT_PATH_ARGUMENT_BYTES:
            batches.append(current_batch)
            current_batch = []
            current_bytes = 0
        current_batch.append(path)
        current_bytes += path_bytes
    if current_batch:
        batches.append(current_batch)
    return batches


# Reads targeted status for normal selections and avoids an unsafe giant path list for bulk initial commits.
def selected_status_paths(repo: Any, selected_paths: list[str]) -> tuple[list[str], bool]:
    """Return current changed paths plus whether one complete status scan was used."""

    use_full_status = git_path_argument_bytes(selected_paths) > MAX_GIT_PATH_ARGUMENT_BYTES
    arguments = ["--porcelain=v1", "-z", "--untracked-files=all"]
    if not use_full_status:
        arguments.extend(["--", *selected_paths])
    raw_status = repo.git.status(*arguments)
    current_paths = [str(entry.get("path") or "") for entry in parse_porcelain_status(raw_status)]
    return current_paths, use_full_status


# Checks ignored paths in bounded commands so a bulk selection cannot exceed process argument limits.
def ignored_git_paths(repo: Any, selected_paths: list[str]) -> list[str]:
    """Return every selected path that Git currently classifies as ignored."""

    ignored_paths = []
    for batch in batched_git_paths(selected_paths):
        ignored_paths.extend(repo.ignored(*batch))
    return ignored_paths


# Removes stale and ignored paths so they cannot abort staging of the remaining current changes.
def stageable_git_paths(repo: Any, selected_paths: list[str], current_paths: list[str]) -> list[str]:
    """Return selected paths that still exist in current status and are not ignored."""

    current_keys = {normalized_git_path(path) for path in current_paths}
    current_selected = [path for path in selected_paths if normalized_git_path(path) in current_keys]
    if not current_selected:
        return []
    try:
        ignored_paths = ignored_git_paths(repo, current_selected)
    except GitCommandError as error:
        message = git_failure_message("Git could not check the selected paths against .gitignore.", error)
        raise AppError(message, "GIT_IGNORE_CHECK_FAILED", git_error_details(error)) from error

    ignored_keys = {normalized_git_path(path) for path in ignored_paths}
    return [path for path in current_selected if normalized_git_path(path) not in ignored_keys]


# Stages an exact all-current selection once, or uses bounded batches for a deliberate subset.
def stage_git_paths(
    repo: Any,
    selected_paths: list[str],
    current_paths: list[str],
    used_full_status: bool,
) -> None:
    """Stage safe paths while avoiding one unbounded command line for bulk commits."""

    selected_keys = {normalized_git_path(path) for path in selected_paths}
    current_keys = {normalized_git_path(path) for path in current_paths}
    if used_full_status and selected_keys == current_keys:
        repo.git.add("-A", "--", ".")
        return
    for batch in batched_git_paths(selected_paths):
        repo.git.add("-A", "--", *batch)
