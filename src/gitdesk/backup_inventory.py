"""Registered Local, Repo, Media, and non-secret settings inventory for Backup Mode."""

from __future__ import annotations

# Hashing and portable-name helpers create stable collision-safe snapshot targets.
import hashlib
from pathlib import Path
import re
from typing import Any

# Existing stores remain authoritative for every root Backup Mode is allowed to read.
from gitdesk.localproject_records import clean_local_project_list
from gitdesk.managedrepos import clean_repository_map
from gitdesk.media_library_store import MediaLibraryStore
from gitdesk.storage import app_config_path


# Folder names intentionally match the human-readable layout requested for every dated snapshot.
LOCAL_BACKUP_FOLDER = "local mode backups"
REPO_BACKUP_FOLDER = "repo mode backups"
MEDIA_BACKUP_FOLDER = "media mode backup"
SETTINGS_BACKUP_FOLDER = "user settings and other setting backups"

# Backup Mode copies app-owned non-secret JSON only; legacy token vault files are deliberately absent.
SAFE_METADATA_FILE_NAMES = (
    "settings.json",
    "reposettings.json",
    "media-library.json",
    "documents.json",
    "shared-resources.json",
    "sync-ignore.json",
)

# Portable target segments avoid operating-system-reserved path punctuation.
UNSAFE_TARGET_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


# Produces a readable stable target name and adds a path hash to prevent label collisions.
def backup_target(label_value: Any, path_value: Any) -> str:
    """Return a portable collision-safe snapshot target folder or filename."""

    label = UNSAFE_TARGET_CHARACTERS.sub("-", str(label_value or "").strip()).strip(" .-")
    label = re.sub(r"\s+", " ", label)[:80] or "unnamed"
    path_digest = hashlib.sha256(str(path_value or "").encode("utf-8")).hexdigest()[:10]
    return f"{label} -- {path_digest}"


# Creates one normalized directory source record without touching the filesystem.
def directory_source(category: str, path_value: Any, label_value: Any) -> dict[str, str]:
    """Return one stable directory-source record for a registered root."""

    path = str(path_value or "").strip()
    target = backup_target(label_value or Path(path).name, path)
    source_id = hashlib.sha256(f"{category}\0{path}".encode("utf-8")).hexdigest()
    return {
        "id": source_id,
        "category": category,
        "kind": "directory",
        "path": path,
        "label": str(label_value or Path(path).name),
        "target": target,
        "snapshot_path": f"{category}/{target}",
    }


# Creates one normalized metadata-file record whose snapshot name stays recognizable.
def metadata_source(path: Path) -> dict[str, str]:
    """Return one stable file-source record for an allowlisted metadata JSON file."""

    source_id = hashlib.sha256(f"{SETTINGS_BACKUP_FOLDER}\0{path}".encode("utf-8")).hexdigest()
    return {
        "id": source_id,
        "category": SETTINGS_BACKUP_FOLDER,
        "kind": "file",
        "path": str(path),
        "label": path.name,
        "target": path.name,
        "snapshot_path": f"{SETTINGS_BACKUP_FOLDER}/{path.name}",
    }


# De-duplicates directory records within one mode while retaining first-seen human labels.
def unique_directories(records: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return directory records de-duplicated by resolved-or-lexical path."""

    unique = []
    seen = set()
    for record in records:
        raw_path = record["path"]
        try:
            key = str(Path(raw_path).expanduser().resolve()).casefold()
        except OSError:
            key = raw_path.casefold()
        if not raw_path or key in seen:
            continue
        unique.append(record)
        seen.add(key)
    return unique


# Builds the complete source inventory from private registries without activating any workspace.
def backup_sources(settings: dict[str, Any]) -> list[dict[str, str]]:
    """Return every registered backup source grouped by user-requested mode folders."""

    local_sources = [
        directory_source(LOCAL_BACKUP_FOLDER, project["path"], project["name"])
        for project in clean_local_project_list(settings.get("local_projects"))
    ]
    repository_sources = []
    repositories = clean_repository_map(settings.get("managed_repositories"))
    # Every account bucket can own distinct checkouts, while duplicate paths are removed after collection.
    for records in repositories.values():
        repository_sources.extend(
            directory_source(REPO_BACKUP_FOLDER, record["path"], record["full_name"])
            for record in records
        )
    media_sources = [
        directory_source(MEDIA_BACKUP_FOLDER, album["path"], album["name"])
        for album in MediaLibraryStore().load()["albums"]
    ]
    metadata_sources = [
        metadata_source(app_config_path() / name)
        for name in SAFE_METADATA_FILE_NAMES
        if (app_config_path() / name).is_file()
    ]
    return [
        *unique_directories(local_sources),
        *unique_directories(repository_sources),
        *unique_directories(media_sources),
        *metadata_sources,
    ]


# Summarizes inventory counts without reading any registered content tree.
def inventory_summary(sources: list[dict[str, str]]) -> dict[str, int]:
    """Return per-group source counts for Backup Mode overview rendering."""

    return {
        "local": sum(source["category"] == LOCAL_BACKUP_FOLDER for source in sources),
        "repo": sum(source["category"] == REPO_BACKUP_FOLDER for source in sources),
        "media": sum(source["category"] == MEDIA_BACKUP_FOLDER for source in sources),
        "settings": sum(source["category"] == SETTINGS_BACKUP_FOLDER for source in sources),
    }
