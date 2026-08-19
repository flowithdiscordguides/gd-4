"""Timestamps and bounded receipt sanitation for persisted Sync Chain records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def sync_timestamp() -> str:
    """Return an ISO-8601 UTC timestamp without fractional seconds."""

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_receipt(value: Any) -> dict[str, Any] | None:
    """Return a sanitized synchronization receipt, or None for malformed metadata."""

    if not isinstance(value, dict):
        return None
    destination_digest = str(value.get("destination_digest") or "").strip()
    if not destination_digest:
        return None
    try:
        counts = [max(0, int(value.get(name) or 0)) for name in ("file_count", "directory_count", "total_bytes")]
    except (TypeError, ValueError):
        return None
    return {
        "source_path": str(value.get("source_path") or "").strip(),
        "destination_path": str(value.get("destination_path") or "").strip(),
        "source_digest": str(value.get("source_digest") or "").strip(),
        "destination_digest": destination_digest,
        "synced_at": str(value.get("synced_at") or "").strip()[:40],
        "file_count": counts[0],
        "directory_count": counts[1],
        "total_bytes": counts[2],
        "sync_mode": str(value.get("sync_mode") or "working_tree")[:32],
        "release_tag": str(value.get("release_tag") or "").strip()[:128],
    }
