"""Content fingerprinting and staged snapshot copying for Project Sync Chains."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
from typing import Any

from gitdesk.errors import AppError
from gitdesk.gitops import open_repository
from gitdesk.syncchain_destinations import paths_overlap


# Git metadata never crosses a Sync Chain edge because every stage owns its own repository history.
SYNC_EXCLUDED_NAME = ".git"

# File content is streamed so large project assets do not need to fit in memory.
HASH_CHUNK_SIZE = 1024 * 1024


# Returns whether one path is excluded directly or by a selected parent directory.
def path_is_excluded(relative_path: str, ignored_paths: frozenset[str]) -> bool:
    """Return True when relative_path is covered by the immutable ignored path set."""

    return any(
        relative_path == ignored_path or relative_path.startswith(f"{ignored_path}/")
        for ignored_path in ignored_paths
    )


# Resolves an existing readable source directory for snapshot construction.
def normalize_sync_source(path_value: str) -> Path:
    """Return a resolved existing source directory for a one-way mirror operation."""

    cleaned_path = str(path_value or "").strip()
    if not cleaned_path:
        raise AppError("A synchronization source folder is required.", "SYNC_SOURCE_EMPTY")
    source = Path(cleaned_path).expanduser().resolve()
    if not source.exists() or not source.is_dir():
        raise AppError("The synchronization source folder no longer exists.", "SYNC_SOURCE_INVALID")
    return source


# Requires the destination itself, rather than one of its parents, to be a non-bare Git working tree.
def normalize_sync_destination(path_value: str) -> Path:
    """Return the exact resolved working-tree root for a managed destination repository."""

    cleaned_path = str(path_value or "").strip()
    if not cleaned_path:
        raise AppError("A synchronization destination repository is required.", "SYNC_DESTINATION_EMPTY")
    destination = Path(cleaned_path).expanduser().resolve()
    repo = open_repository(str(destination))
    working_tree = Path(str(repo.working_tree_dir or "")).expanduser().resolve()
    if working_tree != destination:
        raise AppError("The synchronization destination must be the repository root.", "SYNC_DESTINATION_NOT_ROOT")
    git_entry = destination / SYNC_EXCLUDED_NAME
    if not git_entry.exists() and not git_entry.is_symlink():
        raise AppError("The destination repository has no Git metadata to preserve.", "SYNC_DESTINATION_GIT_MISSING")
    return destination


# Rejects any source/destination relationship that could recursively copy or replace its own input.
def validate_mirror_paths(source: Path, destination: Path) -> None:
    """Raise when source and destination are identical or nested inside one another."""

    if paths_overlap(str(source), str(destination)):
        raise AppError(
            "Synchronization source and destination must be separate, non-nested folders.",
            "SYNC_PATH_OVERLAP",
        )


# Feeds an unambiguous type/path boundary into a deterministic folder digest.
def update_entry_identity(digest: Any, entry_type: str, relative_path: str) -> None:
    """Add one typed relative path to a content fingerprint digest."""

    digest.update(entry_type.encode("ascii"))
    digest.update(b"\0")
    digest.update(relative_path.encode("utf-8", errors="surrogateescape"))
    digest.update(b"\0")


# Streams a regular file into the current digest without following symbolic links.
def update_file_content(digest: Any, file_path: Path) -> int:
    """Hash a regular file and return its byte count."""

    total_bytes = 0
    try:
        with file_path.open("rb") as source_file:
            while True:
                chunk = source_file.read(HASH_CHUNK_SIZE)
                if not chunk:
                    return total_bytes
                digest.update(chunk)
                total_bytes += len(chunk)
    except OSError as error:
        raise AppError("A source file could not be read during synchronization.", "SYNC_SOURCE_READ_FAILED") from error


# Walks a tree without following symlinks and excludes Git metadata at every depth.
def fingerprint_directory(root: Path, ignored_paths: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Return a deterministic digest and size counts after applying ignored paths."""

    digest = hashlib.sha256()
    file_count = 0
    directory_count = 0
    total_bytes = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name)
        except OSError as error:
            raise AppError("A folder could not be read during synchronization.", "SYNC_SOURCE_READ_FAILED") from error
        for entry in entries:
            if entry.name == SYNC_EXCLUDED_NAME:
                continue
            entry_path = Path(entry.path)
            relative_path = entry_path.relative_to(root).as_posix()
            # A selected directory rule covers its full subtree, so traversal must stop at the parent.
            if path_is_excluded(relative_path, ignored_paths):
                continue
            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise AppError("A filesystem entry could not be inspected.", "SYNC_SOURCE_READ_FAILED") from error
            mode = entry_stat.st_mode
            if stat.S_ISLNK(mode):
                update_entry_identity(digest, "link", relative_path)
                try:
                    link_target = os.readlink(entry_path)
                except OSError as error:
                    raise AppError("A symbolic link could not be read.", "SYNC_SOURCE_READ_FAILED") from error
                digest.update(link_target.encode("utf-8", errors="surrogateescape"))
                digest.update(b"\0")
                file_count += 1
            elif stat.S_ISREG(mode):
                update_entry_identity(digest, "file", relative_path)
                total_bytes += update_file_content(digest, entry_path)
                file_count += 1
            elif stat.S_ISDIR(mode):
                update_entry_identity(digest, "directory", relative_path)
                directory_count += 1
                pending.append(entry_path)
            else:
                raise AppError(
                    f"Unsupported filesystem entry in sync source: {relative_path}",
                    "SYNC_SOURCE_ENTRY_UNSUPPORTED",
                )
    return {
        "digest": digest.hexdigest(),
        "file_count": file_count,
        "directory_count": directory_count,
        "total_bytes": total_bytes,
    }


# Public fingerprint entry point resolves the folder before reading it.
def folder_fingerprint(path_value: str) -> dict[str, Any]:
    """Return a deterministic fingerprint for an existing folder excluding all .git entries."""

    root = normalize_sync_source(path_value)
    return {"path": str(root), **fingerprint_directory(root)}


# Copies one symlink exactly as a link instead of following it outside the source tree.
def copy_symbolic_link(source: Path, destination: Path) -> None:
    """Create destination with the same symbolic-link target as source."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(os.readlink(source), destination, target_is_directory=source.is_dir())
    except OSError as error:
        raise AppError("A symbolic link could not be copied.", "SYNC_STAGE_COPY_FAILED") from error


# Recursively copies source content into an empty staging directory while excluding Git metadata.
def copy_snapshot_entries(
    source_root: Path,
    source_directory: Path,
    target_directory: Path,
    ignored_paths: frozenset[str],
) -> None:
    """Copy non-ignored children into target_directory without following symlinks."""

    for entry in sorted(source_directory.iterdir(), key=lambda item: item.name):
        if entry.name == SYNC_EXCLUDED_NAME:
            continue
        relative_path = entry.relative_to(source_root).as_posix()
        # Ignored directories are skipped as one unit and therefore never materialize in the snapshot.
        if path_is_excluded(relative_path, ignored_paths):
            continue
        target = target_directory / entry.name
        if entry.is_symlink():
            copy_symbolic_link(entry, target)
        elif entry.is_dir():
            target.mkdir(parents=False, exist_ok=False)
            copy_snapshot_entries(source_root, entry, target, ignored_paths)
        elif entry.is_file():
            shutil.copy2(entry, target, follow_symlinks=False)
        else:
            raise AppError(
                f"Unsupported filesystem entry in sync source: {relative_path}",
                "SYNC_SOURCE_ENTRY_UNSUPPORTED",
            )


# Recursively copies source content into an empty staging directory while applying Sync Ignore rules.
def copy_snapshot(source: Path, staging: Path, ignored_paths: frozenset[str] = frozenset()) -> None:
    """Copy a filtered non-Git working snapshot into staging without following symlinks."""

    try:
        staging.mkdir(parents=False, exist_ok=False)
        copy_snapshot_entries(source, source, staging, ignored_paths)
    except AppError:
        raise
    except OSError as error:
        raise AppError("The source snapshot could not be staged.", "SYNC_STAGE_COPY_FAILED") from error


# Confirms a staged snapshot exactly matches a stable source fingerprint before replacement starts.
def build_verified_snapshot(
    source: Path,
    staging: Path,
    ignored_paths: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Copy a filtered source and return its fingerprint after detecting concurrent edits."""

    source_before = fingerprint_directory(source, ignored_paths)
    copy_snapshot(source, staging, ignored_paths)
    staged = fingerprint_directory(staging)
    source_after = fingerprint_directory(source, ignored_paths)
    if staged["digest"] != source_before["digest"] or source_after["digest"] != source_before["digest"]:
        raise AppError(
            "Source files changed while synchronization was preparing. Try again after edits finish.",
            "SYNC_SOURCE_CHANGED",
        )
    return staged
