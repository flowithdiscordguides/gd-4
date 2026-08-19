"""Collision-safe movement of image originals between registered Media albums."""

from __future__ import annotations

# Standard-library file descriptors keep cross-volume copies streamed, exclusive, and symlink-resistant.
import os
from pathlib import Path
import shutil
import stat
from typing import Any

from gitdesk.errors import AppError
from gitdesk.media_album_files import MAX_IMPORT_FILE_NAME_LENGTH, portable_leaf_name
from gitdesk.media_library import IMAGE_EXTENSIONS, selected_media_path
from gitdesk.media_library_store import MediaLibraryStore, album_directory


# Large originals are copied in bounded chunks before the source is removed.
MOVE_COPY_BUFFER_BYTES = 1024 * 1024


# Returns whether either album root contains the other and would therefore index the same moved file.
def album_roots_overlap(left: Path, right: Path) -> bool:
    """Return whether two resolved album roots overlap."""

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


# Reserves the first available direct-child filename without replacing any destination entry.
def reserve_destination(root: Path, name: str, mode: int) -> tuple[Path, int]:
    """Return an exclusive destination path and its open writable descriptor."""

    source_name = Path(name)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    for sequence in range(1, 10001):
        candidate_name = name if sequence == 1 else f"{source_name.stem} ({sequence}){source_name.suffix}"
        target = root / candidate_name
        try:
            return target, os.open(target, flags, mode)
        except FileExistsError:
            continue
        except OSError as error:
            raise AppError("Unable to reserve the destination photo.", "MEDIA_MOVE_DESTINATION_FAILED") from error
    raise AppError("Too many destination photos use that filename.", "MEDIA_MOVE_NAME_EXHAUSTED")


# Removes only the exclusive destination file created by the current failed operation.
def remove_failed_destination(path: Path | None) -> None:
    """Best-effort removal for one incomplete reserved destination."""

    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        pass


# Applies source timestamps without requesting unsupported no-follow behavior on Windows.
def preserve_original_times(target: Path, source_stat: os.stat_result) -> None:
    """Copy source access and modification nanoseconds onto the reserved destination file."""

    timestamps = (source_stat.st_atime_ns, source_stat.st_mtime_ns)
    # Passing False is valid only where Python reports the platform's no-follow capability.
    if os.utime in os.supports_follow_symlinks:
        os.utime(target, ns=timestamps, follow_symlinks=False)
        return
    os.utime(target, ns=timestamps)


# Streams one source descriptor into its reserved target, then removes the unchanged source path.
def transfer_original(source: Path, destination_root: Path) -> Path:
    """Move a regular non-symlink file across filesystems without overwriting destination content."""

    name = portable_leaf_name(
        source.name,
        MAX_IMPORT_FILE_NAME_LENGTH,
        "MEDIA_MOVE_NAME_EMPTY",
        "MEDIA_MOVE_NAME_INVALID",
    )
    source_flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    source_descriptor = -1
    target_descriptor = -1
    target = None
    try:
        source_descriptor = os.open(source, source_flags)
        source_stat = os.fstat(source_descriptor)
        if not stat.S_ISREG(source_stat.st_mode):
            raise AppError("Only regular photo files can be moved.", "MEDIA_MOVE_SOURCE_INVALID")
        target, target_descriptor = reserve_destination(
            destination_root,
            name,
            stat.S_IMODE(source_stat.st_mode) or 0o600,
        )
        with os.fdopen(source_descriptor, "rb") as source_file:
            source_descriptor = -1
            with os.fdopen(target_descriptor, "wb") as target_file:
                target_descriptor = -1
                shutil.copyfileobj(source_file, target_file, MOVE_COPY_BUFFER_BYTES)
                target_file.flush()
                os.fsync(target_file.fileno())
        preserve_original_times(target, source_stat)
        current_stat = source.stat(follow_symlinks=False)
        original_identity = (
            source_stat.st_dev,
            source_stat.st_ino,
            source_stat.st_size,
            source_stat.st_mtime_ns,
        )
        current_identity = (
            current_stat.st_dev,
            current_stat.st_ino,
            current_stat.st_size,
            current_stat.st_mtime_ns,
        )
        if current_identity != original_identity:
            raise AppError("The source photo changed while it was moving.", "MEDIA_MOVE_SOURCE_CHANGED")
        source.unlink()
        return target
    except AppError:
        remove_failed_destination(target)
        raise
    except OSError as error:
        remove_failed_destination(target)
        raise AppError("Unable to move the selected photo.", "MEDIA_MOVE_FAILED") from error
    finally:
        if source_descriptor >= 0:
            os.close(source_descriptor)
        if target_descriptor >= 0:
            os.close(target_descriptor)


# Resolves both registered albums and performs one explicit original-file move.
def move_media_item(
    source_album_id: Any,
    destination_album_id: Any,
    relative_value: Any,
    store: MediaLibraryStore | None = None,
) -> dict[str, Any]:
    """Move one contained image original into another non-overlapping registered album."""

    media_store = store or MediaLibraryStore()
    source_album, source = selected_media_path(media_store, source_album_id, relative_value)
    destination_album = media_store.require_album(destination_album_id)
    if source_album["id"] == destination_album["id"]:
        raise AppError("Choose a different destination album.", "MEDIA_MOVE_SAME_ALBUM")
    if source.suffix.lower() not in IMAGE_EXTENSIONS:
        raise AppError("Only photos can be moved between albums.", "MEDIA_MOVE_IMAGE_REQUIRED")
    source_root = album_directory(source_album["path"])
    destination_root = album_directory(destination_album["path"])
    if album_roots_overlap(source_root, destination_root):
        raise AppError("Overlapping album folders cannot be move destinations.", "MEDIA_MOVE_ALBUM_OVERLAP")
    target = transfer_original(source, destination_root)
    return {
        "source_album_id": source_album["id"],
        "destination_album_id": destination_album["id"],
        "destination_album_name": destination_album["name"],
        "source_path": str(relative_value or ""),
        "destination_path": target.name,
    }
