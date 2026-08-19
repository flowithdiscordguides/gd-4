"""Factual phase, byte, and item progress for cancellable Backup Mode transactions."""

from __future__ import annotations

# Callback typing keeps snapshot services independent from the threaded job owner.
from typing import Any, Callable

# Cancellation is a normal user outcome, not a partial-success condition.
from gitdesk.errors import AppError


# Progress callbacks receive one complete JSON-safe snapshot rather than lossy percentage deltas.
ProgressCallback = Callable[[dict[str, Any]], None]

# Cancellation checks remain callable so synchronous tests and jobs can provide different owners.
CancellationCheck = Callable[[], bool]


# Raises at every bounded I/O checkpoint before more source or staging data is processed.
def ensure_backup_active(cancel_check: CancellationCheck | None) -> None:
    """Raise a stable cancellation error when the active Backup job was cancelled."""

    if cancel_check and cancel_check():
        raise AppError("Backup cancelled. No version was created.", "BACKUP_CANCELLED")


# SnapshotProgress owns exact phase-local byte and item counts reported to the transfer dialog.
class SnapshotProgress:
    """Publish factual calculating, copying, verifying, and finalizing progress."""

    # Starts with an indeterminate calculating phase because its total is not known before traversal.
    def __init__(self, callback: ProgressCallback | None = None) -> None:
        self.callback = callback
        self.phase = "preparing"
        self.current_path = ""
        self.bytes_done = 0
        self.bytes_total = 0
        self.items_done = 0
        self.items_total = 0
        self.emit()

    # Publishes one complete state so polling never has to reconstruct missed deltas.
    def emit(self) -> None:
        """Send the current progress state when a job callback is available."""

        if not self.callback:
            return
        self.callback({
            "phase": self.phase,
            "current_path": self.current_path,
            "bytes_done": self.bytes_done,
            "bytes_total": self.bytes_total,
            "items_done": self.items_done,
            "items_total": self.items_total,
        })

    # Resets phase-local counters when the transaction advances to measurable work.
    def begin_phase(self, phase: str, byte_total: int = 0, item_total: int = 0) -> None:
        """Begin one factual progress phase with bounded non-negative totals."""

        self.phase = phase
        self.current_path = ""
        self.bytes_done = 0
        self.bytes_total = max(0, int(byte_total))
        self.items_done = 0
        self.items_total = max(0, int(item_total))
        self.emit()

    # Records bytes read during manifest calculation or post-copy verification.
    def advance_read(self, display_path: str, byte_count: int = 0, item_complete: bool = False) -> None:
        """Record factual source or destination bytes read and completed entries."""

        self.current_path = display_path
        self.bytes_done += max(0, int(byte_count))
        if item_complete:
            self.items_done += 1
        self.emit()

    # Starts the determinate transfer phase from the completed selected manifest.
    def begin_copy(self, manifest: dict[str, Any]) -> None:
        """Begin copying with exact selected regular-file bytes and file/link item totals."""

        self.begin_phase("copying", manifest.get("total_bytes", 0), manifest.get("file_count", 0))

    # Records bytes physically written to the staging version and completed copied items.
    def advance_copy(self, display_path: str, byte_count: int = 0, item_complete: bool = False) -> None:
        """Record factual staging bytes written and completed entries."""

        self.current_path = display_path
        self.bytes_done += max(0, int(byte_count))
        if item_complete:
            self.items_done += 1
        self.emit()

    # Verification re-reads the staged copy after each regular file was hashed during its physical copy.
    def begin_verification(self, manifest: dict[str, Any]) -> None:
        """Begin verification with exact expected read bytes and file/link item totals."""

        self.begin_phase(
            "verifying",
            int(manifest.get("total_bytes", 0)),
            int(manifest.get("file_count", 0)),
        )

    # Finalization has no fake duration; completed measurable totals stay visible at 100 percent.
    def begin_finalizing(self) -> None:
        """Mark measurable work complete while metadata and the atomic rename finish."""

        self.phase = "finalizing"
        self.current_path = ""
        self.bytes_done = self.bytes_total
        self.items_done = self.items_total
        self.emit()
