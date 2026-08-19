"""Shared typed progress callback for long-running Sync Chain operations."""

from __future__ import annotations

from typing import Any, Callable


ProgressCallback = Callable[[dict[str, Any]], None]


# Keeps progress optional for direct callers while giving background jobs factual phases.
def report_progress(progress: ProgressCallback | None, **details: Any) -> None:
    """Send one progress update when a caller supplied a reporter."""

    if progress:
        progress(details)
