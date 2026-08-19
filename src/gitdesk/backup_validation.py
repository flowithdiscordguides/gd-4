"""Installed-tree and prior-baseline validation for versioned Backup snapshots."""

from __future__ import annotations

# Filesystem type checks establish physical installation without following symbolic links.
import os
from pathlib import Path
import stat
from typing import Any

# Manifest hashing prevents a control file from claiming missing or corrupted content is current.
from gitdesk.backup_manifest import hash_file
from gitdesk.backup_progress import CancellationCheck, SnapshotProgress, ensure_backup_active
from gitdesk.errors import AppError


# Resolves only manifest-owned relative keys beneath one dated Backup folder.
def installed_entry_path(snapshot: Path, entry_key: str) -> Path:
    """Return one safe installed manifest path or reject an invalid control-file key."""

    relative = Path(entry_key)
    invalid_part = any(part in {"", ".", ".."} for part in relative.parts)
    if relative.is_absolute() or not relative.parts or invalid_part:
        raise AppError(
            "Backup manifest contains an invalid installed path.",
            "BACKUP_MANIFEST_PATH_INVALID",
            {"path": entry_key},
        )
    return snapshot.joinpath(*relative.parts)


# Confirms the installed dated folder physically owns every selected manifest entry.
def validate_installed_snapshot(snapshot: Path, manifest: dict[str, Any]) -> None:
    """Raise unless every installed entry has its expected type, size, and link target."""

    if snapshot.is_symlink() or not snapshot.is_dir():
        raise AppError("The completed backup folder was not installed.", "BACKUP_INSTALL_VERIFY_FAILED")
    for entry_key, entry in manifest.get("entries", {}).items():
        path = installed_entry_path(snapshot, entry_key)
        try:
            mode = path.lstat().st_mode
            kind = entry.get("kind")
            matches = (
                (kind == "directory" and stat.S_ISDIR(mode))
                or (kind == "file" and stat.S_ISREG(mode) and path.stat().st_size == int(entry.get("size") or 0))
                or (
                    kind == "link"
                    and stat.S_ISLNK(mode)
                    and os.readlink(path) == str(entry.get("link_target") or "")
                )
            )
        except OSError as error:
            raise AppError(
                "A selected item is missing from the installed backup.",
                "BACKUP_INSTALL_VERIFY_FAILED",
                {"path": entry_key, "reason": str(error or "Installed item is unavailable.")[:300]},
            ) from error
        if not matches:
            raise AppError(
                "A selected item was not installed correctly in the backup.",
                "BACKUP_INSTALL_VERIFY_FAILED",
                {"path": entry_key},
            )


# Re-reads exactly the manifest-owned paths so destination-generated metadata never becomes claimed content.
def verify_snapshot_content(
    snapshot: Path,
    manifest: dict[str, Any],
    progress: SnapshotProgress | None = None,
    cancel_check: CancellationCheck | None = None,
) -> None:
    """Raise unless every manifest-owned installed path matches its exact content identity."""

    if snapshot.is_symlink() or not snapshot.is_dir():
        raise AppError("The backup snapshot is unavailable for verification.", "BACKUP_VERIFY_FAILED")
    # Only claimed entries are read; unclaimed sidecars at explicitly skipped paths are ignored factually.
    for entry_key, entry in manifest.get("entries", {}).items():
        ensure_backup_active(cancel_check)
        path = installed_entry_path(snapshot, entry_key)
        kind = entry.get("kind")
        try:
            mode = path.lstat().st_mode
            if kind == "directory":
                matches = stat.S_ISDIR(mode)
            elif kind == "link":
                matches = stat.S_ISLNK(mode) and os.readlink(path) == str(entry.get("link_target") or "")
                if matches and progress:
                    progress.advance_read(entry_key, item_complete=True)
            elif kind == "file" and stat.S_ISREG(mode):
                digest, byte_count = hash_file(path, entry_key, progress, cancel_check)
                matches = byte_count == int(entry.get("size") or 0) and digest == str(entry.get("digest") or "")
            else:
                matches = False
        except AppError as error:
            if error.code == "BACKUP_CANCELLED":
                raise
            raise AppError(
                "Backup snapshot verification could not read an installed item.",
                "BACKUP_VERIFY_FAILED",
                {"path": entry_key},
            ) from error
        except OSError as error:
            raise AppError(
                "Backup snapshot verification could not read an installed item.",
                "BACKUP_VERIFY_FAILED",
                {"path": entry_key},
            ) from error
        if not matches:
            raise AppError(
                "Backup snapshot content does not match its manifest.",
                "BACKUP_VERIFY_FAILED",
                {"path": entry_key},
            )


# Re-hashes a prior dated folder before allowing its manifest to suppress a new backup copy.
def prior_snapshot_matches_manifest(
    snapshot: Path,
    manifest: dict[str, Any],
    progress: SnapshotProgress | None = None,
    cancel_check: CancellationCheck | None = None,
) -> bool:
    """Return whether every prior selected source still matches its persisted manifest bytes."""

    try:
        verify_snapshot_content(snapshot, manifest, progress, cancel_check)
    except AppError as error:
        if error.code == "BACKUP_CANCELLED":
            raise
        return False
    return True
