"""Merge-forward snapshot transactions for Backup Mode destinations."""

from __future__ import annotations

# Standard-library JSON, filesystem, and timestamp tools implement portable full snapshots.
from datetime import datetime
import json
from pathlib import Path
import shutil
from typing import Any, Callable
from uuid import uuid4

# Backup manifests provide deterministic source comparison and post-copy verification.
from gitdesk.backup_copy import copy_manifest_source
from gitdesk.backup_manifest import entry_identity, entries_for_source, manifest_diff, scan_sources
from gitdesk.backup_progress import (
    CancellationCheck,
    ProgressCallback,
    SnapshotProgress,
    ensure_backup_active,
)
from gitdesk.backup_skips import installed_manifest, private_skipped_paths, public_skipped_items
from gitdesk.backup_validation import (
    prior_snapshot_matches_manifest,
    validate_installed_snapshot,
    verify_snapshot_content,
)
from gitdesk.errors import AppError


# Snapshot control files live inside each version but are not part of backed-up source content.
BACKUP_MANIFEST_NAME = ".gitdesk-backup-manifest.json"
BACKUP_LOG_NAME = "backup-log.json"

# Human-readable snapshot names use filesystem-safe local date and time.
BACKUP_FOLDER_PREFIX = "gitdesk backups "


# Removes only a transaction-owned file, link, or directory without following links.
def remove_snapshot_path(path: Path) -> None:
    """Remove path when it exists as a file, link, or directory."""

    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


# Resolves an existing destination and rejects recursive placement inside any directory source.
def validate_backup_destination(destination_value: Any, sources: list[dict[str, Any]]) -> Path:
    """Return a safe existing backup destination outside every backed-up directory root."""

    raw_destination = str(destination_value or "").strip()
    destination = Path(raw_destination).expanduser()
    if not raw_destination or destination.is_symlink() or not destination.is_dir():
        raise AppError("Choose an available backup destination folder.", "BACKUP_DESTINATION_UNAVAILABLE")
    destination = destination.resolve()
    for source in sources:
        if source["kind"] != "directory":
            continue
        raw_source = str(source.get("path") or "").strip()
        try:
            source_path = Path(raw_source).expanduser().resolve()
            destination.relative_to(source_path)
        except ValueError:
            continue
        except OSError:
            continue
        raise AppError(
            f"Backup destination cannot be inside {source['label']}.",
            "BACKUP_DESTINATION_RECURSIVE",
        )
    return destination


# Creates a unique human-readable snapshot path when two backups finish in the same second.
def next_snapshot_path(destination: Path) -> Path:
    """Return an unused dated snapshot path inside destination."""

    base_name = f"{BACKUP_FOLDER_PREFIX}{datetime.now().astimezone().strftime('%Y-%m-%d %H-%M-%S')}"
    candidate = destination / base_name
    suffix = 2
    while candidate.exists() or candidate.is_symlink():
        candidate = destination / f"{base_name} ({suffix})"
        suffix += 1
    return candidate


# Validates that a stored prior snapshot remains one direct child of the current destination.
def previous_snapshot_path(destination: Path, path_value: Any) -> Path | None:
    """Return a valid prior snapshot root or None when unavailable."""

    raw_path = str(path_value or "").strip()
    if not raw_path:
        return None
    candidate = Path(raw_path).expanduser()
    try:
        resolved = candidate.resolve()
    except OSError:
        return None
    if (
        candidate.is_symlink()
        or not resolved.is_dir()
        or resolved.parent != destination
        or not resolved.name.startswith(BACKUP_FOLDER_PREFIX)
    ):
        return None
    return resolved


# Loads one complete prior manifest only from a validated snapshot control file.
def load_snapshot_manifest(snapshot: Path | None) -> dict[str, Any] | None:
    """Return a prior snapshot manifest or None when no valid snapshot is available."""

    if snapshot is None:
        return None
    manifest_path = snapshot / BACKUP_MANIFEST_NAME
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), dict):
        return None
    return payload


# Converts the prior manifest's persisted source list into a stable id mapping.
def source_map(manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Return valid source records keyed by stable id."""

    sources = manifest.get("sources", []) if isinstance(manifest, dict) else []
    return {
        str(source.get("id")): source
        for source in sources
        if isinstance(source, dict) and source.get("id") and source.get("snapshot_path")
    }


# Compares all entries owned by one source without considering scan timestamps.
def source_entries_match(
    left_manifest: dict[str, Any],
    right_manifest: dict[str, Any],
    source_id: str,
) -> bool:
    """Return True when one source has identical paths and content identity."""

    left_entries = entries_for_source(left_manifest, source_id)
    right_entries = entries_for_source(right_manifest, source_id)
    if set(left_entries) != set(right_entries):
        return False
    return all(
        entry_identity(left_entries[key]) == entry_identity(right_entries[key])
        for key in left_entries
    )


# Returns source ids whose content or snapshot target differs from the prior completed version.
def changed_source_ids(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> set[str]:
    """Return sources that must be recopied into the next merge-forward snapshot."""

    if previous is None:
        return {str(source["id"]) for source in current["sources"]}
    previous_sources = source_map(previous)
    changed = set()
    for source in current["sources"]:
        source_id = str(source["id"])
        old_source = previous_sources.get(source_id)
        target_changed = old_source and old_source.get("snapshot_path") != source.get("snapshot_path")
        if not old_source or target_changed or not source_entries_match(previous, current, source_id):
            changed.add(source_id)
    return changed


# Writes one formatted JSON control file in cancellable encoder chunks after verification succeeds.
def write_snapshot_json(
    path: Path,
    payload: dict[str, Any],
    cancel_check: CancellationCheck | None = None,
) -> None:
    """Write a complete formatted JSON object inside a transaction staging folder."""

    try:
        encoder = json.JSONEncoder(indent=2, sort_keys=True)
        with path.open("x", encoding="utf-8") as output_file:
            for chunk in encoder.iterencode(payload):
                ensure_backup_active(cancel_check)
                output_file.write(chunk)
            output_file.write("\n")
    except OSError as error:
        raise AppError("Backup snapshot metadata could not be written.", "BACKUP_METADATA_WRITE_FAILED") from error


# Builds and atomically installs one full current version by merging changes over the prior snapshot.
def create_backup_snapshot(
    destination_value: Any,
    sources: list[dict[str, Any]],
    latest_snapshot_value: Any,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancellationCheck | None = None,
    seal_cancellation: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Create a verified dated backup snapshot and return its version metadata."""

    progress = SnapshotProgress(progress_callback)
    ensure_backup_active(cancel_check)
    destination = validate_backup_destination(destination_value, sources)
    previous_path = previous_snapshot_path(destination, latest_snapshot_value)
    previous_manifest = load_snapshot_manifest(previous_path)
    # A baseline without its valid manifest cannot prove ownership of inherited snapshot paths.
    if previous_manifest is None:
        previous_path = None
    current_manifest = scan_sources(sources, progress, cancel_check)
    if current_manifest["errors"]:
        raise AppError(
            "Backup stopped because one or more registered sources are unavailable.",
            "BACKUP_SOURCES_UNAVAILABLE",
            {"errors": current_manifest["errors"]},
        )
    # A prior control file cannot suppress copying unless its installed bytes still match every manifest entry.
    if previous_path and previous_manifest and not prior_snapshot_matches_manifest(
        previous_path,
        previous_manifest,
        progress,
        cancel_check,
    ):
        previous_path = None
        previous_manifest = None
    changes = manifest_diff(previous_manifest, current_manifest)
    if previous_manifest is not None and not changes["has_changes"]:
        ensure_backup_active(cancel_check)
        if seal_cancellation and not seal_cancellation():
            raise AppError("Backup cancelled. No version was created.", "BACKUP_CANCELLED")
        progress.begin_finalizing()
        return {"no_changes": True, "manifest": current_manifest, "changes": changes}

    final_path = next_snapshot_path(destination)
    staging = destination / f".gitdesk-backup-stage-{uuid4().hex}"
    current_sources = {source["id"]: source for source in current_manifest["sources"]}
    previous_sources = source_map(previous_manifest)
    changed_ids = changed_source_ids(previous_manifest, current_manifest)
    metadata_warnings: list[dict[str, str]] = []
    skipped_items: list[dict[str, Any]] = []
    transaction_path = staging
    try:
        staging.mkdir(parents=False, exist_ok=False)
        progress.begin_copy(current_manifest)
        # Unchanged sources merge forward from the verified prior snapshot; changed sources copy from live roots.
        for source_id in sorted(current_sources):
            ensure_backup_active(cancel_check)
            source = current_sources[source_id]
            copy_source = source
            if previous_path and source_id not in changed_ids:
                copy_source = {
                    **source,
                    "path": str(previous_path / Path(previous_sources[source_id]["snapshot_path"])),
                }
            _copied_target, source_skips = copy_manifest_source(
                copy_source,
                staging,
                current_manifest,
                progress,
                cancel_check,
                metadata_warnings,
                source,
            )
            skipped_items.extend(source_skips)

        # The installed manifest excludes every explicit skip so verification never claims absent content exists.
        completed_manifest = installed_manifest(current_manifest, skipped_items)
        progress.begin_verification(completed_manifest)
        verify_snapshot_content(staging, completed_manifest, progress, cancel_check)

        pending_changes = manifest_diff(completed_manifest, current_manifest)
        log = {
            "created_at": current_manifest["scanned_at"],
            "previous_snapshot": str(previous_path or ""),
            "snapshot": str(final_path),
            "changes": changes,
            "source_count": len(current_manifest["sources"]),
            "metadata_warnings": metadata_warnings,
            "skipped_count": len(skipped_items),
            "skipped_items": skipped_items,
        }
        write_snapshot_json(staging / BACKUP_MANIFEST_NAME, completed_manifest, cancel_check)
        write_snapshot_json(staging / BACKUP_LOG_NAME, log, cancel_check)
        ensure_backup_active(cancel_check)
        progress.begin_finalizing()
        if seal_cancellation and not seal_cancellation():
            raise AppError("Backup cancelled. No version was created.", "BACKUP_CANCELLED")
        staging.rename(final_path)
        transaction_path = final_path
        validate_installed_snapshot(final_path, completed_manifest)
    except AppError:
        remove_snapshot_path(transaction_path)
        raise
    except OSError as error:
        remove_snapshot_path(transaction_path)
        raise AppError("Backup snapshot could not be completed.", "BACKUP_SNAPSHOT_FAILED") from error

    version = {
        "name": final_path.name,
        "path": str(final_path),
        "created_at": current_manifest["scanned_at"],
        "file_count": completed_manifest["file_count"],
        "directory_count": completed_manifest["directory_count"],
        "total_bytes": completed_manifest["total_bytes"],
        "changes": changes,
        "metadata_warnings": metadata_warnings,
        "skipped_count": len(skipped_items),
    }
    return {
        "no_changes": False,
        "version": version,
        "manifest": completed_manifest,
        "changes": changes,
        "pending_changes": pending_changes,
        "skipped_items": public_skipped_items(skipped_items),
        "_skipped_source_paths": private_skipped_paths(skipped_items),
    }
