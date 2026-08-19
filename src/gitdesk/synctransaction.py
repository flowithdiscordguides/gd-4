"""Crash-recoverable destination replacement for Project Sync Chains."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from threading import RLock
from typing import Any
from uuid import uuid4

from gitdesk.errors import AppError
from gitdesk.syncchains import sync_timestamp
from gitdesk.syncmirror import build_verified_snapshot, fingerprint_directory
from gitdesk.syncmirror import normalize_sync_destination, normalize_sync_source, validate_mirror_paths


# Serializing mirror operations prevents two bridge workers from replacing related folders concurrently.
SYNC_TRANSACTION_LOCK = RLock()


# Writes the small recovery journal before each destructive rename boundary.
def write_journal(path: Path, payload: dict[str, Any]) -> None:
    """Persist a complete transaction journal beside the destination repository."""

    temporary_path = path.with_name(f"{path.name}.tmp")
    try:
        temporary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary_path.replace(path)
    except OSError as error:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise AppError("The synchronization recovery journal could not be written.", "SYNC_JOURNAL_FAILED") from error


# Loads a journal only when it contains the exact paths expected for this destination.
def read_journal(path: Path, destination: Path) -> dict[str, Any] | None:
    """Return a valid transaction journal for destination, or None when no journal exists."""

    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AppError("A prior synchronization journal is unreadable.", "SYNC_JOURNAL_INVALID") from error
    if not isinstance(payload, dict) or payload.get("destination") != str(destination):
        raise AppError("A prior synchronization journal does not match its destination.", "SYNC_JOURNAL_INVALID")
    return payload


# Removes a path without following a symbolic link outside the transaction workspace.
def remove_transaction_path(path: Path) -> None:
    """Remove a transaction file, link, or directory when it still exists."""

    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


# Returns whether a directory, file, or symbolic link contains the Git metadata entry.
def git_metadata_exists(path: Path) -> bool:
    """Return whether the repository root currently has a .git entry."""

    git_path = path / ".git"
    return git_path.exists() or git_path.is_symlink()


# Copies Git metadata into a staged working tree while leaving rollback metadata intact.
def copy_git_metadata(source: Path, destination: Path) -> None:
    """Copy a repository's .git directory, file, or link into a staged snapshot."""

    source_git = source / ".git"
    destination_git = destination / ".git"
    if source_git.is_symlink():
        destination_git.symlink_to(source_git.readlink(), target_is_directory=source_git.is_dir())
    elif source_git.is_dir():
        shutil.copytree(source_git, destination_git, symlinks=True)
    elif source_git.is_file():
        shutil.copy2(source_git, destination_git, follow_symlinks=False)
    else:
        raise AppError("The destination repository has no Git metadata.", "REPOSITORY_INVALID")


# Restores the original destination from a backup after an interrupted pre-install phase.
def restore_backup(destination: Path, staging: Path, backup: Path) -> None:
    """Restore destination and its .git entry from backup, then remove staging leftovers."""

    if not backup.exists():
        remove_transaction_path(staging)
        return
    backup_git = backup / ".git"
    destination_git = destination / ".git"
    if not git_metadata_exists(backup):
        if git_metadata_exists(destination):
            shutil.move(str(destination_git), str(backup_git))
        elif git_metadata_exists(staging):
            shutil.move(str(staging / ".git"), str(backup_git))
        else:
            raise OSError("No recoverable Git metadata remains for the destination repository.")
    remove_transaction_path(destination)
    backup.rename(destination)
    remove_transaction_path(staging)


# Recovers a prior crash deterministically: installed snapshots finish, earlier phases roll back.
def recover_interrupted_transaction(destination: Path, journal_path: Path) -> None:
    """Finalize or roll back one interrupted transaction before a new sync begins."""

    payload = read_journal(journal_path, destination)
    if not payload:
        return
    staging = Path(str(payload.get("staging") or ""))
    backup = Path(str(payload.get("backup") or ""))
    if staging.parent != destination.parent or backup.parent != destination.parent:
        raise AppError("A prior synchronization journal contains unsafe paths.", "SYNC_JOURNAL_INVALID")
    try:
        if payload.get("phase") == "installed" and destination.is_dir() and git_metadata_exists(destination):
            remove_transaction_path(staging)
            remove_transaction_path(backup)
        else:
            restore_backup(destination, staging, backup)
        journal_path.unlink(missing_ok=True)
    except OSError as error:
        raise AppError("A prior synchronization could not be recovered safely.", "SYNC_RECOVERY_FAILED") from error


# Recovers the deterministic transaction journal associated with one repository path.
def recover_destination_transaction(path_value: str) -> None:
    """Recover an interrupted Sync Chain replacement for one existing destination folder."""

    destination = Path(str(path_value or "")).expanduser().resolve()
    journal = destination.parent / f".gitdesk-sync-{destination.name}.journal.json"
    with SYNC_TRANSACTION_LOCK:
        recover_interrupted_transaction(destination, journal)


# MirrorTransaction retains the original folder until metadata persistence confirms the new receipt.
class MirrorTransaction:
    """Own one staged destination replacement and provide explicit commit or rollback boundaries."""

    # Stores paths and fingerprint results needed by bridge-level metadata persistence.
    def __init__(
        self,
        source: Path,
        destination: Path,
        staging: Path,
        backup: Path,
        journal: Path,
        snapshot: dict[str, Any],
    ) -> None:
        self.source = source
        self.destination = destination
        self.staging = staging
        self.backup = backup
        self.journal = journal
        self.snapshot = snapshot
        self.finished = False

    # Returns the persistent receipt shape saved only after installation succeeds.
    def receipt(self) -> dict[str, Any]:
        """Return a synchronization receipt for the installed snapshot."""

        return {
            "source_path": str(self.source),
            "destination_path": str(self.destination),
            "source_digest": self.snapshot["digest"],
            "destination_digest": self.snapshot["digest"],
            "synced_at": sync_timestamp(),
            "file_count": self.snapshot["file_count"],
            "directory_count": self.snapshot["directory_count"],
            "total_bytes": self.snapshot["total_bytes"],
        }

    # Finalizes the installed snapshot and reports non-fatal backup cleanup failure.
    def commit(self) -> str:
        """Remove recovery state after metadata save and return an optional cleanup warning."""

        self.finished = True
        try:
            self.journal.unlink(missing_ok=True)
            remove_transaction_path(self.backup)
            return ""
        except OSError:
            return f"Previous destination backup remains at {self.backup}"

    # Restores the original repository when metadata persistence or later validation fails.
    def rollback(self) -> None:
        """Restore the original destination working tree and clear transaction state."""

        if self.finished:
            return
        try:
            restore_backup(self.destination, self.staging, self.backup)
            self.journal.unlink(missing_ok=True)
            self.finished = True
        except OSError as error:
            raise AppError(
                f"Synchronization failed and automatic rollback needs attention at {self.backup}.",
                "SYNC_ROLLBACK_FAILED",
            ) from error


# Prepares and installs a complete snapshot while retaining the previous tree for bridge-level commit.
def begin_mirror_transaction(
    source_path: str,
    destination_path: str,
    ignored_paths: frozenset[str] = frozenset(),
) -> MirrorTransaction:
    """Install a filtered staged mirror and return its uncommitted transaction handle."""

    with SYNC_TRANSACTION_LOCK:
        source = normalize_sync_source(source_path)
        requested_destination = Path(str(destination_path or "")).expanduser().resolve()
        journal = requested_destination.parent / f".gitdesk-sync-{requested_destination.name}.journal.json"
        recover_interrupted_transaction(requested_destination, journal)
        destination = normalize_sync_destination(str(requested_destination))
        validate_mirror_paths(source, destination)
        transaction_id = uuid4().hex
        staging = destination.parent / f".gitdesk-sync-stage-{transaction_id}"
        backup = destination.parent / f".gitdesk-sync-backup-{transaction_id}"
        payload = {
            "destination": str(destination),
            "staging": str(staging),
            "backup": str(backup),
            "phase": "preparing",
        }
        try:
            snapshot = build_verified_snapshot(source, staging, ignored_paths)
            payload["phase"] = "staged"
            payload["new_digest"] = snapshot["digest"]
            write_journal(journal, payload)
            destination.rename(backup)
            payload["phase"] = "destination_moved"
            write_journal(journal, payload)
            copy_git_metadata(backup, staging)
            payload["phase"] = "metadata_copied"
            write_journal(journal, payload)
            staging.rename(destination)
            payload["phase"] = "installed"
            write_journal(journal, payload)
            installed = fingerprint_directory(destination)
            if installed["digest"] != snapshot["digest"]:
                raise AppError("Installed synchronization content failed verification.", "SYNC_INSTALL_VERIFY_FAILED")
            return MirrorTransaction(source, destination, staging, backup, journal, snapshot)
        except AppError:
            try:
                restore_backup(destination, staging, backup)
                journal.unlink(missing_ok=True)
            except OSError as rollback_error:
                raise AppError(
                    f"Synchronization failed and rollback needs attention at {backup}.",
                    "SYNC_ROLLBACK_FAILED",
                ) from rollback_error
            raise
        except OSError as error:
            try:
                restore_backup(destination, staging, backup)
                journal.unlink(missing_ok=True)
            except OSError as rollback_error:
                raise AppError(
                    f"Synchronization failed and rollback needs attention at {backup}.",
                    "SYNC_ROLLBACK_FAILED",
                ) from rollback_error
            raise AppError("The destination repository could not be replaced.", "SYNC_REPLACE_FAILED") from error
