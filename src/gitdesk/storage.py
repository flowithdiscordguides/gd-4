"""Shared private storage paths and atomic file replacement for GitDesk app data."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from typing import Any

from platformdirs import PlatformDirs

from gitdesk import APP_NAME
from gitdesk.errors import AppError


# Every settings, registry, and token transaction shares this re-entrant lock so worker threads cannot lose updates.
APP_STORAGE_LOCK = RLock()


# Identifies this checkout only when GitDesk is imported directly from repository source.
def source_checkout_root() -> Path | None:
    """Return the active GitDesk source root, or None for an installed or frozen package."""

    candidate = Path(__file__).resolve().parents[2]
    return candidate if (candidate / "pyproject.toml").is_file() else None


# Rejects app-owned paths that would place runtime data beneath the source-controlled checkout.
def private_storage_path(path: Path) -> Path:
    """Return a resolved app-storage path that is outside the GitDesk source checkout."""

    resolved = path.expanduser().resolve()
    checkout_root = source_checkout_root()
    if checkout_root is not None and (resolved == checkout_root or checkout_root in resolved.parents):
        raise AppError(
            "GitDesk private data cannot be stored inside the application source repository.",
            "APP_STORAGE_PATH_UNSAFE",
        )
    return resolved


# Resolves the single platform config directory used by source runs and packaged desktop builds.
def app_config_path() -> Path:
    """Return GitDesk's platform-specific configuration directory."""

    return private_storage_path(PlatformDirs(APP_NAME, "XanderApps").user_config_path)


# Resolves app-owned editable content separately from config JSON and source-controlled bundled assets.
def app_data_path() -> Path:
    """Return GitDesk's platform-specific user-data directory outside the source checkout."""

    return private_storage_path(PlatformDirs(APP_NAME, "XanderApps").user_data_path)


# Flushes a directory after atomic replacement when the host filesystem supports directory file descriptors.
def flush_parent_directory(path: Path) -> None:
    """Best-effort flush the directory containing a replaced private file."""

    directory_descriptor: int | None = None
    try:
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        os.fsync(directory_descriptor)
    except OSError:
        # The file replacement is already atomic; unsupported directory fsync must not turn a save into data loss.
        return
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)


# Writes a private file beside its destination, flushes it, and atomically replaces the old complete file.
def atomic_write_private_bytes(
    path: Path,
    content: bytes,
    directory_mode: int,
    file_mode: int,
) -> None:
    """Atomically write private bytes to path with owner-only permissions."""

    path = private_storage_path(path)
    temporary_path: Path | None = None
    with APP_STORAGE_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(directory_mode)
        file_descriptor, raw_temporary_path = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(raw_temporary_path)
        try:
            with os.fdopen(file_descriptor, "wb") as output_file:
                output_file.write(content)
                output_file.flush()
                os.fsync(output_file.fileno())
            temporary_path.chmod(file_mode)
            os.replace(temporary_path, path)
            temporary_path = None
            path.chmod(file_mode)
            flush_parent_directory(path)
        finally:
            # A failed write keeps the old destination intact and removes only the unused temporary file.
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass


# Serializes JSON completely before touching disk so encoding failures cannot damage the previous settings file.
def atomic_write_private_json(
    path: Path,
    payload: dict[str, Any],
    directory_mode: int,
    file_mode: int,
) -> None:
    """Atomically write a formatted private JSON object to path."""

    encoded_payload = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    atomic_write_private_bytes(path, encoded_payload, directory_mode, file_mode)
