"""Owner-only registry persistence for Document Builder metadata and active selections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gitdesk import documentbuilder
from gitdesk.errors import AppError
from gitdesk.reposettings import clean_category_name
from gitdesk.reposettings_recovery import invalid_json_backup_path, load_recoverable_json, mark_backup_recovered
from gitdesk.storage import APP_STORAGE_LOCK, app_config_path, atomic_write_private_bytes, atomic_write_private_json


# The schema field allows future metadata additions without guessing which shape an older file used.
DOCUMENT_SCHEMA_VERSION = 1

# Document paths and category names are private local metadata readable only by the current user.
DOCUMENT_DIRECTORY_MODE = 0o700
DOCUMENT_FILE_MODE = 0o600


# Sanitizes category arrays while keeping first-seen display order.
def clean_categories(value: Any) -> list[str]:
    """Return valid unique document category labels."""

    if not isinstance(value, list):
        return []
    categories = []
    for raw_category in value:
        try:
            category = clean_category_name(raw_category)
        except AppError:
            continue
        if category and category not in categories:
            categories.append(category)
    return categories


# Normalizes raw disk content into the only metadata shape Document Builder persists.
def clean_registry(value: Any) -> dict[str, Any]:
    """Return a complete sanitized Document Builder registry."""

    raw = value if isinstance(value, dict) else {}
    documents = documentbuilder.clean_document_records(raw.get("documents"))
    categories = clean_categories(raw.get("categories"))
    for record in documents:
        category = record.get("category", "")
        if category and category not in categories:
            categories.append(category)
    document_paths = {record["path"] for record in documents}
    active_document = str(raw.get("active_document") or "")
    if active_document not in document_paths:
        active_document = ""
    return {
        "schema_version": DOCUMENT_SCHEMA_VERSION,
        "documents": documents,
        "categories": categories,
        "active_document": active_document,
        "active_folder": str(raw.get("active_folder") or "") if active_document else "",
        "active_file": str(raw.get("active_file") or "") if active_document else "",
    }


# DocumentStore owns documents.json independently from Git/account and Local Mode settings.
class DocumentStore:
    """Persist non-secret Document Builder registry metadata atomically."""

    # Prepares the platform config path without creating the registry until the first save.
    def __init__(self) -> None:
        self.config_path = app_config_path() / "documents.json"

    # Returns the safe empty registry used when no saved metadata exists.
    def defaults(self) -> dict[str, Any]:
        """Return an empty versioned document registry."""

        return clean_registry({})

    # Preserves malformed bytes before attempting to recover a complete JSON object from them.
    def preserve_invalid_json(self) -> Path:
        """Return a private backup containing the current malformed registry."""

        backup_path = invalid_json_backup_path(self.config_path)
        try:
            atomic_write_private_bytes(
                backup_path,
                self.config_path.read_bytes(),
                DOCUMENT_DIRECTORY_MODE,
                DOCUMENT_FILE_MODE,
            )
        except OSError as error:
            raise AppError(
                "Document metadata is invalid and could not be preserved.",
                "DOCUMENT_SETTINGS_INVALID_JSON",
            ) from error
        return backup_path

    # Loads the registry, sanitizes it, and salvages valid metadata from malformed trailing content.
    def load(self) -> dict[str, Any]:
        """Return the current sanitized Document Builder registry."""

        with APP_STORAGE_LOCK:
            if not self.config_path.exists():
                return self.defaults()
            try:
                with self.config_path.open("r", encoding="utf-8") as registry_file:
                    raw_registry = json.load(registry_file)
            except OSError as error:
                raise AppError("Unable to read document metadata.", "DOCUMENT_SETTINGS_READ_FAILED") from error
            except json.JSONDecodeError:
                backup_path = self.preserve_invalid_json()
                recovered = load_recoverable_json(backup_path)
                registry = clean_registry(recovered)
                self.write(registry)
                mark_backup_recovered(backup_path)
                return registry
            registry = clean_registry(raw_registry)
            if raw_registry != registry:
                self.write(registry)
            return registry

    # Atomically replaces documents.json using private app-metadata permissions.
    def write(self, registry: dict[str, Any]) -> None:
        """Persist a sanitized document registry."""

        try:
            atomic_write_private_json(
                self.config_path,
                clean_registry(registry),
                DOCUMENT_DIRECTORY_MODE,
                DOCUMENT_FILE_MODE,
            )
        except OSError as error:
            raise AppError("Unable to save document metadata.", "DOCUMENT_SETTINGS_WRITE_FAILED") from error

    # Merges approved registry fields with the latest disk state to prevent worker update loss.
    def save(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Persist allowed metadata updates and return the complete registry."""

        with APP_STORAGE_LOCK:
            registry = self.load()
            for key in ("documents", "categories", "active_document", "active_folder", "active_file"):
                if key in updates:
                    registry[key] = updates[key]
            registry = clean_registry(registry)
            self.write(registry)
            return registry
