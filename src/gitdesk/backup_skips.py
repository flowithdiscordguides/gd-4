"""Factual skipped-item records and installed-manifest filtering for Backup Mode."""

from __future__ import annotations

# Stable hashes keep source locations out of frontend commands and user-visible markup.
import hashlib
from pathlib import Path
from typing import Any


# Builds one stable opaque identifier from manifest-owned values rather than an absolute source path.
def skipped_item_id(source_id: str, entry_key: str) -> str:
    """Return a stable opaque id for one skipped manifest entry."""

    identity = f"{source_id}\0{entry_key}".encode("utf-8", errors="surrogateescape")
    return hashlib.sha256(identity).hexdigest()[:24]


# Resolves the original registered location represented by one source-relative manifest entry.
def original_item_path(source: dict[str, Any], relative_path: str) -> str:
    """Return the absolute original path for a skipped source item."""

    root = Path(str(source.get("path") or "")).expanduser().absolute()
    if source.get("kind") != "directory" or not relative_path:
        return str(root)
    return str(root.joinpath(*Path(relative_path).parts))


# Creates one complete durable ledger record while keeping display and source locations separate.
def skipped_item(
    source: dict[str, Any],
    entry_key: str,
    relative_path: str,
    entry: dict[str, Any],
    code: str,
    reason: str,
) -> dict[str, Any]:
    """Return one JSON-safe skipped-item record with its captured original location."""

    source_id = str(source.get("id") or "")
    return {
        "id": skipped_item_id(source_id, entry_key),
        "source_id": source_id,
        "path": entry_key,
        "name": Path(entry_key).name or str(source.get("label") or entry_key),
        "kind": str(entry.get("kind") or "item"),
        "code": str(code or "BACKUP_ITEM_SKIPPED")[:100],
        "reason": str(reason or "The item could not be copied.")[:500],
        "source_path": original_item_path(source, relative_path),
    }


# Returns the frontend-safe ledger without placing captured absolute locations in browser state.
def public_skipped_items(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return skipped-item records safe for transfer and history rendering."""

    return [
        {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or "Skipped item"),
            "kind": str(item.get("kind") or "item"),
            "code": str(item.get("code") or "BACKUP_ITEM_SKIPPED"),
            "reason": str(item.get("reason") or "The item could not be copied."),
        }
        for item in items
    ]


# Builds the private lookup consumed only by the process-owned Backup job reveal command.
def private_skipped_paths(items: list[dict[str, Any]]) -> dict[str, str]:
    """Return captured source locations keyed by opaque skipped-item id."""

    return {
        str(item["id"]): str(item["source_path"])
        for item in items
        if item.get("id") and item.get("source_path")
    }


# Removes skipped entries and recomputes every installed-content total from the surviving manifest.
def installed_manifest(
    requested_manifest: dict[str, Any],
    skipped_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the exact manifest for content physically eligible for installation."""

    skipped_paths = {str(item.get("path") or "") for item in skipped_items}
    entries = {
        key: value
        for key, value in requested_manifest.get("entries", {}).items()
        if key not in skipped_paths
    }
    total_bytes = sum(int(item.get("size") or 0) for item in entries.values() if item.get("kind") == "file")
    return {
        **requested_manifest,
        "entries": entries,
        "errors": [],
        "file_count": sum(item.get("kind") in {"file", "link"} for item in entries.values()),
        "directory_count": sum(item.get("kind") == "directory" for item in entries.values()),
        "total_bytes": total_bytes,
        "requested_file_count": int(requested_manifest.get("file_count") or 0),
        "requested_directory_count": int(requested_manifest.get("directory_count") or 0),
        "requested_total_bytes": int(requested_manifest.get("total_bytes") or 0),
        "skipped_count": len(skipped_items),
        "skipped_paths": sorted(skipped_paths, key=str.casefold),
    }
