"""Project-scoped notification facts derived from Local Mode activity and Sync Chain receipts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from gitdesk.syncchains import clean_sync_chains


# Parses persisted UTC timestamps without allowing malformed history to become a fresh notification.
def parsed_timestamp(value: Any) -> datetime | None:
    """Return an aware ISO timestamp or None when the stored value is invalid."""

    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


# Returns the durable acknowledgement boundary for one project's Local-to-Private-Beta changes.
def notification_boundary(chain: dict[str, Any]) -> datetime | None:
    """Use the latest Local sync receipt, falling back to the chain creation time."""

    receipt = chain.get("receipts", {}).get("local_to_private_beta") or {}
    return parsed_timestamp(receipt.get("synced_at") or chain.get("created_at"))


# Projects only added and edited file events detected after the chain's last Local sync.
def sync_chain_notifications(
    settings: dict[str, Any],
    file_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return one frontend-safe pending-change record for each affected Sync Chain project."""

    notifications = []
    for chain in clean_sync_chains(settings.get("sync_chains")):
        boundary = notification_boundary(chain)
        if boundary is None:
            continue
        pending = []
        for event in file_events:
            occurred_at = parsed_timestamp(event.get("occurred_at"))
            if str(event.get("project_path") or "") != chain["project_path"]:
                continue
            if occurred_at is not None and occurred_at > boundary:
                pending.append(event)
        if not pending:
            continue
        latest = max(pending, key=lambda event: parsed_timestamp(event.get("occurred_at")))
        notifications.append({
            "chain_id": chain["id"],
            "project_path": chain["project_path"],
            "change_count": len(pending),
            "latest_changed_at": str(latest.get("occurred_at") or ""),
        })
    return notifications
