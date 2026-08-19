"""Owner-only album registry for GitDesk Media Mode."""

from __future__ import annotations

# Standard-library helpers validate identifiers, preserve malformed metadata, and type album records.
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

# GitDesk storage helpers provide recoverable owner-only atomic writes.
from gitdesk.categorynames import clean_category_name
from gitdesk.errors import AppError
from gitdesk.reposettings_recovery import invalid_json_backup_path, load_recoverable_json, mark_backup_recovered
from gitdesk.sharedresource_store import clean_resource_name
from gitdesk.storage import APP_STORAGE_LOCK, app_config_path, atomic_write_private_bytes, atomic_write_private_json


# The schema version keeps parent-favorite and future album-record migrations explicit.
MEDIA_LIBRARY_SCHEMA_VERSION = 3

# Album identifiers are random lowercase UUID hex values generated only by this store.
ALBUM_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")

# Album labels stay compact in the rail while allowing normal punctuation and Unicode names.
MAX_ALBUM_NAME_LENGTH = 80

# Parent favorites match Local Mode's compact picker behavior while remaining Media-specific metadata.
MAX_PARENT_FAVORITES = 12

# Media registry paths are private local metadata and therefore use owner-only permissions.
MEDIA_LIBRARY_DIRECTORY_MODE = 0o700
MEDIA_LIBRARY_FILE_MODE = 0o600


# Validates a user-facing album label without turning it into a filesystem path.
def album_name(value: Any) -> str:
    """Return a bounded album label or raise a structured validation error."""

    name = str(value or "").strip()
    if not name:
        raise AppError("Album name is required.", "MEDIA_ALBUM_NAME_EMPTY")
    if len(name) > MAX_ALBUM_NAME_LENGTH or any(ord(character) < 32 for character in name):
        raise AppError("Album name contains unsupported characters.", "MEDIA_ALBUM_NAME_INVALID")
    return name


# Sanitizes one persisted album record without requiring removable drives to be connected.
def clean_album(value: Any) -> dict[str, str] | None:
    """Return one safe album record, or None when required identity is malformed."""

    if not isinstance(value, dict):
        return None
    identifier = str(value.get("id") or "").strip().lower()
    path = str(value.get("path") or "").strip()
    try:
        name = album_name(value.get("name"))
    except AppError:
        return None
    try:
        category = clean_category_name(value.get("category"))
    except AppError:
        category = ""
    if not ALBUM_ID_PATTERN.fullmatch(identifier) or not path:
        return None
    resource_name = clean_resource_name(value.get("resource_name"))
    return {
        "id": identifier,
        "name": name,
        "path": path,
        "category": category,
        "resource_name": resource_name,
    }


# Removes malformed and duplicate records while preserving the first stable album and path identity.
def clean_albums(value: Any) -> list[dict[str, str]]:
    """Return de-duplicated persisted albums in their saved order."""

    if not isinstance(value, list):
        return []
    albums = []
    seen_ids = set()
    seen_paths = set()
    # A duplicated identifier or folder path cannot represent two independent album owners.
    for raw_album in value:
        album = clean_album(raw_album)
        path_key = album["path"].casefold() if album else ""
        if not album or album["id"] in seen_ids or path_key in seen_paths:
            continue
        albums.append(album)
        seen_ids.add(album["id"])
        seen_paths.add(path_key)
    return albums


# Keeps saved parent paths usable across disconnected drives without touching the filesystem during registry loading.
def clean_parent_favorites(value: Any) -> list[str]:
    """Return bounded de-duplicated Media parent paths in saved order."""

    if not isinstance(value, list):
        return []
    favorites = []
    seen = set()
    for raw_path in value:
        path = str(raw_path or "").strip()
        key = path.casefold()
        if not path or len(path) > 4096 or any(ord(character) < 32 for character in path) or key in seen:
            continue
        favorites.append(path)
        seen.add(key)
        if len(favorites) >= MAX_PARENT_FAVORITES:
            break
    return favorites


# Produces the complete registry shape and chooses a valid active album when possible.
def clean_registry(value: Any) -> dict[str, Any]:
    """Return the complete sanitized Media Mode registry."""

    raw = value if isinstance(value, dict) else {}
    albums = clean_albums(raw.get("albums"))
    valid_ids = {album["id"] for album in albums}
    active_album_id = str(raw.get("active_album_id") or "").strip().lower()
    if active_album_id not in valid_ids:
        active_album_id = albums[0]["id"] if albums else ""
    return {
        "schema_version": MEDIA_LIBRARY_SCHEMA_VERSION,
        "active_album_id": active_album_id,
        "albums": albums,
        "parent_favorites": clean_parent_favorites(raw.get("parent_favorites")),
    }


# Resolves a selected folder and rejects symbolic-link album roots before registration.
def album_directory(path_value: Any) -> Path:
    """Return an existing non-symlink album directory."""

    raw_path = str(path_value or "").strip()
    candidate = Path(raw_path).expanduser() if raw_path else Path()
    if not raw_path or candidate.is_symlink():
        raise AppError("Album folder is invalid.", "MEDIA_ALBUM_PATH_INVALID")
    try:
        path = candidate.resolve()
    except OSError as error:
        raise AppError("Album folder is unavailable.", "MEDIA_ALBUM_PATH_INVALID") from error
    if not path.is_dir():
        raise AppError("Album folder must be an existing directory.", "MEDIA_ALBUM_PATH_INVALID")
    return path


# Resolves a parent chosen for album creation without allowing a symbolic-link root.
def parent_directory(path_value: Any) -> Path:
    """Return an existing non-symlink Media album parent directory."""

    try:
        return album_directory(path_value)
    except AppError as error:
        raise AppError("Choose an existing album parent folder.", "MEDIA_PARENT_PATH_INVALID") from error


# MediaLibraryStore owns album references independently from repository and Local Mode settings.
class MediaLibraryStore:
    """Persist Media Mode album references without copying or deleting user media."""

    # Allows focused tests to supply an isolated registry path.
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or app_config_path() / "media-library.json"

    # Returns an empty versioned registry without creating a file.
    def defaults(self) -> dict[str, Any]:
        """Return the safe empty Media Mode registry."""

        return clean_registry({})

    # Preserves malformed bytes before replacement so private album references remain recoverable.
    def preserve_invalid_json(self) -> Path:
        """Return the backup path containing the unreadable registry bytes."""

        backup_path = invalid_json_backup_path(self.config_path)
        try:
            atomic_write_private_bytes(
                backup_path,
                self.config_path.read_bytes(),
                MEDIA_LIBRARY_DIRECTORY_MODE,
                MEDIA_LIBRARY_FILE_MODE,
            )
        except OSError as error:
            raise AppError(
                "Media library metadata is invalid and could not be preserved.",
                "MEDIA_LIBRARY_SETTINGS_INVALID_JSON",
            ) from error
        return backup_path

    # Loads and sanitizes the private registry, recovering complete JSON from a malformed backup when possible.
    def load(self) -> dict[str, Any]:
        """Return the current Media Mode registry."""

        with APP_STORAGE_LOCK:
            if not self.config_path.exists():
                return self.defaults()
            try:
                with self.config_path.open("r", encoding="utf-8") as registry_file:
                    raw_registry = json.load(registry_file)
            except OSError as error:
                raise AppError("Unable to read Media library metadata.", "MEDIA_LIBRARY_READ_FAILED") from error
            except json.JSONDecodeError:
                backup_path = self.preserve_invalid_json()
                registry = clean_registry(load_recoverable_json(backup_path))
                self.write(registry)
                mark_backup_recovered(backup_path)
                return registry
            registry = clean_registry(raw_registry)
            if raw_registry != registry:
                self.write(registry)
            return registry

    # Writes only the sanitized registry with owner-only permissions.
    def write(self, registry: dict[str, Any]) -> None:
        """Persist complete Media Mode metadata atomically."""

        try:
            atomic_write_private_json(
                self.config_path,
                clean_registry(registry),
                MEDIA_LIBRARY_DIRECTORY_MODE,
                MEDIA_LIBRARY_FILE_MODE,
            )
        except OSError as error:
            raise AppError("Unable to save Media library metadata.", "MEDIA_LIBRARY_WRITE_FAILED") from error

    # Returns one album by stable identifier or raises when the frontend selection is stale.
    def require_album(self, album_id: Any) -> dict[str, str]:
        """Return the requested saved album."""

        identifier = str(album_id or "").strip().lower()
        album = next((item for item in self.load()["albums"] if item["id"] == identifier), None)
        if not album:
            raise AppError("Select a saved Media album first.", "MEDIA_ALBUM_NOT_FOUND")
        return album

    # Registers one existing folder without changing anything inside it.
    def add_album(self, path_value: Any, name_value: Any = "", category_value: Any = "") -> dict[str, Any]:
        """Save a folder-backed album and make it active."""

        path = album_directory(path_value)
        name = album_name(name_value or path.name)
        category = clean_category_name(category_value)
        with APP_STORAGE_LOCK:
            registry = self.load()
            if any(Path(item["path"]).expanduser() == path for item in registry["albums"]):
                raise AppError("That folder is already registered as an album.", "MEDIA_ALBUM_DUPLICATE")
            album = {
                "id": uuid4().hex,
                "name": name,
                "path": str(path),
                "category": category,
                "resource_name": "",
            }
            registry["albums"].append(album)
            registry["active_album_id"] = album["id"]
            self.write(registry)
            return registry

    # Changes the active album without rescanning or mutating any folder.
    def select_album(self, album_id: Any) -> dict[str, Any]:
        """Persist the selected album identifier."""

        album = self.require_album(album_id)
        with APP_STORAGE_LOCK:
            registry = self.load()
            registry["active_album_id"] = album["id"]
            self.write(registry)
            return registry

    # Updates display metadata only so physical album and resource paths remain stable.
    def rename_album(self, album_id: Any, name_value: Any, category_value: Any | None = None) -> dict[str, Any]:
        """Update a saved album label and optional category without renaming its folder."""

        album = self.require_album(album_id)
        name = album_name(name_value)
        category = album.get("category", "") if category_value is None else clean_category_name(category_value)
        with APP_STORAGE_LOCK:
            registry = self.load()
            registry["albums"] = [
                {**item, "name": name, "category": category} if item["id"] == album["id"] else item
                for item in registry["albums"]
            ]
            self.write(registry)
            return registry

    # Removes only the private registry record and deliberately leaves the album folder and resource untouched.
    def remove_album(self, album_id: Any) -> dict[str, Any]:
        """Forget one album without deleting any user files."""

        album = self.require_album(album_id)
        with APP_STORAGE_LOCK:
            registry = self.load()
            registry["albums"] = [item for item in registry["albums"] if item["id"] != album["id"]]
            if registry["active_album_id"] == album["id"]:
                registry["active_album_id"] = registry["albums"][0]["id"] if registry["albums"] else ""
            self.write(registry)
            return registry

    # Moves a verified parent to the front of the Media-specific favorites without affecting Local settings.
    def save_parent_favorite(self, path_value: Any) -> dict[str, Any]:
        """Persist one available Media album parent as the newest favorite."""

        path = str(parent_directory(path_value))
        with APP_STORAGE_LOCK:
            registry = self.load()
            favorites = [item for item in registry["parent_favorites"] if item.casefold() != path.casefold()]
            registry["parent_favorites"] = [path, *favorites][:MAX_PARENT_FAVORITES]
            self.write(registry)
            return registry

    # Links one album to its dedicated Shared Resource after publication succeeds.
    def set_resource(self, album_id: Any, resource_name: Any) -> dict[str, Any]:
        """Persist the Shared Resource owned by one album."""

        album = self.require_album(album_id)
        resource = clean_resource_name(resource_name)
        if not resource:
            raise AppError("Shared Resource name is invalid.", "MEDIA_RESOURCE_NAME_INVALID")
        with APP_STORAGE_LOCK:
            registry = self.load()
            registry["albums"] = [
                {**item, "resource_name": resource} if item["id"] == album["id"] else item
                for item in registry["albums"]
            ]
            self.write(registry)
            return registry
