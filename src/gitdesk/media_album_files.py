"""Create Media albums and import user-supplied images without overwriting existing files."""

from __future__ import annotations

# Standard-library helpers decode bounded bridge payloads and create direct-child files exclusively.
import base64
import binascii
import os
from pathlib import Path
import re
import stat
from typing import Any

# Existing Media and artwork boundaries keep folder registration and image verification consistent.
from gitdesk.errors import AppError
from gitdesk.localproject_icons import validate_raster_bytes, validate_svg_bytes
from gitdesk.media_library_store import MediaLibraryStore, album_directory, parent_directory


# Browser-originated image imports stay bounded before base64 decoding and filesystem writes.
MAX_MEDIA_IMPORT_BYTES = 32 * 1024 * 1024

# Folder and file names are portable across GitDesk's supported desktop operating systems.
MAX_ALBUM_FOLDER_NAME_LENGTH = 80
MAX_IMPORT_FILE_NAME_LENGTH = 180
INVALID_PORTABLE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}

# Imports are limited to formats whose content can be verified without adding an image-decoding dependency.
IMPORT_IMAGE_MIME_TYPES = {
    ".bmp": {"image/bmp"},
    ".gif": {"image/gif"},
    ".ico": {"image/x-icon", "image/vnd.microsoft.icon"},
    ".jpeg": {"image/jpeg"},
    ".jpg": {"image/jpeg"},
    ".png": {"image/png"},
    ".svg": {"image/svg+xml"},
    ".webp": {"image/webp"},
}


# Applies one portable leaf-name policy to album folders and imported filenames.
def portable_leaf_name(value: Any, maximum_length: int, empty_code: str, invalid_code: str) -> str:
    """Return a safe direct-child name or raise a structured Media validation error."""

    name = str(value or "").strip()
    stem = Path(name).stem.casefold()
    if not name:
        raise AppError("A name is required.", empty_code)
    if (
        len(name) > maximum_length
        or name in {".", ".."}
        or name.startswith(".")
        or name.endswith((".", " "))
        or INVALID_PORTABLE_NAME.search(name)
        or stem in WINDOWS_RESERVED_NAMES
    ):
        raise AppError("The name is not valid on supported filesystems.", invalid_code)
    return name


# Validates the user-facing album name before it can become a physical child folder.
def album_folder_name(value: Any) -> str:
    """Return a portable direct-child album folder name."""

    return portable_leaf_name(
        value,
        MAX_ALBUM_FOLDER_NAME_LENGTH,
        "MEDIA_ALBUM_NAME_EMPTY",
        "MEDIA_ALBUM_FOLDER_NAME_INVALID",
    )


# Creates one empty album beneath the chosen parent, then registers it as the active Media album.
def create_media_album(
    parent_value: Any,
    name_value: Any,
    store: MediaLibraryStore | None = None,
    category_value: Any = "",
) -> dict[str, Any]:
    """Create and register one direct-child Media album folder."""

    media_store = store or MediaLibraryStore()
    parent = parent_directory(parent_value)
    name = album_folder_name(name_value)
    target = parent / name
    if target.exists() or target.is_symlink():
        raise AppError("An item with that album name already exists in the parent.", "MEDIA_ALBUM_FOLDER_EXISTS")
    try:
        target.mkdir()
    except FileExistsError as error:
        raise AppError(
            "An item with that album name already exists in the parent.",
            "MEDIA_ALBUM_FOLDER_EXISTS",
        ) from error
    except OSError as error:
        raise AppError("Unable to create the album folder.", "MEDIA_ALBUM_CREATE_FAILED") from error
    try:
        return media_store.add_album(str(target), name, category_value)
    except Exception:
        # Roll back only the empty folder this action created; pre-existing user content is never targeted.
        try:
            target.rmdir()
        except OSError:
            pass
        raise


# Validates a browser-provided filename and requires a content-verifiable image extension.
def import_image_name(value: Any) -> str:
    """Return a safe direct-child imported image filename."""

    name = portable_leaf_name(
        value,
        MAX_IMPORT_FILE_NAME_LENGTH,
        "MEDIA_IMPORT_NAME_EMPTY",
        "MEDIA_IMPORT_NAME_INVALID",
    )
    if Path(name).suffix.lower() not in IMPORT_IMAGE_MIME_TYPES:
        raise AppError(
            "Import a PNG, JPEG, GIF, WebP, BMP, ICO, or safe SVG image.",
            "MEDIA_IMPORT_TYPE_INVALID",
        )
    return name


# Decodes one data URL after checking its declared MIME type and encoded-size upper bound.
def decoded_image_data(data_url_value: Any, suffix: str) -> bytes:
    """Return bounded decoded image bytes whose MIME type matches the filename."""

    data_url = str(data_url_value or "")
    header, separator, encoded = data_url.partition(",")
    expected_types = IMPORT_IMAGE_MIME_TYPES[suffix]
    declared_type = header[5:].split(";", 1)[0].strip().lower() if header.startswith("data:") else ""
    maximum_encoded_length = ((MAX_MEDIA_IMPORT_BYTES + 2) // 3) * 4
    if (
        not separator
        or not header.lower().endswith(";base64")
        or declared_type not in expected_types
        or len(encoded) > maximum_encoded_length
    ):
        raise AppError("The imported image payload is invalid or too large.", "MEDIA_IMPORT_DATA_INVALID")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise AppError("The imported image payload is invalid.", "MEDIA_IMPORT_DATA_INVALID") from error
    if not content:
        raise AppError("The imported image is empty.", "MEDIA_IMPORT_DATA_INVALID")
    if len(content) > MAX_MEDIA_IMPORT_BYTES:
        raise AppError("Imported images must be 32 MB or smaller.", "MEDIA_IMPORT_TOO_LARGE")
    return content


# Confirms bytes match the requested raster format or contain only passive self-contained SVG artwork.
def validate_import_content(name: str, content: bytes) -> None:
    """Raise when imported bytes do not match their image filename."""

    path = Path(name)
    if path.suffix.lower() == ".svg":
        validate_svg_bytes(content)
    else:
        validate_raster_bytes(path, content)


# Reads one copied desktop file without following a final symbolic link or allocating past the import limit.
def copied_image_content(source_value: Any) -> tuple[str, bytes]:
    """Return a copied file's safe leaf name and bounded bytes."""

    source = Path(str(source_value or "")).expanduser()
    name = import_image_name(source.name)
    if source.is_symlink():
        raise AppError("Copied image links cannot be imported.", "MEDIA_IMPORT_SOURCE_SYMLINK")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    try:
        descriptor = os.open(source, flags)
        source_stat = os.fstat(descriptor)
        if not stat.S_ISREG(source_stat.st_mode):
            raise AppError("The copied image is not a regular file.", "MEDIA_IMPORT_SOURCE_INVALID")
        if source_stat.st_size <= 0 or source_stat.st_size > MAX_MEDIA_IMPORT_BYTES:
            raise AppError("Copied images must be between 1 byte and 32 MB.", "MEDIA_IMPORT_TOO_LARGE")
        with os.fdopen(descriptor, "rb") as source_file:
            descriptor = -1
            content = source_file.read(MAX_MEDIA_IMPORT_BYTES + 1)
    except AppError:
        raise
    except OSError as error:
        raise AppError("The copied image could not be read.", "MEDIA_IMPORT_SOURCE_READ_FAILED") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not content or len(content) > MAX_MEDIA_IMPORT_BYTES:
        raise AppError("Copied images must be between 1 byte and 32 MB.", "MEDIA_IMPORT_TOO_LARGE")
    return name, content


# Tries the original name first and then numbered variants until an exclusive create succeeds.
def write_collision_safe_image(root: Path, name: str, content: bytes) -> Path:
    """Write one image as a new direct child without replacing any existing path."""

    source = Path(name)
    for sequence in range(1, 10001):
        candidate_name = name if sequence == 1 else f"{source.stem} ({sequence}){source.suffix}"
        target = root / candidate_name
        opened = False
        try:
            with target.open("xb") as image_file:
                opened = True
                image_file.write(content)
                image_file.flush()
                os.fsync(image_file.fileno())
            return target
        except FileExistsError:
            continue
        except OSError as error:
            if opened:
                try:
                    target.unlink()
                except OSError:
                    pass
            raise AppError("Unable to save the imported image.", "MEDIA_IMPORT_WRITE_FAILED") from error
    raise AppError("Too many files use that image name.", "MEDIA_IMPORT_NAME_EXHAUSTED")


# Imports one validated image into the currently addressed album and returns its stored identity.
def import_media_content(
    album_id: Any,
    name_value: Any,
    content: bytes,
    store: MediaLibraryStore | None = None,
) -> dict[str, Any]:
    """Save verified image bytes as a collision-safe direct child of a registered album."""

    media_store = store or MediaLibraryStore()
    album = media_store.require_album(album_id)
    root = album_directory(album["path"])
    name = import_image_name(name_value)
    if not content or len(content) > MAX_MEDIA_IMPORT_BYTES:
        raise AppError("Imported images must be between 1 byte and 32 MB.", "MEDIA_IMPORT_TOO_LARGE")
    try:
        validate_import_content(name, content)
    except AppError as error:
        raise AppError("The imported image content is invalid.", "MEDIA_IMPORT_CONTENT_INVALID") from error
    target = write_collision_safe_image(root, name, content)
    return {
        "album_id": album["id"],
        "name": target.name,
        "path": target.name,
        "size": len(content),
    }


# Imports one browser data URL after its declared type and base64 encoding pass the existing boundary.
def import_media_image(
    album_id: Any,
    name_value: Any,
    data_url_value: Any,
    store: MediaLibraryStore | None = None,
) -> dict[str, Any]:
    """Save one browser-provided image into a registered album."""

    name = import_image_name(name_value)
    content = decoded_image_data(data_url_value, Path(name).suffix.lower())
    return import_media_content(album_id, name, content, store)


# Imports a copied desktop file without sending its bytes or filesystem path through the WebView.
def import_media_file(
    album_id: Any,
    source_value: Any,
    store: MediaLibraryStore | None = None,
) -> dict[str, Any]:
    """Save one copied image file into a registered album."""

    name, content = copied_image_content(source_value)
    return import_media_content(album_id, name, content, store)
