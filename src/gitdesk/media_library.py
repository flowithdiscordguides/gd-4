"""Folder-backed album discovery, paging, previews, and native opening for Media Mode."""

from __future__ import annotations

# Standard-library helpers encode bounded previews, scan folders, sort records, and validate relative paths.
import base64
from datetime import datetime
import os
from pathlib import Path, PurePosixPath
from typing import Any

# GitDesk boundaries provide structured errors, bounded thumbnailing, private albums, and native opening.
from gitdesk.errors import AppError
from gitdesk.media_library_store import MediaLibraryStore, album_directory
from gitdesk.media_thumbnail import create_media_thumbnail
from gitdesk.nativeopen import open_folder, open_path


# Supported image files remain useful album content even when a format has no safe inline preview.
IMAGE_EXTENSIONS = {
    ".arw", ".avif", ".bmp", ".cr2", ".dng", ".gif", ".heic", ".heif", ".ico", ".jpeg", ".jpg",
    ".nef", ".png", ".psd", ".raw", ".svg", ".tif", ".tiff", ".webp",
}

# Common project video formats are indexed without loading their potentially large bytes into the WebUI.
VIDEO_EXTENSIONS = {
    ".3gp", ".avi", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".mts", ".webm",
}

# One page keeps DOM and bridge payloads bounded for libraries containing thousands of files.
DEFAULT_PAGE_SIZE = 48
MAX_PAGE_SIZE = 96

# Thumbnail decoders stream from disk; this ceiling rejects implausibly large individual library entries.
MAX_MEDIA_PREVIEW_SOURCE_BYTES = 8 * 1024 * 1024 * 1024

# Search input is bounded because it is a filter, not a durable media field.
MAX_SEARCH_LENGTH = 120

# Frontend item keys stay bounded before any component is resolved beneath an album.
MAX_MEDIA_PATH_LENGTH = 1024


# Raises directory-walk errors so unreadable album regions cannot be mistaken for an empty successful scan.
def raise_walk_error(error: OSError) -> None:
    """Propagate an album traversal error to the structured scan boundary."""

    raise error


# Returns whether a file suffix belongs to Media Mode and which semantic kind it represents.
def media_kind(path: Path) -> str:
    """Return image, video, or an empty string for an unsupported file."""

    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return ""


# Formats byte counts into compact factual labels for tiles and the selected-item inspector.
def size_label(size: int) -> str:
    """Return a human-readable binary byte-size label."""

    value = float(max(0, size))
    units = ("B", "KB", "MB", "GB", "TB")
    unit = units[0]
    # Repeated division keeps very large videos readable without losing the original byte count in state.
    for candidate in units:
        unit = candidate
        if value < 1024 or candidate == units[-1]:
            break
        value /= 1024
    precision = 0 if unit == "B" or value >= 100 else 1
    return f"{value:.{precision}f} {unit}"


# Converts one contained media file into frontend-safe metadata without exposing a direct file URL.
def media_item(root: Path, path: Path) -> dict[str, Any] | None:
    """Return one media record, or None when the file became unavailable during scanning."""

    kind = media_kind(path)
    if not kind or path.is_symlink():
        return None
    try:
        stat = path.stat()
        resolved = path.resolve()
        relative_path = resolved.relative_to(root).as_posix()
    except (OSError, ValueError):
        return None
    if not path.is_file():
        return None
    modified = datetime.fromtimestamp(stat.st_mtime).astimezone()
    return {
        "path": relative_path,
        "name": path.name,
        "kind": kind,
        "extension": path.suffix.lower().lstrip(".").upper(),
        "size": stat.st_size,
        "size_label": size_label(stat.st_size),
        "modified": stat.st_mtime,
        "modified_label": modified.strftime("%Y-%m-%d %H:%M"),
        "preview_available": stat.st_size <= MAX_MEDIA_PREVIEW_SOURCE_BYTES,
    }


# Walks one album without following symlink directories or indexing hidden metadata.
def album_media_files(album: dict[str, str]) -> list[tuple[dict[str, Any], Path]]:
    """Return supported media metadata and physical paths for one available album."""

    root = album_directory(album.get("path"))
    discovered = []
    try:
        walker = os.walk(root, followlinks=False, onerror=raise_walk_error)
        # Directory pruning prevents hidden caches and symbolic-link trees from entering the album boundary.
        for current_root, directory_names, file_names in walker:
            current = Path(current_root)
            directory_names[:] = [
                name
                for name in directory_names
                if not name.startswith(".") and not (current / name).is_symlink()
            ]
            for file_name in file_names:
                if file_name.startswith("."):
                    continue
                path = current / file_name
                item = media_item(root, path)
                if item:
                    discovered.append((item, path))
    except OSError as error:
        raise AppError("Unable to scan the selected album.", "MEDIA_ALBUM_SCAN_FAILED") from error
    return discovered


# Returns a lightweight rail record and reports disconnected album folders without dropping their metadata.
def album_payload(album: dict[str, str], active: bool) -> dict[str, Any]:
    """Return frontend-safe album identity and availability metadata."""

    try:
        path = album_directory(album.get("path"))
        exists = True
        location = str(path)
    except AppError:
        exists = False
        location = str(album.get("path") or "")
    return {
        **album,
        "path": location,
        "exists": exists,
        "active": active,
    }


# Applies the requested stable sort after scanning so paging never changes item order between renders.
def sorted_media(items: list[dict[str, Any]], sort_value: Any) -> tuple[list[dict[str, Any]], str]:
    """Return sorted media rows and the accepted sort identifier."""

    sort = str(sort_value or "name").strip().lower()
    if sort == "newest":
        return sorted(items, key=lambda item: (-item["modified"], item["path"].casefold())), sort
    if sort == "size":
        return sorted(items, key=lambda item: (-item["size"], item["path"].casefold())), sort
    return sorted(items, key=lambda item: item["path"].casefold()), "name"


# Builds one bounded page from the selected album while leaving every other album unscanned.
def library_state(
    store: MediaLibraryStore | None = None,
    query_value: Any = "",
    kind_value: Any = "all",
    sort_value: Any = "name",
    page_value: Any = 1,
    page_size_value: Any = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    """Return album rail state and one filtered page of selected-album media."""

    media_store = store or MediaLibraryStore()
    registry = media_store.load()
    active_id = registry["active_album_id"]
    albums = [album_payload(album, album["id"] == active_id) for album in registry["albums"]]
    active_album = next((album for album in registry["albums"] if album["id"] == active_id), None)
    query = str(query_value or "").strip()[:MAX_SEARCH_LENGTH]
    kind = str(kind_value or "all").strip().lower()
    if kind not in {"all", "image", "video"}:
        kind = "all"
    try:
        page = max(1, int(page_value))
        page_size = min(MAX_PAGE_SIZE, max(1, int(page_size_value)))
    except (TypeError, ValueError):
        page = 1
        page_size = DEFAULT_PAGE_SIZE
    if not active_album:
        return {
            "albums": albums,
            "parent_favorites": registry["parent_favorites"],
            "active_album": None,
            "items": [],
            "query": query,
            "kind": kind,
            "sort": "name",
            "page": 1,
            "page_count": 0,
            "page_size": page_size,
            "total_count": 0,
            "filtered_count": 0,
            "image_count": 0,
            "video_count": 0,
        }
    try:
        discovered = [item for item, unused_path in album_media_files(active_album)]
    except AppError as error:
        if error.code != "MEDIA_ALBUM_PATH_INVALID":
            raise
        discovered = []
    image_count = sum(1 for item in discovered if item["kind"] == "image")
    video_count = sum(1 for item in discovered if item["kind"] == "video")
    filtered = [
        item
        for item in discovered
        if (kind == "all" or item["kind"] == kind)
        and (not query or query.casefold() in item["path"].casefold())
    ]
    filtered, sort = sorted_media(filtered, sort_value)
    page_count = (len(filtered) + page_size - 1) // page_size
    page = min(page, page_count) if page_count else 1
    start = (page - 1) * page_size
    return {
        "albums": albums,
        "parent_favorites": registry["parent_favorites"],
        "active_album": album_payload(active_album, True),
        "items": filtered[start:start + page_size],
        "query": query,
        "kind": kind,
        "sort": sort,
        "page": page,
        "page_count": page_count,
        "page_size": page_size,
        "total_count": len(discovered),
        "filtered_count": len(filtered),
        "image_count": image_count,
        "video_count": video_count,
    }


# Normalizes a frontend media key before it can address a file below an album.
def clean_relative_media_path(value: Any) -> str:
    """Return a safe portable album-relative media path."""

    normalized = str(value or "").replace("\\", "/").strip()
    parts = PurePosixPath(normalized).parts
    has_drive = len(normalized) >= 2 and normalized[1] == ":"
    has_hidden_part = any(part.startswith(".") for part in parts)
    if (
        not normalized
        or len(normalized) > MAX_MEDIA_PATH_LENGTH
        or normalized == "."
        or normalized.startswith("/")
        or has_drive
        or ".." in parts
        or has_hidden_part
    ):
        raise AppError("Selected media path is invalid.", "MEDIA_ITEM_PATH_INVALID")
    return PurePosixPath(normalized).as_posix()


# Resolves a selected item and rejects symlinks at every component inside its saved album.
def selected_media_path(store: MediaLibraryStore, album_id: Any, relative_value: Any) -> tuple[dict[str, str], Path]:
    """Return the saved album and one contained regular media file."""

    album = store.require_album(album_id)
    root = album_directory(album["path"])
    relative_path = clean_relative_media_path(relative_value)
    current = root
    # Component checks prevent an album subfolder symlink from redirecting previews or native opening.
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if current.is_symlink():
            raise AppError("Media items cannot pass through symbolic links.", "MEDIA_ITEM_PATH_INVALID")
    try:
        path = current.resolve()
        path.relative_to(root)
    except (OSError, ValueError) as error:
        raise AppError("Selected media path is invalid.", "MEDIA_ITEM_PATH_INVALID") from error
    if not path.is_file() or not media_kind(path):
        raise AppError("Selected media file is unavailable.", "MEDIA_ITEM_NOT_FOUND")
    return album, path


# Encodes one pixel-bounded image or video thumbnail only while its tile or inspector is active.
def media_preview(
    album_id: Any,
    relative_value: Any,
    store: MediaLibraryStore | None = None,
) -> dict[str, Any]:
    """Return a bounded self-contained preview without exposing a filesystem URL."""

    media_store = store or MediaLibraryStore()
    unused_album, path = selected_media_path(media_store, album_id, relative_value)
    try:
        stat = path.stat()
    except OSError as error:
        raise AppError("Selected media file is unavailable.", "MEDIA_ITEM_NOT_FOUND") from error
    kind = media_kind(path)
    if not kind or stat.st_size > MAX_MEDIA_PREVIEW_SOURCE_BYTES:
        return {"path": clean_relative_media_path(relative_value), "data_url": "", "preview_available": False}
    try:
        thumbnail = create_media_thumbnail(path, kind)
    except OSError as error:
        raise AppError("Selected image could not be read.", "MEDIA_PREVIEW_READ_FAILED") from error
    if not thumbnail:
        return {"path": clean_relative_media_path(relative_value), "data_url": "", "preview_available": False}
    encoded = base64.b64encode(thumbnail["content"]).decode("ascii")
    return {
        "path": clean_relative_media_path(relative_value),
        "data_url": f"data:{thumbnail['mime_type']};base64,{encoded}",
        "preview_available": True,
        "modified": stat.st_mtime,
        "width": thumbnail["width"],
        "height": thumbnail["height"],
    }


# Opens the album root in the native file manager after resolving the saved record.
def open_album(album_id: Any, store: MediaLibraryStore | None = None) -> dict[str, str]:
    """Open one saved album folder."""

    album = (store or MediaLibraryStore()).require_album(album_id)
    return open_folder(album["path"])


# Opens one selected image or video through the operating system's default application.
def open_media(
    album_id: Any,
    relative_value: Any,
    store: MediaLibraryStore | None = None,
) -> dict[str, str]:
    """Open one contained media file in its native application."""

    media_store = store or MediaLibraryStore()
    unused_album, path = selected_media_path(media_store, album_id, relative_value)
    return open_path(str(path))
