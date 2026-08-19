"""Content revisions, Local Mode installation merges, and Document Builder publishing for Shared Resources."""

from __future__ import annotations

# Standard-library imports address safe relative paths and perform file-by-file release overlays.
from pathlib import Path, PurePosixPath
import shutil
from typing import Any

# GitDesk modules provide catalog validation, recorded releases, structured errors, and private manifests.
from gitdesk import aiskills
from gitdesk.errors import AppError
from gitdesk import sharedresource_releases
from gitdesk.sharedresource_overlay import retire_removed_paths
from gitdesk.sharedresource_store import SharedResourceStore


# Resource paths may be nested, but must remain portable relative paths inside both catalog and project roots.
MAX_RESOURCE_PATH_LENGTH = 512


# Validates a resource-relative destination before it can address catalog or project content.
def clean_relative_path(value: Any) -> str:
    """Return a safe portable resource-relative path."""

    normalized = str(value or "").replace("\\", "/").strip()
    parts = PurePosixPath(normalized).parts
    has_drive = len(normalized) >= 2 and normalized[1] == ":"
    if (
        not normalized
        or len(normalized) > MAX_RESOURCE_PATH_LENGTH
        or normalized == "."
        or normalized.startswith("/")
        or has_drive
        or ".." in parts
        or ".git" in parts
    ):
        raise AppError(
            "Shared Resource paths must stay inside the resource and cannot target .git.",
            "SHARED_RESOURCE_PATH_INVALID",
        )
    return PurePosixPath(normalized).as_posix()


# Converts a full manifest into the compact metadata exposed to the WebUI.
def manifest_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    """Return frontend-safe name, revision, and file-count metadata for one resource."""

    return {
        "name": manifest["name"],
        "revision": manifest["revision"],
        "revision_label": manifest["revision"][:12],
        "version": int(manifest.get("version") or 0),
        "version_label": f"v{int(manifest.get('version') or 0)}",
        "file_count": len(manifest["files"]),
    }


# Lists explicit release versions without treating unrecorded working-folder edits as published updates.
def list_resources(store: SharedResourceStore | None = None) -> dict[str, Any]:
    """Return the editable root and recorded release metadata for all Shared Resources."""

    return sharedresource_releases.list_resources(store)


# Preflights explicit selections before callers create project folders or remote repositories.
def validate_resource_selection(value: Any, store: SharedResourceStore | None = None) -> list[str]:
    """Return cleaned resource names after confirming every selection has a recorded snapshot."""

    resource_store = store or SharedResourceStore()
    names = aiskills.clean_category_selection(value)
    # Every selection is resolved before callers create external folders or repositories.
    for name in names:
        sharedresource_releases.release_manifest(name, resource_store)
    return names


# Supplies the Local version inspector from tracked metadata without scanning or claiming untracked project files.
def installed_resource_summary(
    path_value: str,
    store: SharedResourceStore | None = None,
    registry: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return installed resource names and recorded versions for one physical version path."""

    version_path = str(Path(path_value).expanduser().resolve())
    resource_registry = registry or (store or SharedResourceStore()).load()
    records = resource_registry["installations"].get(version_path) or {}
    summaries = []
    # Local rows compare exact installed metadata with the latest explicitly recorded catalog release.
    for name, record in sorted(records.items(), key=lambda item: item[0].casefold()):
        latest = resource_registry["catalog"].get(name) or {}
        installed_version = int(record.get("version") or 0)
        latest_version = int(latest.get("version") or 0)
        # Legacy installs name the numbered merge that will establish reliable tracking when one is available.
        if installed_version:
            tracking_message = ""
        elif latest_version:
            tracking_message = f"Merge v{latest_version} to enable version tracking."
        else:
            tracking_message = "Use a numbered resource version to enable version tracking."
        summaries.append({
            "name": name,
            "version": installed_version,
            "version_label": f"v{installed_version}" if installed_version else "Legacy",
            "legacy": installed_version == 0,
            "tracking_message": tracking_message,
            "latest_version": latest_version,
            "latest_version_label": f"v{latest_version}" if latest_version else "",
            "update_available": bool(
                latest
                and (
                    latest.get("revision") != record.get("revision")
                    or latest.get("version") != record.get("version")
                )
            ),
        })
    return summaries


# Resolves a destination folder and rejects symlink roots before any managed paths are addressed below it.
def destination_directory(path_value: str) -> Path:
    """Return a safe existing Shared Resources installation destination."""

    raw_path = str(path_value or "").strip()
    source_path = Path(raw_path).expanduser() if raw_path else Path()
    if not raw_path or source_path.is_symlink():
        raise AppError("Shared Resources destination is invalid.", "SHARED_RESOURCE_DESTINATION_INVALID")
    destination = source_path.resolve()
    if not destination.is_dir():
        raise AppError(
            "Shared Resources destination must be an existing folder.",
            "SHARED_RESOURCE_DESTINATION_INVALID",
        )
    return destination


# Rejects symlinks at every managed path component so an overlay cannot redirect writes or removals elsewhere.
def managed_target(destination: Path, relative_path: str) -> Path:
    """Return a contained non-symlink target path for one managed resource file."""

    clean_path = clean_relative_path(relative_path)
    current_path = destination
    # Each component is checked before later code creates parents or writes a file through it.
    for part in PurePosixPath(clean_path).parts:
        current_path = current_path / part
        if current_path.is_symlink():
            raise AppError(
                "Shared Resource paths cannot pass through symbolic links.",
                "SHARED_RESOURCE_SYMLINK_REJECTED",
            )
    return aiskills.folder_skill_target(destination, Path(clean_path))


# Counts recorded managed paths still present without treating unrelated destination files as resource content.
def installed_file_count(destination: Path, record: dict[str, Any]) -> int:
    """Return the number of one installation's recorded files still present in the destination."""

    present = 0
    # Presence is limited to manifest-owned paths and never scans unrelated project content.
    for relative_path in record.get("files") or {}:
        target_path = managed_target(destination, relative_path)
        if target_path.is_file() and not target_path.is_symlink():
            present += 1
    return present


# Builds version-specific rows for the management modal from catalog revisions and private manifests.
def version_resource_state(path_value: str, store: SharedResourceStore | None = None) -> dict[str, Any]:
    """Return install, missing-file, and update state for every resource in one Local Mode version."""

    destination = destination_directory(path_value)
    resource_store = store or SharedResourceStore()
    registry = resource_store.load()
    records = registry["installations"].get(str(destination), {})
    rows = []
    catalog_resources = list_resources(resource_store)["resources"]
    catalog_names = {item["name"] for item in catalog_resources}
    # Every catalog row is joined with only the selected version's private ownership record.
    for catalog_item in catalog_resources:
        record = records.get(catalog_item["name"])
        # Only explicit project-creation or manager installs establish ownership; pre-existing copies stay untracked.
        if record:
            present_count = installed_file_count(destination, record)
        else:
            present_count = 0
        expected_count = len(record.get("files") or {}) if record else 0
        installed = bool(record)
        installed_legacy = bool(record and not record.get("version"))
        missing = bool(installed and present_count < expected_count)
        outdated = bool(
            record
            and catalog_item.get("recorded")
            and (
                record.get("revision") != catalog_item.get("revision")
                or record.get("version") != catalog_item.get("version")
            )
        )
        # Missing files take priority over revision age because Update can restore and refresh in one action.
        if missing:
            status = "missing"
        elif installed_legacy:
            status = "legacy"
        elif outdated:
            status = "outdated"
        elif not catalog_item.get("recorded"):
            status = "legacy"
        else:
            status = "current" if installed else "available"
        tracking_message = catalog_item.get("tracking_message", "")
        # A tracked legacy install can become numbered immediately because its release already exists.
        if installed_legacy and catalog_item.get("recorded"):
            tracking_message = f"Merge {catalog_item['version_label']} to enable version tracking."
        rows.append({
            **catalog_item,
            "installed": installed,
            "tracked": bool(record),
            "installed_legacy": installed_legacy,
            "merge_available": bool(installed_legacy and catalog_item.get("recorded")),
            "status": status,
            "update_available": bool(outdated or missing),
            "installed_revision": str((record or {}).get("revision") or ""),
            "installed_version": int((record or {}).get("version") or 0),
            "installed_version_label": (
                f"v{int(record.get('version') or 0)}" if record and record.get("version") else "Legacy"
            ) if record else "",
            "tracking_message": tracking_message,
            "present_file_count": present_count,
        })
    # Installed resources remain removable even when their source category no longer exists in the catalog.
    for name in sorted(set(records) - catalog_names, key=str.casefold):
        record = records[name]
        present_count = installed_file_count(destination, record)
        rows.append({
            "name": name,
            "revision": record.get("revision") or "",
            "revision_label": str(record.get("revision") or "")[:12],
            "version": 0,
            "version_label": "Unavailable",
            "file_count": len(record.get("files") or {}),
            "installed": True,
            "tracked": True,
            "installed_legacy": not bool(record.get("version")),
            "merge_available": False,
            "status": "unavailable",
            "update_available": False,
            "installed_revision": record.get("revision") or "",
            "installed_version": int(record.get("version") or 0),
            "installed_version_label": f"v{int(record.get('version') or 0)}" if record.get("version") else "Legacy",
            "tracking_message": (
                "Use a numbered resource version to enable version tracking." if not record.get("version") else ""
            ),
            "present_file_count": present_count,
        })
    return {"version_path": str(destination), "resources": rows}


# Overlays one current resource revision and records exactly which relative paths it owns in this version.
def install_resource(
    name_value: str,
    path_value: str,
    store: SharedResourceStore | None = None,
) -> dict[str, Any]:
    """Merge one resource into a destination and persist its current installation manifest."""

    destination = destination_directory(path_value)
    resource_store = store or SharedResourceStore()
    manifest = sharedresource_releases.release_manifest(name_value, resource_store)
    registry = resource_store.load()
    previous = (registry["installations"].get(str(destination)) or {}).get(manifest["name"]) or {}
    # A release update overlays only its recorded project-relative files and never replaces the version folder.
    for relative_path, source_path in manifest["sources"].items():
        target_path = managed_target(destination, relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
    retirement = retire_removed_paths(
        destination,
        previous.get("files") or {},
        manifest["files"],
        managed_target,
        sharedresource_releases.file_digest,
    )
    resource_store.set_installation(
        str(destination),
        manifest["name"],
        {
            "version": manifest["version"],
            "revision": manifest["revision"],
            "files": manifest["files"],
        },
    )
    return {**manifest_payload(manifest), **retirement, "destination": str(destination)}


# Removes only paths recorded for one resource and prunes parents only while they remain empty below the version root.
def remove_resource(
    name_value: str,
    path_value: str,
    store: SharedResourceStore | None = None,
) -> dict[str, Any]:
    """Remove one tracked resource without deleting unrelated destination content."""

    destination = destination_directory(path_value)
    resource_store = store or SharedResourceStore()
    name = aiskills.clean_category_name(name_value)
    registry = resource_store.load()
    record = (registry["installations"].get(str(destination)) or {}).get(name)
    removed_files = 0
    preserved_files = 0
    # Removal checks both owned paths and installed bytes so project edits are never deleted as stale resources.
    for relative_path in (record or {}).get("files") or {}:
        target_path = managed_target(destination, relative_path)
        expected_digest = record["files"][relative_path]
        matches_install = (
            target_path.is_file()
            and not target_path.is_symlink()
            and sharedresource_releases.file_digest(target_path) == expected_digest
        )
        # User-modified files are preserved because their bytes no longer match GitDesk's installed ownership record.
        if matches_install:
            target_path.unlink()
            removed_files += 1
        elif target_path.exists() or target_path.is_symlink():
            preserved_files += 1
        parent = target_path.parent
        # Only newly empty resource parents are pruned, stopping before the physical version root.
        while parent != destination:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    resource_store.remove_installation(str(destination), name)
    return {
        "resource": name,
        "destination": str(destination),
        "removed_file_count": removed_files,
        "preserved_file_count": preserved_files,
    }


# Applies checkbox selection changes without silently updating resources whose revisions changed.
def apply_resource_selection(
    path_value: str,
    selected_value: Any,
    store: SharedResourceStore | None = None,
) -> dict[str, Any]:
    """Add newly checked resources and remove newly unchecked tracked resources for one version."""

    destination = destination_directory(path_value)
    resource_store = store or SharedResourceStore()
    catalog = list_resources(resource_store)["resources"]
    available = {item["name"] for item in catalog if item.get("recorded")}
    selected = set(aiskills.clean_category_selection(selected_value))
    registry = resource_store.load()
    installed = set((registry["installations"].get(str(destination)) or {}).keys())
    unrecorded = selected - available - installed
    if unrecorded:
        raise AppError(
            "Record selected Shared Resources in Settings before adding them to a project.",
            "SHARED_RESOURCE_RELEASE_REQUIRED",
        )
    # Newly checked recorded releases become tracked overlays without updating existing checked resources.
    for name in sorted((selected - installed) & available, key=str.casefold):
        install_resource(name, str(destination), resource_store)
    # Newly unchecked records remove only their matching managed bytes and drop ownership metadata.
    for name in sorted(installed - selected, key=str.casefold):
        remove_resource(name, str(destination), resource_store)
    return version_resource_state(str(destination), resource_store)


# Carries private manifests forward whenever Local Mode copies a physical version folder.
def clone_installations(source_value: str, target_value: str, store: SharedResourceStore | None = None) -> None:
    """Copy resource installation metadata from a source version to its new physical copy."""

    source = Path(source_value).expanduser().resolve()
    target = Path(target_value).expanduser().resolve()
    (store or SharedResourceStore()).clone_installations(str(source), str(target))


# Keeps installation keys aligned when Local Mode renames a project or version folder.
def remap_installations(source: Path, target: Path, store: SharedResourceStore | None = None) -> None:
    """Remap tracked version paths rooted under a renamed folder."""

    (store or SharedResourceStore()).remap_installation_root(source.resolve(), target.resolve())


# Records manual folder edits from Settings without conflating them with incidental catalog reads.
def record_resource_update(name_value: str, store: SharedResourceStore | None = None) -> dict[str, Any]:
    """Record one resource working folder as its next explicit numbered release."""

    return sharedresource_releases.record_release(name_value, store)
