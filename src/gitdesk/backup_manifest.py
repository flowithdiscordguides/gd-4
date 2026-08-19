"""Deterministic full-content manifests and change diffs for Backup Mode."""

from __future__ import annotations

# Standard-library hashing, traversal, and timestamps avoid new backup dependencies.
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import stat
from typing import Any

# Structured errors prevent partial or unsupported filesystem state from appearing complete.
from gitdesk.backup_progress import CancellationCheck, SnapshotProgress, ensure_backup_active
from gitdesk.backup_selection import clean_selection_rules, has_included_descendant, selection_state
from gitdesk.errors import AppError


# The schema version makes destination manifest evolution explicit.
BACKUP_MANIFEST_SCHEMA_VERSION = 3

# Files stream in bounded chunks so media and repository objects do not enter memory whole.
BACKUP_HASH_CHUNK_SIZE = 1024 * 1024

# UI and private scan state retain a bounded sample while full manifests remain in each snapshot.
MAX_REPORTED_CHANGES = 500


# Returns one stable UTC timestamp for scans and snapshot logs.
def backup_timestamp() -> str:
    """Return a second-precision ISO-8601 UTC timestamp."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# Streams one regular file into SHA-256 while tracking exact read progress and cancellation.
def hash_file(
    path: Path,
    display_path: str,
    progress: SnapshotProgress | None = None,
    cancel_check: CancellationCheck | None = None,
) -> tuple[str, int]:
    """Return the SHA-256 digest and byte count for a regular file."""

    digest = hashlib.sha256()
    total_bytes = 0
    try:
        with path.open("rb") as source_file:
            while True:
                ensure_backup_active(cancel_check)
                chunk = source_file.read(BACKUP_HASH_CHUNK_SIZE)
                if not chunk:
                    if progress:
                        progress.advance_read(display_path, item_complete=True)
                    return digest.hexdigest(), total_bytes
                digest.update(chunk)
                total_bytes += len(chunk)
                if progress:
                    progress.advance_read(display_path, len(chunk))
    except OSError as error:
        raise AppError("A backup source file could not be read.", "BACKUP_SOURCE_READ_FAILED") from error


# Builds one manifest key rooted at the source's stable snapshot target.
def entry_key(source: dict[str, str], relative_path: str = "") -> str:
    """Return the portable snapshot-relative key for one source entry."""

    base = source["snapshot_path"]
    return f"{base}/{relative_path}" if relative_path else base


# Records one file, directory, or link without following links outside registered roots.
def manifest_entry(
    path: Path,
    source: dict[str, str],
    relative_path: str,
    progress: SnapshotProgress | None = None,
    cancel_check: CancellationCheck | None = None,
) -> dict[str, Any]:
    """Return one deterministic manifest entry for path."""

    ensure_backup_active(cancel_check)
    display_path = entry_key(source, relative_path)
    try:
        entry_stat = path.lstat()
    except OSError as error:
        raise AppError("A backup source entry could not be inspected.", "BACKUP_SOURCE_READ_FAILED") from error
    mode = entry_stat.st_mode
    if stat.S_ISLNK(mode):
        try:
            link_target = os.readlink(path)
        except OSError as error:
            raise AppError("A backup source link could not be read.", "BACKUP_SOURCE_READ_FAILED") from error
        digest = hashlib.sha256(link_target.encode("utf-8", errors="surrogateescape")).hexdigest()
        if progress:
            progress.advance_read(display_path, item_complete=True)
        return {
            "source_id": source["id"],
            "kind": "link",
            "size": len(link_target.encode("utf-8", errors="surrogateescape")),
            "digest": digest,
            "modified_ns": entry_stat.st_mtime_ns,
            "link_target": link_target,
        }
    if stat.S_ISREG(mode):
        digest, byte_count = hash_file(path, display_path, progress, cancel_check)
        return {
            "source_id": source["id"],
            "kind": "file",
            "size": byte_count,
            "digest": digest,
            "modified_ns": entry_stat.st_mtime_ns,
            "link_target": "",
        }
    if stat.S_ISDIR(mode):
        return {
            "source_id": source["id"],
            "kind": "directory",
            "size": 0,
            "digest": "",
            "modified_ns": entry_stat.st_mtime_ns,
            "link_target": "",
        }
    raise AppError(
        f"Unsupported backup source entry: {entry_key(source, relative_path)}",
        "BACKUP_SOURCE_ENTRY_UNSUPPORTED",
    )


# Returns explicit rules or a complete-root rule for legacy unfiltered source records.
def source_selection_rules(source: dict[str, Any]) -> dict[str, bool]:
    """Return canonical include/exclude rules for one source."""

    if "selection_rules" not in source:
        return {"": True}
    return clean_selection_rules(source.get("selection_rules"))


# Traverses selected directory content while retaining containers for included descendants.
def scan_directory_source(
    source: dict[str, Any],
    root: Path,
    progress: SnapshotProgress | None = None,
    cancel_check: CancellationCheck | None = None,
) -> dict[str, dict[str, Any]]:
    """Return manifest entries for the included portion of one registered directory root."""

    entries: dict[str, dict[str, Any]] = {}
    rules = source_selection_rules(source)
    if not any(rules.values()):
        return entries
    entries[entry_key(source)] = manifest_entry(root, source, "", progress, cancel_check)
    pending = [root]
    while pending:
        ensure_backup_active(cancel_check)
        directory = pending.pop()
        try:
            children = sorted(os.scandir(directory), key=lambda item: item.name.casefold(), reverse=True)
        except OSError as error:
            raise AppError("A backup source folder could not be read.", "BACKUP_SOURCE_READ_FAILED") from error
        # Reverse-sorted insertion plus stack order keeps the final traversal deterministic.
        for child in reversed(children):
            ensure_backup_active(cancel_check)
            child_path = Path(child.path)
            relative_path = child_path.relative_to(root).as_posix()
            included = selection_state(rules, relative_path)
            is_directory = child.is_dir(follow_symlinks=False)
            if is_directory and not included and not has_included_descendant(rules, relative_path):
                continue
            if not is_directory and not included:
                continue
            item = manifest_entry(child_path, source, relative_path, progress, cancel_check)
            entries[entry_key(source, relative_path)] = item
            if item["kind"] == "directory":
                pending.append(child_path)
    return entries


# Scans one inventory record and returns either complete entries or a frontend-safe error record.
def scan_source(
    source: dict[str, Any],
    progress: SnapshotProgress | None = None,
    cancel_check: CancellationCheck | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str] | None]:
    """Return manifest entries and an optional source error for one registered record."""

    raw_path = str(source.get("path") or "")
    path = Path(raw_path).expanduser()
    try:
        ensure_backup_active(cancel_check)
        if source["kind"] == "directory":
            if not raw_path or path.is_symlink() or not path.is_dir():
                raise AppError("Registered folder is unavailable.", "BACKUP_SOURCE_UNAVAILABLE")
            resolved = path.resolve()
            return scan_directory_source(source, resolved, progress, cancel_check), None
        if not raw_path or path.is_symlink() or not path.is_file():
            raise AppError("Settings file is unavailable.", "BACKUP_SOURCE_UNAVAILABLE")
        resolved = path.resolve()
        return {
            entry_key(source): manifest_entry(resolved, source, "", progress, cancel_check),
        }, None
    except AppError as error:
        if error.code == "BACKUP_CANCELLED":
            raise
        return {}, {
            "source_id": source["id"],
            "label": source["label"],
            "path": raw_path,
            "category": source["category"],
            "message": error.message,
            "code": error.code,
        }
    except OSError:
        return {}, {
            "source_id": source["id"],
            "label": source["label"],
            "path": raw_path,
            "category": source["category"],
            "message": "Registered backup source is unavailable.",
            "code": "BACKUP_SOURCE_UNAVAILABLE",
        }


# Scans every registered source into one complete manifest without mutating originals.
def scan_sources(
    sources: list[dict[str, Any]],
    progress: SnapshotProgress | None = None,
    cancel_check: CancellationCheck | None = None,
) -> dict[str, Any]:
    """Return a deterministic manifest plus unavailable-source records."""

    entries: dict[str, dict[str, Any]] = {}
    errors = []
    # Sources are sorted by snapshot target so manifest order is stable across registry bucket ordering.
    for source in sorted(sources, key=lambda item: item["snapshot_path"].casefold()):
        ensure_backup_active(cancel_check)
        source_entries, source_error = scan_source(source, progress, cancel_check)
        entries.update(source_entries)
        if source_error:
            errors.append(source_error)
    total_bytes = sum(item["size"] for item in entries.values() if item["kind"] == "file")
    return {
        "schema_version": BACKUP_MANIFEST_SCHEMA_VERSION,
        "scanned_at": backup_timestamp(),
        "sources": [dict(source) for source in sources],
        "entries": entries,
        "errors": errors,
        "file_count": sum(item["kind"] in {"file", "link"} for item in entries.values()),
        "directory_count": sum(item["kind"] == "directory" for item in entries.values()),
        "total_bytes": total_bytes,
    }


# Returns the content identity fields that determine whether one entry changed.
def entry_identity(value: dict[str, Any]) -> tuple[Any, ...]:
    """Return comparable kind, size, digest, and link-target fields."""

    return (
        value.get("kind"),
        int(value.get("size") or 0),
        str(value.get("digest") or ""),
        str(value.get("link_target") or ""),
    )


# Collects stable source owners for changed entries before detailed paths are truncated for display.
def entry_source_ids(entries: dict[str, Any], keys: list[str]) -> set[str]:
    """Return nonempty source identifiers owning the requested manifest keys."""

    source_ids = set()
    for key in keys:
        entry = entries.get(key) if isinstance(entries.get(key), dict) else {}
        source_id = str(entry.get("source_id") or "").strip()
        if source_id:
            source_ids.add(source_id)
    return source_ids


# Compares two complete manifests and reports added, modified, and deleted snapshot-relative paths.
def manifest_diff(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Return bounded detailed changes and complete change counts."""

    previous_entries = previous.get("entries", {}) if isinstance(previous, dict) else {}
    current_entries = current.get("entries", {}) if isinstance(current, dict) else {}
    previous_keys = set(previous_entries)
    current_keys = set(current_entries)
    added = sorted(current_keys - previous_keys, key=str.casefold)
    deleted = sorted(previous_keys - current_keys, key=str.casefold)
    modified = sorted(
        (
            key
            for key in current_keys & previous_keys
            if entry_identity(current_entries[key]) != entry_identity(previous_entries[key])
        ),
        key=str.casefold,
    )
    details = [
        *({"kind": "added", "path": path} for path in added),
        *({"kind": "modified", "path": path} for path in modified),
        *({"kind": "deleted", "path": path} for path in deleted),
    ]
    details.sort(key=lambda item: (item["path"].casefold(), item["kind"]))
    # Source ownership remains complete even when the path-level display sample reaches its safe cap.
    changed_source_ids = entry_source_ids(current_entries, [*added, *modified])
    changed_source_ids.update(entry_source_ids(previous_entries, deleted))
    return {
        "has_changes": bool(details),
        "added": len(added),
        "modified": len(modified),
        "deleted": len(deleted),
        "total": len(details),
        "changes": details[:MAX_REPORTED_CHANGES],
        "truncated": len(details) > MAX_REPORTED_CHANGES,
        "changed_source_ids": sorted(changed_source_ids, key=str.casefold),
    }


# Selects entries owned by one stable source identifier for copy verification.
def entries_for_source(manifest: dict[str, Any], source_id: str) -> dict[str, dict[str, Any]]:
    """Return manifest entries belonging to source_id."""

    return {
        key: value
        for key, value in manifest.get("entries", {}).items()
        if value.get("source_id") == source_id
    }
