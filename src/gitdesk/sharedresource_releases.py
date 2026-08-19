"""Explicit numbered releases and immutable snapshots for editable Shared Resource working folders."""

from __future__ import annotations

# Standard-library imports hash files, address safe paths, and stage immutable snapshot copies.
from hashlib import sha256
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any

# GitDesk modules provide catalog validation, structured errors, and private release metadata.
from gitdesk import aiskills
from gitdesk.errors import AppError
from gitdesk.sharedresource_store import SharedResourceStore
from gitdesk.storage import APP_STORAGE_LOCK


# Enforces one portable relative namespace for snapshots and every project installation platform.
def clean_working_path(value: str) -> str:
    """Return a safe portable working-file path or raise a structured catalog error."""

    normalized = str(value or "").replace("\\", "/").strip()
    parts = PurePosixPath(normalized).parts
    has_drive = len(normalized) > 1 and normalized[1] == ":"
    if (
        not normalized
        or len(normalized) > 512
        or normalized.startswith("/")
        or ".." in parts
        or ".git" in parts
        or has_drive
    ):
        raise AppError(
            "Shared Resource files must use project-relative paths outside .git.",
            "SHARED_RESOURCE_PATH_INVALID",
        )
    return PurePosixPath(normalized).as_posix()


# Streams files into SHA-256 so large resources never need to be loaded into memory as a single byte string.
def file_digest(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one regular file."""

    digest = sha256()
    with path.open("rb") as source_file:
        # Fixed-size chunks bound memory while preserving the same digest as a complete-file read.
        for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Resolves layered bundled and writable files with the writable working copy applied last.
def working_files(name_value: str) -> dict[str, Path]:
    """Return effective working files keyed by portable resource-relative path."""

    name = aiskills.clean_category_name(name_value)
    source_paths = aiskills.category_source_paths(name)
    if not source_paths:
        raise AppError("Shared Resource does not exist.", "SHARED_RESOURCE_NOT_FOUND")
    files = {}
    # Later category sources intentionally replace the same relative path from bundled legacy content.
    for source_path in source_paths:
        # Regular files below each layer retain their project-relative locations in the effective working set.
        for source_item in sorted(source_path.rglob("*"), key=lambda item: item.as_posix().lower()):
            if (
                source_item.name in aiskills.IGNORED_SKILL_FILE_NAMES
                or source_item.is_symlink()
                or not source_item.is_file()
            ):
                continue
            relative_path = clean_working_path(source_item.relative_to(source_path).as_posix())
            files[relative_path] = source_item
    return files


# Hashes paths and file bytes together so additions, removals, renames, and edits change the working revision.
def manifest_from_files(name: str, files: dict[str, Path]) -> dict[str, Any]:
    """Return content-addressed working metadata and its source paths."""

    revision_digest = sha256()
    manifest_files = {}
    # Stable path ordering makes the same cross-platform working content produce the same release identity.
    for relative_path in sorted(files, key=str.casefold):
        digest = file_digest(files[relative_path])
        manifest_files[relative_path] = digest
        revision_digest.update(relative_path.encode("utf-8"))
        revision_digest.update(b"\0")
        revision_digest.update(digest.encode("ascii"))
        revision_digest.update(b"\0")
    return {
        "name": name,
        "revision": revision_digest.hexdigest(),
        "files": manifest_files,
        "sources": files,
    }


# Returns current working-copy metadata without changing the catalog's explicitly recorded latest release.
def working_manifest(name_value: str) -> dict[str, Any]:
    """Return the current editable contents for one resource."""

    name = aiskills.clean_category_name(name_value)
    return manifest_from_files(name, working_files(name))


# Keeps release snapshots beside their private registry so project installs do not depend on mutable working files.
def snapshots_root(store: SharedResourceStore) -> Path:
    """Return the owner-private snapshot root for a Shared Resource store."""

    return store.config_path.parent / "shared-resource-releases"


# Resolves one immutable content-addressed snapshot folder below the private catalog root.
def snapshot_path(store: SharedResourceStore, name: str, revision: str) -> Path:
    """Return the snapshot directory for one safe resource name and recorded digest."""

    return snapshots_root(store) / aiskills.clean_category_name(name) / revision


# Rejects tampered symlink components before an immutable snapshot file can be read or copied into a project.
def snapshot_source(root: Path, relative_path: str) -> Path:
    """Return one contained non-symlink snapshot file path."""

    current = root
    # Every existing component is checked so a tampered parent symlink cannot redirect snapshot reads.
    for part in PurePosixPath(clean_working_path(relative_path)).parts:
        current = current / part
        if current.is_symlink():
            raise AppError("A Shared Resource snapshot is unsafe.", "SHARED_RESOURCE_SNAPSHOT_INVALID")
    return current


# Verifies existing snapshot bytes before they are reused as an authoritative release source.
def snapshot_matches(path: Path, files: dict[str, str]) -> bool:
    """Return True when every recorded snapshot file exists with its expected digest."""

    if not path.is_dir() or path.is_symlink():
        return False
    # A snapshot is authoritative only when every recorded path still has its recorded bytes.
    for relative_path, digest in files.items():
        try:
            source = snapshot_source(path, relative_path)
        except AppError:
            return False
        if not source.is_file() or file_digest(source) != digest:
            return False
    return True


# Writes into a staging folder first so a failed copy never becomes the catalog's recorded immutable release.
def write_snapshot(store: SharedResourceStore, manifest: dict[str, Any]) -> Path:
    """Create or validate one immutable release snapshot and return its directory."""

    target = snapshot_path(store, manifest["name"], manifest["revision"])
    if target.exists():
        if snapshot_matches(target, manifest["files"]):
            return target
        raise AppError("A Shared Resource snapshot is incomplete.", "SHARED_RESOURCE_SNAPSHOT_INVALID")
    resource_root = target.parent
    resource_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=".recording-", dir=str(resource_root)))
    try:
        # Each effective working file is copied to the same project-relative path inside the release snapshot.
        for relative_path, source in manifest["sources"].items():
            destination = staging / Path(relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        staging.rename(target)
    except OSError as error:
        shutil.rmtree(staging, ignore_errors=True)
        raise AppError(
            "Unable to record the Shared Resource update.",
            "SHARED_RESOURCE_SNAPSHOT_WRITE_FAILED",
        ) from error
    return target


# Converts stored or working manifests into the stable row shape used across Settings and project creation.
def resource_payload(name: str, working: dict[str, Any] | None, record: dict[str, Any] | None) -> dict[str, Any]:
    """Return release, working-change, and file-count metadata for one resource row."""

    recorded = bool(record)
    version = int((record or {}).get("version") or 0)
    revision = str((record or {}).get("revision") or "")
    working_revision = str((working or {}).get("revision") or "")
    return {
        "name": name,
        "recorded": recorded,
        "legacy": not recorded,
        "version": version,
        "version_label": f"v{version}" if version else "Legacy",
        "tracking_message": "" if recorded else "Record a numbered version to enable version tracking.",
        "revision": revision,
        "revision_label": revision[:12],
        "file_count": len((record or working or {}).get("files") or {}),
        "working_file_count": len((working or {}).get("files") or {}),
        "source_available": working is not None,
        "has_unrecorded_changes": bool(working and working_revision != revision),
    }


# Lists release metadata without hashing large working folders until the user explicitly chooses Update.
def list_resources(store: SharedResourceStore | None = None) -> dict[str, Any]:
    """Return every working or recorded Shared Resource and its explicit release state."""

    resource_store = store or SharedResourceStore()
    registry = resource_store.load()
    category_data = aiskills.list_categories()
    disk_categories = {item["name"]: item for item in category_data["categories"]}
    disk_names = set(disk_categories)
    names = disk_names | set(registry["catalog"])
    resources = []
    # Recorded-only resources remain installable from snapshots even when their editable folder is unavailable.
    for name in sorted(names, key=str.casefold):
        record = registry["catalog"].get(name)
        payload = resource_payload(name, None, record)
        payload["source_available"] = name in disk_names
        payload["working_file_count"] = int((disk_categories.get(name) or {}).get("file_count") or 0)
        payload["has_unrecorded_changes"] = not record and name in disk_names
        resources.append(payload)
    return {"root": category_data["root"], "resources": resources, "categories": resources}


# Advances a resource only when its working content differs from the last explicit recorded release.
def record_release(name_value: str, store: SharedResourceStore | None = None) -> dict[str, Any]:
    """Record the current working folder as the next numbered immutable release."""

    resource_store = store or SharedResourceStore()
    # One lock spans hash, snapshot, version increment, and registry write so concurrent updates cannot reuse a vN.
    with APP_STORAGE_LOCK:
        manifest = working_manifest(name_value)
        previous = resource_store.load()["catalog"].get(manifest["name"])
        if previous and previous.get("revision") == manifest["revision"]:
            return {**resource_payload(manifest["name"], manifest, previous), "changed": False}
        version = int((previous or {}).get("version") or 0) + 1
        write_snapshot(resource_store, manifest)
        record = {"version": version, "revision": manifest["revision"], "files": manifest["files"]}
        resource_store.set_catalog_release(manifest["name"], record)
        return {**resource_payload(manifest["name"], manifest, record), "changed": True}


# Resolves only the latest explicit release; mutable working-copy bytes never enter project installs directly.
def release_manifest(name_value: str, store: SharedResourceStore | None = None) -> dict[str, Any]:
    """Return latest recorded metadata and immutable snapshot file paths for one resource."""

    resource_store = store or SharedResourceStore()
    name = aiskills.clean_category_name(name_value)
    record = resource_store.load()["catalog"].get(name)
    if not record:
        raise AppError(
            "Record this Shared Resource in Settings before adding it to a project.",
            "SHARED_RESOURCE_RELEASE_REQUIRED",
        )
    snapshot = snapshot_path(resource_store, name, record["revision"])
    if not snapshot_matches(snapshot, record["files"]):
        raise AppError("The recorded Shared Resource snapshot is unavailable.", "SHARED_RESOURCE_SNAPSHOT_INVALID")
    sources = {relative_path: snapshot_source(snapshot, relative_path) for relative_path in record["files"]}
    return {"name": name, **record, "sources": sources}
