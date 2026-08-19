"""Import clipboard images and copy contained Media originals through the desktop clipboard."""

from __future__ import annotations

# Standard-library helpers generate safe names and encode raw clipboard pixels without browser clipboard access.
from datetime import datetime
from io import BytesIO
from pathlib import Path
import sys
from typing import Any, Callable

from gitdesk.desktop_clipboard import read_macos_clipboard_file_urls, write_desktop_clipboard_files
from gitdesk.errors import AppError
from gitdesk.media_album_files import import_media_content, import_media_file
from gitdesk.media_library import media_kind, selected_media_path
from gitdesk.media_library_store import MediaLibraryStore


# Raw clipboard images share the same decompressed-pixel ceiling as Media thumbnail generation.
MAX_CLIPBOARD_PIXELS = 16_000_000

# Clipboard readers return copied file paths first and an optional raw image only when no file list exists.
ClipboardPayload = tuple[list[str], Any | None]
ClipboardReader = Callable[[], ClipboardPayload]


# Reads Finder file URLs through the OS clipboard service instead of WKWebView ClipboardEvent delivery.
def macos_clipboard_files() -> list[str]:
    """Return regular file paths currently copied through the macOS general pasteboard."""

    return read_macos_clipboard_file_urls()


# Reads copied files before raw image pixels so Finder filenames and multi-selection remain intact.
def read_desktop_clipboard() -> ClipboardPayload:
    """Return copied desktop file paths or one raw clipboard image."""

    if sys.platform == "darwin":
        file_paths = macos_clipboard_files()
        if file_paths:
            return file_paths, None
    try:
        # The runtime import keeps an outdated source environment from aborting unrelated app startup.
        from PIL import Image, ImageGrab
    except ImportError as error:
        raise AppError(
            "Raw image clipboard support is not installed.",
            "MEDIA_CLIPBOARD_DEPENDENCY_MISSING",
        ) from error
    try:
        value = ImageGrab.grabclipboard()
    except (ChildProcessError, NotImplementedError, OSError) as error:
        raise AppError("The desktop clipboard could not be read.", "MEDIA_CLIPBOARD_READ_FAILED") from error
    if isinstance(value, list):
        return [str(path) for path in value], None
    if isinstance(value, Image.Image):
        return [], value
    return [], None


# Encodes clipboard pixels as PNG after checking dimensions before allocating an album import payload.
def raw_clipboard_png(image: Any) -> bytes:
    """Return bounded PNG bytes for a raw clipboard image."""

    width, height = image.size
    if width <= 0 or height <= 0 or width * height > MAX_CLIPBOARD_PIXELS:
        raise AppError(
            "The copied image is too large to paste safely.",
            "MEDIA_CLIPBOARD_IMAGE_DIMENSIONS",
        )
    try:
        buffer = BytesIO()
        converted = image.convert("RGBA")
        try:
            converted.save(buffer, format="PNG", optimize=True)
        finally:
            converted.close()
        return buffer.getvalue()
    except (OSError, ValueError) as error:
        raise AppError("The copied image could not be decoded.", "MEDIA_CLIPBOARD_IMAGE_INVALID") from error


# Imports every copied file independently while preserving successful images from mixed selections.
def import_clipboard_files(
    album_id: Any,
    paths: list[str],
    store: MediaLibraryStore,
) -> dict[str, Any]:
    """Import copied files and return a safe per-batch summary."""

    imported = []
    failed = []
    for source_value in paths:
        source_name = Path(str(source_value or "")).name or "Copied item"
        try:
            imported.append(import_media_file(album_id, source_value, store))
        except AppError as error:
            failed.append({"name": source_name, "code": error.code})
    if not imported:
        raise AppError(
            "The clipboard does not contain a supported image file.",
            "MEDIA_CLIPBOARD_NO_SUPPORTED_IMAGE",
            {"failed_count": len(failed)},
        )
    return {"imported": imported, "failed": failed}


# Reads the OS clipboard once and imports copied files or raw pixels through the same album validation boundary.
def paste_media_clipboard(
    album_id: Any,
    store: MediaLibraryStore | None = None,
    reader: ClipboardReader = read_desktop_clipboard,
) -> dict[str, Any]:
    """Paste copied desktop images into one registered Media album."""

    media_store = store or MediaLibraryStore()
    media_store.require_album(album_id)
    paths, image = reader()
    if paths:
        return import_clipboard_files(album_id, paths, media_store)
    if image is None:
        raise AppError(
            "The clipboard does not contain a supported image file.",
            "MEDIA_CLIPBOARD_EMPTY",
        )
    try:
        content = raw_clipboard_png(image)
    finally:
        image.close()
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H%M%S")
    imported = import_media_content(
        album_id,
        f"Clipboard image {timestamp}.png",
        content,
        media_store,
    )
    return {"imported": [imported], "failed": []}


# Resolves the selected original inside its registered album before replacing the desktop file clipboard.
def copy_media_item(
    album_id: Any,
    relative_value: Any,
    store: MediaLibraryStore | None = None,
) -> dict[str, str]:
    """Copy one contained image or video original to the operating-system clipboard."""

    media_store = store or MediaLibraryStore()
    unused_album, path = selected_media_path(media_store, album_id, relative_value)
    write_desktop_clipboard_files([str(path)])
    return {"name": path.name, "kind": media_kind(path)}
