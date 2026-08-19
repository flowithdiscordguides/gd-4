"""Verified merge-down transactions for completed Backup Mode versions."""

from __future__ import annotations

# Copying, JSON, path, and identity helpers build one rollback-safe merged parent.
from copy import deepcopy
import errno
import json
import os
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4

# Existing manifest and snapshot contracts remain authoritative during version replay.
from gitdesk.backup_copy import source_relative_path
from gitdesk.backup_manifest import (
    backup_timestamp,
    entries_for_source,
    manifest_diff,
    source_selection_rules,
)
from gitdesk.backup_selection import selection_state
from gitdesk.backup_snapshot import (
    BACKUP_LOG_NAME,
    BACKUP_MANIFEST_NAME,
    load_snapshot_manifest,
    previous_snapshot_path,
    remove_snapshot_path,
    source_map,
    validate_backup_destination,
    write_snapshot_json,
)
from gitdesk.backup_validation import (
    installed_entry_path,
    validate_installed_snapshot,
    verify_snapshot_content,
)
from gitdesk.errors import AppError


# Converts one stored version into a validated path and complete manifest.
def resolved_version(destination: Path, version: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    """Return one available destination-owned version and its manifest."""

    path = previous_snapshot_path(destination, version.get("path"))
    manifest = load_snapshot_manifest(path)
    if path is None or str(path) != version.get("path") or manifest is None:
        raise AppError(
            "A Backup version required for merge down is unavailable.",
            "BACKUP_MERGE_VERSION_UNAVAILABLE",
            {"version": str(version.get("name") or "")[:160]},
        )
    verify_snapshot_content(path, manifest)
    return path, manifest


# Resolves the chosen parent and every newer child in chronological replay order.
def merge_lineage(
    destination: Path,
    versions: list[dict[str, Any]],
    parent_path_value: Any,
) -> tuple[dict[str, Any], Path, dict[str, Any], list[tuple[dict[str, Any], Path, dict[str, Any]]]]:
    """Return a verified parent followed by all newer children oldest-first."""

    parent_path = str(parent_path_value or "").strip()
    parent_index = next(
        (index for index, version in enumerate(versions) if version.get("path") == parent_path),
        None,
    )
    if parent_index is None:
        raise AppError("Choose a valid parent Backup version.", "BACKUP_MERGE_PARENT_INVALID")
    if parent_index == 0:
        raise AppError(
            "Choose a parent with at least one newer child version.",
            "BACKUP_MERGE_CHILD_REQUIRED",
        )
    parent_version = versions[parent_index]
    resolved_parent, parent_manifest = resolved_version(destination, parent_version)
    children = []
    for version in reversed(versions[:parent_index]):
        child_path, child_manifest = resolved_version(destination, version)
        children.append((version, child_path, child_manifest))
    return parent_version, resolved_parent, parent_manifest, children


# Removes one selected path that disappeared while preserving excluded content in nonempty containers.
def remove_deleted_entry(path: Path, display_path: str) -> None:
    """Remove a deleted manifest entry without erasing retained descendants."""

    try:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError as error:
                if error.errno not in {errno.ENOTEMPTY, errno.EEXIST}:
                    raise
    except OSError as error:
        raise AppError(
            "A deleted child item could not be removed from the merge parent.",
            "BACKUP_MERGE_DELETE_FAILED",
            {"path": display_path, "reason": str(error)[:300]},
        ) from error


# Clears a conflicting target only when doing so cannot erase retained directory content.
def prepare_replacement(path: Path, display_path: str) -> None:
    """Make one target available for an exact child-manifest replacement."""

    try:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            path.rmdir()
    except OSError as error:
        code = "BACKUP_MERGE_PATH_CONFLICT" if error.errno in {errno.ENOTEMPTY, errno.EEXIST} \
            else "BACKUP_MERGE_COPY_FAILED"
        message = "A retained folder conflicts with a newer child item." if code.endswith("CONFLICT") \
            else "A merge target could not be prepared."
        raise AppError(message, code, {"path": display_path, "reason": str(error)[:300]}) from error


# Copies one already-verified child entry into the staged parent without following links.
def copy_child_entry(child: Path, staging: Path, entry_key: str, entry: dict[str, Any]) -> None:
    """Replace one staged path with the exact child version entry."""

    source = installed_entry_path(child, entry_key)
    target = installed_entry_path(staging, entry_key)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        kind = entry.get("kind")
        if kind == "directory":
            if target.is_symlink() or target.is_file():
                prepare_replacement(target, entry_key)
            target.mkdir(parents=True, exist_ok=True)
        elif kind == "file":
            prepare_replacement(target, entry_key)
            shutil.copy2(source, target, follow_symlinks=False)
        elif kind == "link":
            prepare_replacement(target, entry_key)
            os.symlink(os.readlink(source), target)
        else:
            raise AppError(
                "A child Backup manifest entry type is unsupported.",
                "BACKUP_MERGE_ENTRY_INVALID",
                {"path": entry_key},
            )
    except AppError:
        raise
    except OSError as error:
        raise AppError(
            "A child Backup item could not be copied into the merge parent.",
            "BACKUP_MERGE_COPY_FAILED",
            {"path": entry_key, "reason": str(error)[:300]},
        ) from error


# Moves prior content when a stable source id now uses a renamed snapshot target.
def relocate_source_target(
    staging: Path,
    manifest: dict[str, Any],
    old_source: dict[str, Any],
    new_source: dict[str, Any],
) -> None:
    """Relocate and remap one source before applying its newer selected scope."""

    old_base = str(old_source.get("snapshot_path") or "")
    new_base = str(new_source.get("snapshot_path") or "")
    if old_base == new_base:
        return
    old_target = installed_entry_path(staging, old_base)
    new_target = installed_entry_path(staging, new_base)
    if new_target.exists() or new_target.is_symlink():
        raise AppError(
            "A renamed Backup source conflicts with an existing merge path.",
            "BACKUP_MERGE_PATH_CONFLICT",
            {"path": new_base},
        )
    try:
        new_target.parent.mkdir(parents=True, exist_ok=True)
        old_target.rename(new_target)
    except OSError as error:
        raise AppError(
            "A renamed Backup source could not be moved inside the merge parent.",
            "BACKUP_MERGE_RENAME_FAILED",
            {"path": old_base, "reason": str(error)[:300]},
        ) from error
    entries = manifest.get("entries", {})
    for key, entry in list(entries_for_source(manifest, str(old_source["id"])).items()):
        relative = source_relative_path(old_source, key)
        new_key = f"{new_base}/{relative}" if relative else new_base
        entries[new_key] = entry
        del entries[key]


# Replaces or appends one manifest source while preserving stable group order.
def replace_manifest_source(manifest: dict[str, Any], source: dict[str, Any]) -> None:
    """Store the newest metadata for one source id in the cumulative manifest."""

    sources = manifest.setdefault("sources", [])
    for index, current in enumerate(sources):
        if current.get("id") == source.get("id"):
            sources[index] = deepcopy(source)
            return
    sources.append(deepcopy(source))


# Applies every source scope owned by one child manifest to the staged cumulative parent.
def apply_child_manifest(
    staging: Path,
    child: Path,
    merged: dict[str, Any],
    child_manifest: dict[str, Any],
) -> None:
    """Replay one child version without touching paths outside its confirmed selection."""

    entries = merged.setdefault("entries", {})
    current_sources = source_map(merged)
    for source in child_manifest.get("sources", []):
        if not isinstance(source, dict) or not source.get("id") or not source.get("snapshot_path"):
            raise AppError("A child Backup source record is invalid.", "BACKUP_MERGE_SOURCE_INVALID")
        source_id = str(source["id"])
        old_source = current_sources.get(source_id)
        if old_source:
            relocate_source_target(staging, merged, old_source, source)
        rules = source_selection_rules(source)
        child_entries = entries_for_source(child_manifest, source_id)
        current_entries = entries_for_source(merged, source_id)
        deleted_keys = [
            key
            for key in current_entries
            if selection_state(rules, source_relative_path(source, key)) and key not in child_entries
        ]
        for key in sorted(deleted_keys, key=lambda item: (item.count("/"), item.casefold()), reverse=True):
            remove_deleted_entry(installed_entry_path(staging, key), key)
            entries.pop(key, None)
        ordered_child_entries = sorted(
            child_entries.items(),
            key=lambda item: (
                item[0].count("/"),
                item[1].get("kind") != "directory",
                item[0].casefold(),
            ),
        )
        for key, entry in ordered_child_entries:
            copy_child_entry(child, staging, key, entry)
            entries[key] = deepcopy(entry)
        replace_manifest_source(merged, source)
        current_sources[source_id] = source
    merged["scanned_at"] = str(child_manifest.get("scanned_at") or merged.get("scanned_at") or "")


# Recomputes factual manifest totals after all child scopes have been replayed.
def finalize_manifest(manifest: dict[str, Any]) -> None:
    """Update cumulative counts from the exact merged entry map."""

    entries = manifest.get("entries", {})
    manifest["errors"] = []
    manifest["file_count"] = sum(entry.get("kind") in {"file", "link"} for entry in entries.values())
    manifest["directory_count"] = sum(entry.get("kind") == "directory" for entry in entries.values())
    manifest["total_bytes"] = sum(
        int(entry.get("size") or 0)
        for entry in entries.values()
        if entry.get("kind") == "file"
    )


# Retains the original log and appends one explicit merge-down transaction record.
def merged_log(
    parent: Path,
    staging: Path,
    children: list[tuple[dict[str, Any], Path, dict[str, Any]]],
    changes: dict[str, Any],
) -> dict[str, Any]:
    """Return the parent log with one bounded merge-down history entry."""

    try:
        raw = json.loads((parent / BACKUP_LOG_NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    log = dict(raw) if isinstance(raw, dict) else {}
    raw_history = log.get("merge_down_history")
    history = list(raw_history[-49:]) if isinstance(raw_history, list) else []
    history.append({
        "merged_at": backup_timestamp(),
        "parent_snapshot": str(parent),
        "child_snapshots": [str(path) for _version, path, _manifest in children],
        "changes": changes,
    })
    log["snapshot"] = str(parent)
    log["merge_down_history"] = history
    for control_name in (BACKUP_MANIFEST_NAME, BACKUP_LOG_NAME):
        (staging / control_name).unlink(missing_ok=True)
    return log


# Swaps a verified stage into the original parent path while retaining rollback until validation passes.
def install_merged_parent(parent: Path, staging: Path, manifest: dict[str, Any]) -> str:
    """Install the merged parent and return a nonfatal rollback-cleanup warning."""

    rollback = parent.parent / f".gitdesk-backup-merge-rollback-{uuid4().hex}"
    try:
        parent.rename(rollback)
        try:
            staging.rename(parent)
            validate_installed_snapshot(parent, manifest)
        except (AppError, OSError) as error:
            try:
                remove_snapshot_path(parent)
                rollback.rename(parent)
            except OSError as rollback_error:
                raise AppError(
                    "The merged parent could not be installed or rolled back.",
                    "BACKUP_MERGE_ROLLBACK_FAILED",
                    {"reason": str(rollback_error)[:300]},
                ) from rollback_error
            if isinstance(error, AppError):
                raise
            raise AppError(
                "The merged parent could not be installed.",
                "BACKUP_MERGE_INSTALL_FAILED",
                {"reason": str(error)[:300]},
            ) from error
        try:
            remove_snapshot_path(rollback)
            return ""
        except OSError as error:
            return f"The previous parent rollback copy could not be removed: {str(error)[:240]}"
    except AppError:
        raise
    except OSError as error:
        raise AppError(
            "The parent Backup version could not enter the merge transaction.",
            "BACKUP_MERGE_INSTALL_FAILED",
            {"reason": str(error)[:300]},
        ) from error


# Builds, verifies, and atomically installs one cumulative parent without mutating any child version.
def merge_backup_versions(
    destination_value: Any,
    versions: list[dict[str, Any]],
    parent_path_value: Any,
) -> dict[str, Any]:
    """Merge every newer version into a chosen parent and return updated metadata."""

    destination = validate_backup_destination(destination_value, [])
    parent_version, parent, parent_manifest, children = merge_lineage(
        destination,
        versions,
        parent_path_value,
    )
    staging = destination / f".gitdesk-backup-merge-stage-{uuid4().hex}"
    merged = deepcopy(parent_manifest)
    try:
        shutil.copytree(parent, staging, symlinks=True)
        for _version, child, child_manifest in children:
            apply_child_manifest(staging, child, merged, child_manifest)
        finalize_manifest(merged)
        changes = manifest_diff(parent_manifest, merged)
        if not changes["has_changes"]:
            remove_snapshot_path(staging)
            return {
                "no_changes": True,
                "version": parent_version,
                "merged_children": len(children),
                "cleanup_warning": "",
            }
        log = merged_log(parent, staging, children, changes)
        write_snapshot_json(staging / BACKUP_MANIFEST_NAME, merged)
        write_snapshot_json(staging / BACKUP_LOG_NAME, log)
        validate_installed_snapshot(staging, merged)
        verify_snapshot_content(staging, merged)
        cleanup_warning = install_merged_parent(parent, staging, merged)
    except AppError:
        remove_snapshot_path(staging)
        raise
    except OSError as error:
        remove_snapshot_path(staging)
        raise AppError(
            "Backup versions could not be merged safely.",
            "BACKUP_MERGE_FAILED",
            {"reason": str(error)[:300]},
        ) from error
    updated_version = {
        **parent_version,
        "file_count": merged["file_count"],
        "directory_count": merged["directory_count"],
        "total_bytes": merged["total_bytes"],
        "changes": changes,
    }
    return {
        "no_changes": False,
        "version": updated_version,
        "merged_children": len(children),
        "cleanup_warning": cleanup_warning,
    }
