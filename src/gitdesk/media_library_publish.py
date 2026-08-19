"""Publish folder-backed Media Mode albums as versioned Shared Resources."""

from __future__ import annotations

# Standard-library paths and file operations support streamed copies and recoverable working-folder replacement.
from pathlib import Path
import shutil
import tempfile
from typing import Any
from uuid import uuid4

# GitDesk catalog and album services enforce resource identity, media filtering, and explicit releases.
from gitdesk import aiskills
from gitdesk.errors import AppError
from gitdesk.media_library import album_media_files
from gitdesk.media_library_store import MediaLibraryStore
from gitdesk.sharedresource_releases import record_release
from gitdesk.sharedresource_store import SharedResourceStore


# All album files live below this stable project-relative namespace when the resource is installed.
MEDIA_RESOURCE_DIRECTORY = "media"


# Confirms a first-time resource name is not already owned by another catalog folder or Media Mode album.
def available_resource_name(
    store: MediaLibraryStore,
    album_id: str,
    name_value: Any,
) -> str:
    """Return a valid unused resource name for one first publication."""

    name = aiskills.clean_category_name(str(name_value or ""))
    registry = store.load()
    linked_elsewhere = any(
        album["id"] != album_id and album.get("resource_name") == name
        for album in registry["albums"]
    )
    # Existing disk sources may be legacy, bundled, or writable and cannot be silently replaced.
    if linked_elsewhere or aiskills.category_source_paths(name):
        raise AppError(
            "That Shared Resource name is already in use.",
            "MEDIA_RESOURCE_NAME_IN_USE",
        )
    return name


# Copies supported album files into a staging resource without loading large videos into memory.
def stage_album_resource(album: dict[str, str], resource_name: str, writable_root: Path) -> Path:
    """Return a staged dedicated Shared Resource folder containing the album media."""

    staging = Path(tempfile.mkdtemp(prefix=".media-publish-", dir=str(writable_root)))
    resource_root = staging / resource_name
    media_root = resource_root / MEDIA_RESOURCE_DIRECTORY / resource_name
    try:
        media_files = album_media_files(album)
        if not media_files:
            raise AppError(
                "This album has no supported images or videos to publish.",
                "MEDIA_ALBUM_EMPTY",
            )
        # Relative media paths preserve the album's organization beneath its dedicated project namespace.
        for item, source in media_files:
            target = media_root / Path(item["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    except (OSError, AppError) as error:
        shutil.rmtree(staging, ignore_errors=True)
        if isinstance(error, AppError):
            raise
        raise AppError(
            "Unable to prepare the album for Shared Resources.",
            "MEDIA_RESOURCE_COPY_FAILED",
        ) from error
    return staging


# Swaps one dedicated resource working folder while retaining a backup until release recording succeeds.
def replace_working_resource(staging: Path, target: Path) -> Path | None:
    """Install the staged working folder and return its recoverable prior-folder backup."""

    staged_resource = staging / target.name
    backup = target.with_name(f".{target.name}.media-backup-{uuid4().hex}")
    try:
        if target.exists():
            target.rename(backup)
        staged_resource.rename(target)
        staging.rmdir()
        return backup if backup.exists() else None
    except OSError as error:
        if not target.exists() and backup.exists():
            backup.rename(target)
        shutil.rmtree(staging, ignore_errors=True)
        raise AppError(
            "Unable to replace the album Shared Resource working folder.",
            "MEDIA_RESOURCE_REPLACE_FAILED",
        ) from error


# Restores the previous editable working folder after release recording fails.
def restore_working_resource(target: Path, backup: Path | None) -> None:
    """Restore the prior working folder or remove the failed first-publication folder."""

    if target.exists():
        shutil.rmtree(target)
    if backup and backup.exists():
        backup.rename(target)


# Publishes an album to its dedicated resource and advances only when its supported contents changed.
def publish_album(
    album_id: Any,
    resource_name_value: Any = "",
    media_store: MediaLibraryStore | None = None,
    resource_store: SharedResourceStore | None = None,
) -> dict[str, Any]:
    """Mirror one album into a dedicated Shared Resource and record its explicit release."""

    album_store = media_store or MediaLibraryStore()
    album = album_store.require_album(album_id)
    saved_name = album.get("resource_name") or ""
    resource_name = saved_name or available_resource_name(
        album_store,
        album["id"],
        resource_name_value,
    )
    writable_root = aiskills.writable_categories_root(create=True)
    target = writable_root / resource_name
    foreign_sources = [
        path
        for path in aiskills.category_source_paths(resource_name)
        if path.resolve() != target.resolve()
    ]
    # A later name collision cannot be folded into the dedicated album resource during an update.
    if foreign_sources:
        raise AppError(
            "This album's Shared Resource name now conflicts with another resource source.",
            "MEDIA_RESOURCE_NAME_IN_USE",
        )
    staging = stage_album_resource(album, resource_name, writable_root)
    previous_registry = album_store.load()
    linked_first_release = not bool(saved_name)
    if linked_first_release:
        try:
            album_store.set_resource(album["id"], resource_name)
        except AppError:
            shutil.rmtree(staging, ignore_errors=True)
            raise
    backup = None
    replaced = False
    try:
        backup = replace_working_resource(staging, target)
        replaced = True
        release = record_release(resource_name, resource_store)
    except Exception:
        if replaced:
            restore_working_resource(target, backup)
        if linked_first_release:
            album_store.write(previous_registry)
        raise
    if backup and backup.exists():
        shutil.rmtree(backup)
    return {
        "album_id": album["id"],
        "resource_name": resource_name,
        "resource_path": str(target),
        "release": release,
    }
