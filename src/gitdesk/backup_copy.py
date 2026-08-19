"""Manifest-owned copying for complete or partially selected Backup Mode sources."""

from __future__ import annotations

# Link and filesystem helpers reproduce only entries proven by the pre-copy manifest.
import errno
import hashlib
import os
from pathlib import Path
import stat
from typing import Any

# Manifest ownership keeps copying and later verification on the exact same selected paths.
from gitdesk.backup_manifest import entries_for_source
from gitdesk.backup_progress import CancellationCheck, SnapshotProgress, ensure_backup_active
from gitdesk.backup_skips import skipped_item
from gitdesk.errors import AppError


# Copy chunks provide responsive cancellation and factual byte updates for large files.
BACKUP_COPY_CHUNK_SIZE = 1024 * 1024

# These destination errors affect the transaction rather than one path, so continuing would misreport recovery.
SYSTEMIC_DESTINATION_ERRNOS = {
    getattr(errno, "EDQUOT", 122),
    getattr(errno, "EIO", 5),
    getattr(errno, "ENODEV", 19),
    getattr(errno, "ENOENT", 2),
    getattr(errno, "ENOSPC", 28),
    getattr(errno, "ENXIO", 6),
    getattr(errno, "EROFS", 30),
    getattr(errno, "ESTALE", 116),
}


# BackupItemError marks one manifest entry as skippable without weakening transaction-wide failures.
class BackupItemError(Exception):
    """Describe one source or destination item that can be skipped safely."""

    # Retains a stable code and bounded operating-system reason for the durable skipped ledger.
    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = str(reason or "The item could not be copied.")[:500]


# Uses the operating-system explanation without leaking source or staging locations into visible error text.
def os_error_reason(error: OSError, fallback: str) -> str:
    """Return one bounded path-free operating-system failure reason."""

    return str(getattr(error, "strerror", "") or fallback)[:300]


# Records a destination metadata limitation without misrepresenting copied file content as missing.
def record_metadata_warning(
    warnings: list[dict[str, str]] | None,
    display_path: str,
    operation: str,
    error: Exception,
) -> None:
    """Append one safe backup-relative metadata warning when a collector is available."""

    if warnings is None:
        return
    warnings.append({
        "path": display_path,
        "operation": operation,
        "message": str(error or "Destination filesystem does not support this metadata.")[:300],
    })


# Preserves portable mode and timestamp fields without letting removable-drive limitations erase content.
def apply_portable_metadata(
    source: Path,
    target: Path,
    display_path: str,
    warnings: list[dict[str, str]] | None,
) -> None:
    """Apply supported mode and time metadata, recording destination limitations as warnings."""

    try:
        source_stat = source.stat(follow_symlinks=False)
    except OSError as error:
        record_metadata_warning(warnings, display_path, "source metadata", error)
        return
    try:
        os.chmod(target, stat.S_IMODE(source_stat.st_mode), follow_symlinks=False)
    except (NotImplementedError, OSError) as error:
        record_metadata_warning(warnings, display_path, "permissions", error)
    try:
        os.utime(
            target,
            ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns),
            follow_symlinks=False,
        )
    except (NotImplementedError, OSError) as error:
        record_metadata_warning(warnings, display_path, "timestamps", error)


# Confirms a source entry still has the manifest-owned type before any copy operation follows it.
def validate_source_entry(path: Path, entry: dict[str, Any]) -> None:
    """Raise one skippable item error when a source changed after manifest creation."""

    try:
        mode = path.lstat().st_mode
        kind = entry.get("kind")
        valid = (
            (kind == "directory" and stat.S_ISDIR(mode))
            or (kind == "file" and stat.S_ISREG(mode))
            or (kind == "link" and stat.S_ISLNK(mode))
        )
        if not valid:
            raise BackupItemError("BACKUP_SOURCE_CHANGED", "The source item changed type during backup.")
        if kind == "link" and os.readlink(path) != str(entry.get("link_target") or ""):
            raise BackupItemError("BACKUP_SOURCE_CHANGED", "The source link changed during backup.")
    except BackupItemError:
        raise
    except OSError as error:
        reason = os_error_reason(error, "The source item became unavailable.")
        raise BackupItemError("BACKUP_SOURCE_CHANGED", reason) from error


# Converts a manifest key back to its safe source-relative path.
def source_relative_path(source: dict[str, Any], entry_key: str) -> str:
    """Return the source-relative portion of one owned manifest key."""

    base = str(source["snapshot_path"])
    if entry_key == base:
        return ""
    prefix = f"{base}/"
    if not entry_key.startswith(prefix):
        raise AppError("A backup manifest path is outside its source target.", "BACKUP_MANIFEST_PATH_INVALID")
    return entry_key[len(prefix):]


# Creates the owned destination parent while retaining the exact failed manifest path in diagnostics.
def destination_item_error(error: OSError, display_path: str, message: str) -> BackupItemError:
    """Return an item error or raise when the destination itself cannot continue safely."""

    if error.errno in SYSTEMIC_DESTINATION_ERRNOS:
        raise AppError(
            "The backup destination cannot continue accepting backup data.",
            "BACKUP_DESTINATION_WRITE_FAILED",
            {"path": display_path, "reason": os_error_reason(error, message)},
        ) from error
    return BackupItemError("BACKUP_DESTINATION_ITEM_FAILED", os_error_reason(error, message))


# Creates the owned destination parent while distinguishing item collisions from drive-wide failures.
def ensure_target_parent(target: Path, display_path: str) -> None:
    """Create target's parent directories or raise a classified destination error."""

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise destination_item_error(error, display_path, "The parent folder could not be created.")


# Recreates one manifest-owned link without following its target during the copy.
def copy_symbolic_link(target: Path, entry: dict[str, Any], display_path: str) -> None:
    """Create one selected symbolic link or raise a path-specific destination error."""

    try:
        os.symlink(str(entry.get("link_target") or ""), target)
    except OSError as error:
        item_error = destination_item_error(error, display_path, "The symbolic link could not be created.")
        item_error.code = "BACKUP_LINK_COPY_FAILED"
        raise item_error from error


# Removes only a partial file created by the active item attempt before continuing to later entries.
def remove_partial_file(target: Path, display_path: str) -> None:
    """Delete one transaction-owned partial file or stop if cleanup itself fails."""

    try:
        target.unlink(missing_ok=True)
    except OSError as error:
        raise AppError(
            "A partial backup item could not be cleaned up safely.",
            "BACKUP_PARTIAL_CLEANUP_FAILED",
            {"path": display_path, "reason": str(error or "Partial-file cleanup failed.")[:300]},
        ) from error


# Copies one regular file in bounded chunks before applying its source metadata.
def copy_regular_file(
    source: Path,
    target: Path,
    display_path: str,
    expected_entry: dict[str, Any],
    progress: SnapshotProgress | None,
    cancel_check: CancellationCheck | None,
    metadata_warnings: list[dict[str, str]] | None = None,
) -> None:
    """Copy and hash one regular file with exact progress and item-local cleanup."""

    try:
        source_file = source.open("rb")
    except OSError as error:
        reason = os_error_reason(error, "The source file could not be opened.")
        raise BackupItemError("BACKUP_SOURCE_COPY_FAILED", reason) from error
    try:
        target_file = target.open("xb")
    except OSError as error:
        source_file.close()
        raise destination_item_error(error, display_path, "The destination file could not be created.")
    digest = hashlib.sha256()
    byte_count = 0
    try:
        with source_file, target_file:
            while True:
                ensure_backup_active(cancel_check)
                try:
                    chunk = source_file.read(BACKUP_COPY_CHUNK_SIZE)
                except OSError as error:
                    raise BackupItemError(
                        "BACKUP_SOURCE_COPY_FAILED",
                        os_error_reason(error, "Source read failed."),
                    ) from error
                if not chunk:
                    break
                try:
                    written = target_file.write(chunk)
                    if written != len(chunk):
                        raise OSError("Backup destination accepted a partial file write.")
                except OSError as error:
                    raise destination_item_error(error, display_path, "The destination write failed.") from error
                digest.update(chunk)
                byte_count += written
                if progress:
                    progress.advance_copy(display_path, written)
            try:
                target_file.flush()
                os.fsync(target_file.fileno())
            except OSError as error:
                raise destination_item_error(error, display_path, "The destination could not save the file.")
        expected_size = int(expected_entry.get("size") or 0)
        expected_digest = str(expected_entry.get("digest") or "")
        if byte_count != expected_size or digest.hexdigest() != expected_digest:
            raise BackupItemError("BACKUP_SOURCE_CHANGED", "The source file changed while it was being copied.")
        apply_portable_metadata(source, target, display_path, metadata_warnings)
        if progress:
            progress.advance_copy(display_path, item_complete=True)
    except BackupItemError:
        remove_partial_file(target, display_path)
        raise


# Copies exactly the pre-scanned entries for one source into its grouped staging target.
def copy_manifest_source(
    source: dict[str, Any],
    staging: Path,
    manifest: dict[str, Any],
    progress: SnapshotProgress | None = None,
    cancel_check: CancellationCheck | None = None,
    metadata_warnings: list[dict[str, str]] | None = None,
    original_source: dict[str, Any] | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    """Copy one selected source and return its target plus every factual skipped entry."""

    source_path = Path(source["path"]).expanduser()
    source_root = source_path.absolute()
    target_root = staging / Path(source["snapshot_path"])
    entries = entries_for_source(manifest, str(source["id"]))
    ordered_entries = sorted(
        entries.items(),
        key=lambda item: (
            source_relative_path(source, item[0]).count("/"),
            item[1].get("kind") != "directory",
            item[0].casefold(),
        ),
    )
    copied_directories = []
    skipped_items = []
    skipped_directories = []
    for key, entry in ordered_entries:
        ensure_backup_active(cancel_check)
        relative_path = source_relative_path(source, key)
        ledger_source = original_source or source
        parent_skip = next(
            (
                path
                for path in skipped_directories
                if not path or relative_path.startswith(f"{path}/")
            ),
            None,
        )
        if parent_skip is not None:
            skipped_items.append(skipped_item(
                ledger_source,
                key,
                relative_path,
                entry,
                "BACKUP_PARENT_SKIPPED",
                "A parent folder could not be copied, so this item was not attempted.",
            ))
            if progress:
                progress.advance_copy(key)
            continue
        if source["kind"] == "directory":
            current_source = source_root / Path(relative_path) if relative_path else source_root
            current_target = target_root / Path(relative_path) if relative_path else target_root
        else:
            current_source = source_root
            current_target = target_root
        try:
            validate_source_entry(current_source, entry)
            ensure_target_parent(current_target, key)
            if entry["kind"] == "directory":
                try:
                    current_target.mkdir(parents=True, exist_ok=False)
                except OSError as error:
                    raise destination_item_error(
                        error,
                        key,
                        "The destination folder could not be created.",
                    ) from error
                copied_directories.append((current_source, current_target))
            elif entry["kind"] == "link":
                copy_symbolic_link(current_target, entry, key)
                if progress:
                    progress.advance_copy(key, item_complete=True)
            elif entry["kind"] == "file":
                copy_regular_file(
                    current_source,
                    current_target,
                    key,
                    entry,
                    progress,
                    cancel_check,
                    metadata_warnings,
                )
            else:
                raise AppError("A backup manifest entry type is unsupported.", "BACKUP_MANIFEST_ENTRY_INVALID")
        except BackupItemError as error:
            skipped_items.append(skipped_item(
                ledger_source,
                key,
                relative_path,
                entry,
                error.code,
                error.reason,
            ))
            if entry.get("kind") == "directory":
                skipped_directories.append(relative_path)
            if progress:
                progress.advance_copy(key)
    # Directory metadata is applied after children so writes do not immediately replace source timestamps.
    for current_source, current_target in reversed(copied_directories):
        ensure_backup_active(cancel_check)
        relative_path = current_target.relative_to(staging).as_posix()
        apply_portable_metadata(current_source, current_target, relative_path, metadata_warnings)
    return target_root, skipped_items
