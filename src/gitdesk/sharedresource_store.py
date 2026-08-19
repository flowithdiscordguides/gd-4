"""Owner-only persistence for Shared Resources installations and Document Builder links."""

from __future__ import annotations

# Standard-library imports parse, sanitize, and type private registry data.
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

# GitDesk storage helpers provide structured recovery and owner-only atomic writes.
from gitdesk.errors import AppError
from gitdesk.reposettings_recovery import invalid_json_backup_path, load_recoverable_json, mark_backup_recovered
from gitdesk.storage import APP_STORAGE_LOCK, app_config_path, atomic_write_private_bytes, atomic_write_private_json


# The schema version makes future manifest migrations explicit instead of relying on partial record shapes.
SHARED_RESOURCE_SCHEMA_VERSION = 2

# Resource metadata contains private local paths and therefore uses owner-only directory and file permissions.
SHARED_RESOURCE_DIRECTORY_MODE = 0o700
SHARED_RESOURCE_FILE_MODE = 0o600

# File and revision digests are lowercase SHA-256 values produced only by the resource catalog.
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# Persisted resource keys follow the same portable directory-name contract as the editable catalog.
RESOURCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,63}$")


# Accepts only catalog-produced digest strings before persisted manifests are trusted by removal or comparison logic.
def clean_digest(value: Any) -> str:
    """Return a valid SHA-256 digest string, or an empty string for malformed metadata."""

    digest = str(value or "").strip().lower()
    return digest if DIGEST_PATTERN.fullmatch(digest) else ""


# Prevents malformed metadata keys from becoming filesystem folder names during later install operations.
def clean_resource_name(value: Any) -> str:
    """Return a valid portable resource name, or an empty string for malformed metadata."""

    name = str(value or "").strip()
    return name if RESOURCE_NAME_PATTERN.fullmatch(name) else ""


# Keeps persisted ownership paths relative and prevents malformed metadata from addressing repository internals.
def clean_relative_metadata_path(value: Any) -> str:
    """Return a safe relative manifest path, or an empty string for malformed metadata."""

    normalized = str(value or "").replace("\\", "/").strip()
    parts = PurePosixPath(normalized).parts
    has_drive = len(normalized) >= 2 and normalized[1] == ":"
    if not normalized or normalized == "." or normalized.startswith("/") or has_drive:
        return ""
    if ".." in parts or ".git" in parts:
        return ""
    return PurePosixPath(normalized).as_posix()


# Normalizes one resource installation while retaining only safe path-to-digest ownership information.
def clean_installation(value: Any) -> dict[str, Any] | None:
    """Return one sanitized installation record, or None when it has no usable resource identity."""

    if not isinstance(value, dict):
        return None
    resource = clean_resource_name(value.get("resource"))
    version = value.get("version") if isinstance(value.get("version"), int) else 0
    version = version if version > 0 else 0
    revision = clean_digest(value.get("revision"))
    raw_files = value.get("files") if isinstance(value.get("files"), dict) else {}
    files = {}
    # Only safe relative paths with catalog-produced hashes can remain resource-owned.
    for raw_path, raw_digest in raw_files.items():
        relative_path = clean_relative_metadata_path(raw_path)
        digest = clean_digest(raw_digest)
        if relative_path and digest:
            files[relative_path] = digest
    if not resource:
        return None
    return {"resource": resource, "version": version, "revision": revision, "files": files}


# Normalizes the latest explicitly recorded release for one editable resource working folder.
def clean_catalog_record(value: Any) -> dict[str, Any] | None:
    """Return one sanitized catalog release, or None when required release identity is invalid."""

    if not isinstance(value, dict):
        return None
    version = value.get("version") if isinstance(value.get("version"), int) else 0
    revision = clean_digest(value.get("revision"))
    raw_files = value.get("files") if isinstance(value.get("files"), dict) else {}
    files = {}
    # Release files use the same path and digest boundary as installation ownership manifests.
    for raw_path, raw_digest in raw_files.items():
        relative_path = clean_relative_metadata_path(raw_path)
        digest = clean_digest(raw_digest)
        if relative_path and digest:
            files[relative_path] = digest
    if version < 1 or not revision:
        return None
    return {"version": version, "revision": revision, "files": files}


# Cleans the resource release catalog while allowing categories to be temporarily absent from disk.
def clean_catalog(value: Any) -> dict[str, dict[str, Any]]:
    """Return sanitized latest-release records keyed by Shared Resource name."""

    if not isinstance(value, dict):
        return {}
    catalog = {}
    # Each persisted catalog key must remain a portable resource folder name with a complete release record.
    for raw_name, raw_record in value.items():
        name = clean_resource_name(raw_name)
        record = clean_catalog_record(raw_record)
        if name and record:
            catalog[name] = record
    return catalog


# Cleans every version-keyed installation group without requiring currently disconnected folders to exist.
def clean_installations(value: Any) -> dict[str, dict[str, dict[str, Any]]]:
    """Return sanitized Shared Resources installations keyed by version path and resource name."""

    if not isinstance(value, dict):
        return {}
    installations = {}
    # Disconnected version paths stay addressable while malformed groups are discarded.
    for raw_version_path, raw_resources in value.items():
        version_path = str(raw_version_path or "").strip()
        if not version_path or not isinstance(raw_resources, dict):
            continue
        resources = {}
        # Each version retains only independently valid resource ownership manifests.
        for raw_name, raw_record in raw_resources.items():
            record = clean_installation(raw_record)
            name = clean_resource_name(raw_name)
            if record and name:
                record["resource"] = name
                resources[name] = record
        if resources:
            installations[version_path] = resources
    return installations


# Sanitizes Document Builder source links so updates can reuse a prior resource destination safely.
def clean_document_links(value: Any) -> dict[str, dict[str, str]]:
    """Return valid document-file links keyed by their physical source paths."""

    if not isinstance(value, dict):
        return {}
    links = {}
    # Document links retain physical source keys but sanitize every reusable resource destination.
    for raw_source_path, raw_link in value.items():
        source_path = str(raw_source_path or "").strip()
        if not source_path or not isinstance(raw_link, dict):
            continue
        resource = clean_resource_name(raw_link.get("resource"))
        target_path = clean_relative_metadata_path(raw_link.get("target_path"))
        if resource and target_path:
            links[source_path] = {"resource": resource, "target_path": target_path}
    return links


# Produces the complete persisted shape after dropping malformed or unsupported metadata.
def clean_registry(value: Any) -> dict[str, Any]:
    """Return the complete sanitized Shared Resources registry."""

    raw = value if isinstance(value, dict) else {}
    return {
        "schema_version": SHARED_RESOURCE_SCHEMA_VERSION,
        "catalog": clean_catalog(raw.get("catalog")),
        "installations": clean_installations(raw.get("installations")),
        "document_links": clean_document_links(raw.get("document_links")),
    }


# SharedResourceStore owns private resource metadata independently from project folders and repository settings.
class SharedResourceStore:
    """Persist resource installation manifests and Document Builder links atomically."""

    # Allows focused tests to supply an isolated path while production uses the standard application config folder.
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or app_config_path() / "shared-resources.json"

    # Returns an empty versioned registry without creating the metadata file.
    def defaults(self) -> dict[str, Any]:
        """Return the safe empty Shared Resources registry."""

        return clean_registry({})

    # Preserves malformed bytes before recovery so no potentially useful private metadata is silently discarded.
    def preserve_invalid_json(self) -> Path:
        """Return a private backup containing the unreadable registry bytes."""

        backup_path = invalid_json_backup_path(self.config_path)
        try:
            atomic_write_private_bytes(
                backup_path,
                self.config_path.read_bytes(),
                SHARED_RESOURCE_DIRECTORY_MODE,
                SHARED_RESOURCE_FILE_MODE,
            )
        except OSError as error:
            raise AppError(
                "Shared Resources metadata is invalid and could not be preserved.",
                "SHARED_RESOURCE_SETTINGS_INVALID_JSON",
            ) from error
        return backup_path

    # Loads, sanitizes, and repairs the registry while retaining a recoverable backup of malformed JSON.
    def load(self) -> dict[str, Any]:
        """Return current Shared Resources metadata from private application storage."""

        with APP_STORAGE_LOCK:
            if not self.config_path.exists():
                return self.defaults()
            try:
                with self.config_path.open("r", encoding="utf-8") as registry_file:
                    raw_registry = json.load(registry_file)
            except OSError as error:
                raise AppError(
                    "Unable to read Shared Resources metadata.",
                    "SHARED_RESOURCE_SETTINGS_READ_FAILED",
                ) from error
            except json.JSONDecodeError:
                backup_path = self.preserve_invalid_json()
                raw_registry = load_recoverable_json(backup_path)
                registry = clean_registry(raw_registry)
                self.write(registry)
                mark_backup_recovered(backup_path)
                return registry
            registry = clean_registry(raw_registry)
            if raw_registry != registry:
                self.write(registry)
            return registry

    # Writes only the sanitized registry with owner-only permissions.
    def write(self, registry: dict[str, Any]) -> None:
        """Persist complete Shared Resources metadata atomically."""

        try:
            atomic_write_private_json(
                self.config_path,
                clean_registry(registry),
                SHARED_RESOURCE_DIRECTORY_MODE,
                SHARED_RESOURCE_FILE_MODE,
            )
        except OSError as error:
            raise AppError(
                "Unable to save Shared Resources metadata.",
                "SHARED_RESOURCE_SETTINGS_WRITE_FAILED",
            ) from error

    # Replaces one version's resource record without exposing unrelated installations to callers.
    def set_installation(self, version_path: str, resource: str, record: dict[str, Any]) -> None:
        """Save one resource installation for a physical Local Mode version."""

        with APP_STORAGE_LOCK:
            registry = self.load()
            installations = registry["installations"]
            version_records = dict(installations.get(version_path) or {})
            version_records[resource] = {**record, "resource": resource}
            installations[version_path] = version_records
            self.write(registry)

    # Replaces the catalog's latest release only after its immutable snapshot has been written successfully.
    def set_catalog_release(self, resource: str, record: dict[str, Any]) -> None:
        """Save one explicitly recorded Shared Resource release."""

        with APP_STORAGE_LOCK:
            registry = self.load()
            registry["catalog"][resource] = record
            self.write(registry)

    # Removes one installation record and drops the empty version group left behind.
    def remove_installation(self, version_path: str, resource: str) -> dict[str, Any] | None:
        """Delete and return one resource installation record from private metadata."""

        with APP_STORAGE_LOCK:
            registry = self.load()
            version_records = dict(registry["installations"].get(version_path) or {})
            record = version_records.pop(resource, None)
            if version_records:
                registry["installations"][version_path] = version_records
            else:
                registry["installations"].pop(version_path, None)
            self.write(registry)
            return clean_installation(record)

    # Removes every installation owned by a version that is being permanently deleted.
    def remove_version_installations(self, version_path: str) -> dict[str, dict[str, Any]]:
        """Delete and return all resource records for one Local Mode version."""

        with APP_STORAGE_LOCK:
            registry = self.load()
            records = registry["installations"].pop(version_path, {})
            if records:
                self.write(registry)
            return records

    # Restores a removed version group when a later deletion step fails.
    def restore_version_installations(self, version_path: str, records: dict[str, Any]) -> None:
        """Merge previously removed resource records back into private metadata."""

        if not records:
            return
        with APP_STORAGE_LOCK:
            registry = self.load()
            current = dict(registry["installations"].get(version_path) or {})
            registry["installations"][version_path] = {**records, **current}
            self.write(registry)

    # Copies manifests when Local Mode copies a version so later updates remain revision-aware.
    def clone_installations(self, source_path: str, target_path: str) -> None:
        """Copy every tracked resource installation from one version path to another."""

        with APP_STORAGE_LOCK:
            registry = self.load()
            source_records = registry["installations"].get(source_path) or {}
            if source_records:
                registry["installations"][target_path] = json.loads(json.dumps(source_records))
                self.write(registry)

    # Remaps version keys after a project or version folder is renamed without changing resource ownership.
    def remap_installation_root(self, source_root: Path, target_root: Path) -> None:
        """Move installation keys rooted under source_root to their corresponding target_root paths."""

        with APP_STORAGE_LOCK:
            registry = self.load()
            remapped = {}
            changed = False
            # Every installation below the renamed root moves by the same relative path.
            for raw_path, records in registry["installations"].items():
                try:
                    relative_path = Path(raw_path).expanduser().resolve().relative_to(source_root)
                    next_path = str((target_root / relative_path).resolve())
                    changed = True
                except (OSError, ValueError):
                    next_path = raw_path
                remapped[next_path] = records
            if changed:
                registry["installations"] = remapped
                self.write(registry)

    # Saves the relationship that lets Document Builder update a previously published resource file.
    def set_document_link(self, source_path: str, resource: str, target_path: str) -> None:
        """Persist one Document Builder file-to-resource destination link."""

        with APP_STORAGE_LOCK:
            registry = self.load()
            registry["document_links"][source_path] = {
                "resource": resource,
                "target_path": target_path,
            }
            self.write(registry)
