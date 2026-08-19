"""Single-owner threaded Backup jobs with polling and an atomic cancellation boundary."""

from __future__ import annotations

# Locks, daemon workers, monotonic time, and opaque ids provide bounded in-process job ownership.
from threading import Lock, Thread
import time
from typing import Any, Callable
from uuid import uuid4

# Structured errors remain safe when a background worker reports failure through polling.
from gitdesk.errors import AppError, safe_unexpected_error


# A worker receives a complete-state progress callback and its cancellation gate.
BackupWorker = Callable[[Callable[[dict[str, Any]], None], "CancellationGate"], dict[str, Any]]


# CancellationGate prevents cancellation from racing the final atomic snapshot installation.
class CancellationGate:
    """Own a cancellation request until the worker seals its commit boundary."""

    # New jobs begin cancellable and unrequested.
    def __init__(self) -> None:
        self.lock = Lock()
        self.cancel_requested = False
        self.sealed = False

    # Requests cancellation only while cleanup can still guarantee no installed version.
    def request(self) -> bool:
        """Request cancellation and return whether the request was accepted."""

        with self.lock:
            if self.sealed:
                return False
            self.cancel_requested = True
            return True

    # Reports cancellation at bounded worker I/O checkpoints.
    def requested(self) -> bool:
        """Return whether cancellation was accepted before the commit boundary."""

        with self.lock:
            return self.cancel_requested

    # Atomically closes cancellation immediately before final snapshot installation.
    def seal(self) -> bool:
        """Seal the job and return False when cancellation won the boundary race."""

        with self.lock:
            if self.cancel_requested:
                return False
            self.sealed = True
            return True

    # Reports whether the transfer dialog should keep its Cancel action enabled.
    def cancellable(self) -> bool:
        """Return whether a new cancellation request can still be accepted."""

        with self.lock:
            return not self.sealed and not self.cancel_requested


# BackupJob stores only one transaction's bounded status, progress, result, and safe error payload.
class BackupJob:
    """Run one Backup transaction and expose JSON-safe polling state."""

    # Initializes immutable identity plus queued progress before the daemon worker starts.
    def __init__(self, worker: BackupWorker) -> None:
        self.id = uuid4().hex
        self.worker = worker
        self.lock = Lock()
        self.gate = CancellationGate()
        self.status = "queued"
        self.progress = {
            "phase": "preparing",
            "current_path": "",
            "bytes_done": 0,
            "bytes_total": 0,
            "items_done": 0,
            "items_total": 0,
        }
        self.result: dict[str, Any] | None = None
        self.skipped_paths: dict[str, str] = {}
        self.error: dict[str, Any] | None = None
        self.started_at = time.monotonic()

    # Starts one daemon thread so bridge status and cancellation requests remain independently dispatchable.
    def start(self) -> None:
        """Start this job's bounded worker thread."""

        Thread(target=self.run, name=f"gitdesk-backup-{self.id[:8]}", daemon=True).start()

    # Accepts complete progress snapshots and ignores late updates after a terminal result.
    def update_progress(self, progress: dict[str, Any]) -> None:
        """Replace current progress with one complete worker-owned state."""

        with self.lock:
            if self.status in {"completed", "cancelled", "failed"}:
                return
            self.progress = dict(progress)

    # Runs the transaction and converts every result into one stable terminal job state.
    def run(self) -> None:
        """Execute the worker and retain its result or safe failure."""

        with self.lock:
            self.status = "running"
        try:
            result = self.worker(self.update_progress, self.gate)
            skipped_paths = result.pop("_skipped_source_paths", {})
            with self.lock:
                self.result = result
                self.skipped_paths = dict(skipped_paths) if isinstance(skipped_paths, dict) else {}
                self.status = "completed"
        except AppError as error:
            with self.lock:
                self.error = error.to_payload()
                self.status = "cancelled" if error.code == "BACKUP_CANCELLED" else "failed"
        except Exception as error:
            with self.lock:
                self.error = safe_unexpected_error(error)
                self.status = "failed"

    # Returns an immutable polling payload with live elapsed time and cancellation availability.
    def payload(self) -> dict[str, Any]:
        """Return this job's current JSON-safe status."""

        with self.lock:
            return {
                "job_id": self.id,
                "status": self.status,
                "progress": dict(self.progress),
                "cancellable": self.status in {"queued", "running"} and self.gate.cancellable(),
                "elapsed_seconds": max(0.0, time.monotonic() - self.started_at),
                "result": self.result,
                "error": self.error,
            }

    # Resolves one captured source path without ever accepting an absolute location from frontend state.
    def skipped_path(self, item_id_value: Any) -> str:
        """Return one private skipped source path by opaque id."""

        item_id = str(item_id_value or "").strip()
        with self.lock:
            path = self.skipped_paths.get(item_id, "")
        if not path:
            raise AppError("That skipped backup item is no longer available.", "BACKUP_SKIPPED_ITEM_NOT_FOUND")
        return path


# BackupJobManager permits one active disk-intensive Backup transaction and bounds retained terminal jobs.
class BackupJobManager:
    """Start, poll, and cancel one active Backup job at a time."""

    # Initializes empty process-local ownership.
    def __init__(self) -> None:
        self.lock = Lock()
        self.jobs: dict[str, BackupJob] = {}

    # Removes completed history before starting the one allowed active transfer.
    def start(self, worker: BackupWorker) -> dict[str, Any]:
        """Start one Backup job or reject a competing active transaction."""

        with self.lock:
            active = next(
                (job for job in self.jobs.values() if job.status in {"queued", "running"}),
                None,
            )
            if active:
                raise AppError("Another backup is already in progress.", "BACKUP_JOB_ACTIVE")
            self.jobs = {
                job_id: job
                for job_id, job in self.jobs.items()
                if job.status in {"queued", "running"}
            }
            job = BackupJob(worker)
            self.jobs[job.id] = job
            job.start()
        return job.payload()

    # Resolves only opaque ids created by this process.
    def job(self, job_id_value: Any) -> BackupJob:
        """Return one known Backup job or raise a stable not-found error."""

        job_id = str(job_id_value or "").strip()
        with self.lock:
            job = self.jobs.get(job_id)
        if not job:
            raise AppError("That backup transfer is no longer available.", "BACKUP_JOB_NOT_FOUND")
        return job

    # Returns current progress without blocking the worker.
    def status(self, job_id_value: Any) -> dict[str, Any]:
        """Return one Backup job's current polling payload."""

        return self.job(job_id_value).payload()

    # Requests cancellation and returns the resulting authoritative job state.
    def cancel(self, job_id_value: Any) -> dict[str, Any]:
        """Request cancellation before atomic installation and return current state."""

        job = self.job(job_id_value)
        accepted = job.gate.request()
        payload = job.payload()
        payload["cancel_accepted"] = accepted
        return payload

    # Resolves one terminal job's server-owned skipped location for a native file-manager reveal.
    def skipped_path(self, job_id_value: Any, item_id_value: Any) -> str:
        """Return one skipped source path owned by a known completed job."""

        job = self.job(job_id_value)
        if job.status != "completed":
            raise AppError("That backup has not completed.", "BACKUP_JOB_NOT_COMPLETED")
        return job.skipped_path(item_id_value)


# One process-local manager matches the single desktop user's Backup workspace.
BACKUP_JOB_MANAGER = BackupJobManager()
