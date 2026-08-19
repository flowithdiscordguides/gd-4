"""Bounded in-memory background jobs for progress-aware artifact synchronization."""

from __future__ import annotations

from secrets import token_urlsafe
from threading import Lock, Thread
from time import monotonic
from typing import Any, Callable

from gitdesk import syncchains
from gitdesk.errors import AppError, safe_unexpected_error


JOB_RETENTION_SECONDS = 15 * 60
JobProgress = Callable[[dict[str, Any]], None]
JobRunner = Callable[[JobProgress], dict[str, Any]]
SyncEdgeRunner = Callable[..., dict[str, Any]]


# SyncJobRegistry owns one active job per artifact edge and bounded terminal results for frontend polling.
class SyncJobRegistry:
    """Run artifact work off the WebUI callback while preserving terminal results and safe errors."""

    def __init__(self) -> None:
        self.lock = Lock()
        self.jobs: dict[str, dict[str, Any]] = {}
        self.active_keys: dict[str, str] = {}

    def _clean_locked(self, now: float) -> None:
        expired = [
            job_id for job_id, job in self.jobs.items()
            if job["status"] in {"succeeded", "failed"}
            and now - float(job.get("finished_at") or now) >= JOB_RETENTION_SECONDS
        ]
        for job_id in expired:
            self.jobs.pop(job_id, None)

    def start(self, key: str, runner: JobRunner) -> dict[str, Any]:
        """Start one daemon worker or return the matching active job without queuing a duplicate."""

        with self.lock:
            self._clean_locked(monotonic())
            active_id = self.active_keys.get(key)
            if active_id and active_id in self.jobs:
                return {"job_id": active_id, "reused": True}
            job_id = token_urlsafe(24)
            self.jobs[job_id] = {
                "status": "queued",
                "progress": {"phase": "queued", "message": "Waiting for artifact sync availability"},
                "result": None,
                "error": None,
                "finished_at": None,
            }
            self.active_keys[key] = job_id
        thread = Thread(target=self._run, args=(job_id, key, runner), daemon=True)
        with self.lock:
            self.jobs[job_id]["thread"] = thread
        thread.start()
        return {"job_id": job_id, "reused": False}

    def _report(self, job_id: str, update: dict[str, Any]) -> None:
        progress = {
            key: value for key, value in update.items()
            if key in {
                "phase", "message", "asset_index", "asset_count", "bytes_transferred", "bytes_total",
            }
            and isinstance(value, (str, int))
        }
        with self.lock:
            job = self.jobs.get(job_id)
            if job and job["status"] in {"queued", "running"}:
                job["status"] = "running"
                job["progress"] = progress

    def _run(self, job_id: str, key: str, runner: JobRunner) -> None:
        self._report(job_id, {"phase": "queued", "message": "Waiting for artifact sync availability"})
        try:
            result = runner(lambda update: self._report(job_id, update))
        except AppError as error:
            self._finish(job_id, key, "failed", error=error.to_payload())
        except Exception as error:
            self._finish(job_id, key, "failed", error=safe_unexpected_error(error))
        else:
            self._finish(job_id, key, "succeeded", result=result)

    def _finish(
        self,
        job_id: str,
        key: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job:
                return
            job["status"] = status
            job["result"] = result
            job["error"] = error
            job["finished_at"] = monotonic()
            if self.active_keys.get(key) == job_id:
                self.active_keys.pop(key, None)

    def status(self, job_id: str) -> dict[str, Any]:
        """Return one frontend-safe job snapshot without exposing its runner or native thread."""

        with self.lock:
            self._clean_locked(monotonic())
            job = self.jobs.get(job_id)
            if not job:
                raise AppError("That artifact synchronization is no longer available.", "SYNC_JOB_MISSING")
            return {
                "job_id": job_id,
                "status": job["status"],
                "progress": dict(job["progress"]),
                "result": job["result"],
                "error": job["error"],
            }


SYNC_JOB_REGISTRY = SyncJobRegistry()


# Starts only the configured artifact edge so filesystem mirrors keep their established direct response contract.
def start_sync_chain_job(controller: Any, payload: dict[str, Any], sync_runner: SyncEdgeRunner) -> dict[str, Any]:
    """Start one project-scoped artifact-only edge job and return its opaque identifier."""

    chain_id = str(payload.get("chain_id") or "").strip()
    edge = str(payload.get("edge") or "").strip()
    if not chain_id or edge not in syncchains.EDGE_NAMES[1:]:
        raise AppError("Background synchronization requires a repository stage edge.", "SYNC_JOB_EDGE_INVALID")
    settings = controller.settings_store.load()
    chain = syncchains.require_chain(settings, chain_id)
    if not syncchains.artifact_only_for_edge(chain, edge):
        raise AppError("Background synchronization requires Built artifacts only.", "SYNC_JOB_MODE_INVALID")
    expected_tag = str(payload.get("expected_release_tag") or "")

    def run(progress: JobProgress) -> dict[str, Any]:
        current = controller.settings_store.load()
        current_chain = syncchains.require_chain(current, chain_id)
        if not syncchains.artifact_only_for_edge(current_chain, edge):
            raise AppError("Built artifacts only changed before synchronization started.", "SYNC_JOB_MODE_CHANGED")
        return sync_runner(controller, current, chain_id, edge, "", expected_tag, progress)

    return SYNC_JOB_REGISTRY.start(f"{chain_id}\0{edge}", run)


# Resolves one opaque job id supplied by the same local WebUI that started the transfer.
def sync_chain_job_status(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the current or terminal artifact job state."""

    job_id = str(payload.get("job_id") or "").strip()
    if not job_id:
        raise AppError("An artifact synchronization id is required.", "SYNC_JOB_ID_INVALID")
    return SYNC_JOB_REGISTRY.status(job_id)
