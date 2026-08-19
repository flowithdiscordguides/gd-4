"""Document Builder publishing links and explicit Shared Resource release updates."""

from __future__ import annotations

# Standard-library imports validate physical document files and copy them into resource working folders.
from pathlib import Path
import shutil
from typing import Any

# GitDesk modules enforce catalog names, safe paths, explicit releases, and private document links.
from gitdesk import aiskills
from gitdesk.errors import AppError
from gitdesk import sharedresource_releases
from gitdesk import sharedresources
from gitdesk.sharedresource_store import SharedResourceStore


# Copies a selected document into a resource working folder without silently publishing a numbered release.
def publish_document_file(
    source_value: str,
    resource_value: str,
    target_value: str,
    store: SharedResourceStore | None = None,
) -> dict[str, Any]:
    """Publish one document file to a working path and remember its future update destination."""

    source = Path(str(source_value or "")).expanduser()
    if source.is_symlink() or not source.resolve().is_file():
        raise AppError("Selected document file is invalid.", "SHARED_RESOURCE_SOURCE_INVALID")
    resource = aiskills.clean_category_name(resource_value)
    if not aiskills.category_source_paths(resource):
        raise AppError("Shared Resource does not exist.", "SHARED_RESOURCE_NOT_FOUND")
    target_path = sharedresources.clean_relative_path(target_value)
    writable_root = aiskills.writable_categories_root(create=True)
    resource_root = (writable_root / resource).resolve()
    resource_root.mkdir(parents=True, exist_ok=True)
    destination = sharedresources.managed_target(resource_root, target_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source.resolve(), destination)
    resource_store = store or SharedResourceStore()
    resource_store.set_document_link(str(source.resolve()), resource, target_path)
    working = sharedresource_releases.working_manifest(resource)
    record = resource_store.load()["catalog"].get(resource)
    return {
        "link": {"resource": resource, "target_path": target_path},
        **sharedresource_releases.resource_payload(resource, working, record),
    }


# Republishes a linked document and records the whole resource working folder as one explicit release update.
def update_document_file(source_value: str, store: SharedResourceStore | None = None) -> dict[str, Any]:
    """Update a linked resource file and record its resource's next numbered release."""

    source = Path(str(source_value or "")).expanduser().resolve()
    resource_store = store or SharedResourceStore()
    link = resource_store.load()["document_links"].get(str(source))
    if not link:
        raise AppError(
            "Add this document file to Shared Resources before updating it.",
            "SHARED_RESOURCE_DOCUMENT_LINK_MISSING",
        )
    published = publish_document_file(str(source), link["resource"], link["target_path"], resource_store)
    released = sharedresource_releases.record_release(link["resource"], resource_store)
    return {**released, "link": published["link"]}


# Combines release choices with the saved destination for the currently selected Document Builder file.
def document_resource_state(source_value: str, store: SharedResourceStore | None = None) -> dict[str, Any]:
    """Return Shared Resource choices and the selected document file's publish link."""

    raw_source = str(source_value or "").strip()
    source_path = str(Path(raw_source).expanduser().resolve()) if raw_source else ""
    resource_store = store or SharedResourceStore()
    registry = resource_store.load()
    return {
        **sharedresource_releases.list_resources(resource_store),
        "link": registry["document_links"].get(source_path),
    }
