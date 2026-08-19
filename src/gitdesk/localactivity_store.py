"""Private persistence and filesystem change detection for Local Mode activity."""

from __future__ import annotations

# Standard-library tools provide timestamps, stable ids, JSON parsing, traversal, and paths.
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any

# GitDesk storage guarantees atomic owner-only writes, while version rules identify generated trees.
from gitdesk.errors import AppError
from gitdesk.localversions import PRUNED_TREE_NAMES
from gitdesk.storage import APP_STORAGE_LOCK, atomic_write_private_json


# Activity state uses the same owner-only privacy boundary as settings and token metadata.
ACTIVITY_DIRECTORY_MODE = 0o700
ACTIVITY_FILE_MODE = 0o600

# Bounded history and snapshots prevent long-lived projects from growing private state without limit.
MAX_STORED_EVENTS = 5000
MAX_FILES_PER_VERSION = 10000

# The version allows future migrations to reject incompatible state instead of misreading it.
ACTIVITY_STATE_VERSION = 1

# The private activity filename lives beside settings without becoming general configuration.
LOCAL_ACTIVITY_FILENAME = "local-activity.json"

# Finder metadata is not project work and must never create activity artifacts.
IGNORED_FILE_NAMES = {".DS_Store"}


# Returns the private local activity store associated with one SettingsStore path.
def activity_store(settings_path: Path) -> "LocalActivityStore":
    """Return the owner-only activity store beside settings_path."""

    return LocalActivityStore(settings_path.with_name(LOCAL_ACTIVITY_FILENAME))


# Returns a filesystem birth timestamp only where the operating system exposes creation semantics.
def birth_timestamp_ns(stat_result: os.stat_result) -> int:
    """Return a nanosecond creation timestamp or zero when the platform cannot provide one."""

    birth_seconds = getattr(stat_result, "st_birthtime", None)
    if birth_seconds is not None:
        return int(float(birth_seconds) * 1_000_000_000)
    # Windows defines ctime as creation time; Unix ctime is metadata-change time and is not equivalent.
    if os.name == "nt":
        return int(stat_result.st_ctime_ns)
    return 0


# Converts a nanosecond filesystem timestamp into the UTC format used by Project Hub events.
def timestamp_from_ns(timestamp_ns: int) -> str:
    """Return a Z-suffixed UTC timestamp for a positive nanosecond value."""

    timestamp = datetime.fromtimestamp(timestamp_ns / 1_000_000_000, timezone.utc).isoformat()
    return timestamp.replace("+00:00", "Z")


# Cleans one persisted file fingerprint without trusting private JSON contents.
def clean_fingerprint(value: Any) -> dict[str, int] | None:
    """Return a valid file fingerprint or None for malformed state."""

    if not isinstance(value, dict):
        return None
    try:
        modified_ns = max(0, int(value.get("modified_ns") or 0))
        size = max(0, int(value.get("size") or 0))
        birth_ns = max(0, int(value.get("birth_ns") or 0))
    except (TypeError, ValueError):
        return None
    return {"modified_ns": modified_ns, "size": size, "birth_ns": birth_ns}


# Cleans one detected file event so corrupt state cannot inject unexpected frontend fields.
def clean_file_event(value: Any) -> dict[str, str] | None:
    """Return a bounded local file event or None for malformed state."""

    if not isinstance(value, dict):
        return None
    event_id = str(value.get("id") or "").strip()
    kind = str(value.get("kind") or "").strip()
    occurred_at = str(value.get("occurred_at") or "").strip()
    if not event_id or kind not in {"file_added", "file_modified"} or not occurred_at:
        return None
    return {
        "id": event_id[:64],
        "kind": kind,
        "occurred_at": occurred_at[:40],
        "project_path": str(value.get("project_path") or "").strip(),
        "project_name": str(value.get("project_name") or "").strip()[:160],
        "feature_path": str(value.get("feature_path") or "").strip(),
        "feature_name": str(value.get("feature_name") or "").strip()[:160],
        "version_path": str(value.get("version_path") or "").strip(),
        "version_name": str(value.get("version_name") or "").strip()[:160],
        "file_path": str(value.get("file_path") or "").strip()[:500],
        "title": str(value.get("title") or "File activity").strip()[:200],
        "detail": str(value.get("detail") or "").strip()[:500],
    }


# Produces a stable event id so repeated scans cannot duplicate the same observed file state.
def file_event_id(kind: str, version_path: str, relative_path: str, fingerprint: dict[str, int]) -> str:
    """Return a stable id for one file state observed inside a version."""

    source = (
        f"{kind}:{version_path}:{relative_path}:"
        f"{fingerprint['modified_ns']}:{fingerprint['size']}"
    ).encode("utf-8")
    return hashlib.sha256(source).hexdigest()[:32]


# Builds the complete factual file event consumed by activity normalization.
def build_file_event(
    context: dict[str, Any],
    version: dict[str, Any],
    relative_path: str,
    fingerprint: dict[str, int],
    kind: str,
    timestamp_ns: int,
) -> dict[str, str]:
    """Return one added or modified file event with project hierarchy context."""

    action = "Added" if kind == "file_added" else "Edited"
    return {
        "id": file_event_id(kind, version["path"], relative_path, fingerprint),
        "kind": kind,
        "occurred_at": timestamp_from_ns(timestamp_ns),
        "project_path": context["project_path"],
        "project_name": context["project_name"],
        "feature_path": version["feature_path"],
        "feature_name": version["feature_name"],
        "version_path": version["path"],
        "version_name": version["name"],
        "file_path": relative_path,
        "title": f"{action} {Path(relative_path).name}",
        "detail": relative_path,
    }


# Scans one version without following symlinks or descending into dependencies and generated outputs.
def version_snapshot(version_path: Path) -> tuple[dict[str, dict[str, int]], list[str], bool]:
    """Return bounded file fingerprints, warnings, and whether the scan is incomplete."""

    snapshot: dict[str, dict[str, int]] = {}
    warnings = []
    incomplete = False

    # The error callback preserves partial factual results while making unreadable paths visible to the user.
    def note_walk_error(error: OSError) -> None:
        """Record an unreadable directory without aborting other known versions."""

        nonlocal incomplete
        incomplete = True
        warnings.append(f"Could not inspect local activity inside {version_path.name}: {error}.")

    for directory, directory_names, file_names in os.walk(version_path, topdown=True, onerror=note_walk_error):
        # Pruning happens before descent so dependencies and build output cannot become false work signals.
        directory_names[:] = sorted([
            name
            for name in directory_names
            if name not in PRUNED_TREE_NAMES and not (Path(directory) / name).is_symlink()
        ])
        for file_name in sorted(file_names):
            if file_name in IGNORED_FILE_NAMES:
                continue
            if len(snapshot) >= MAX_FILES_PER_VERSION:
                warnings.append(
                    f"Local activity scan reached {MAX_FILES_PER_VERSION} files in {version_path.name}."
                )
                return snapshot, warnings, True
            file_path = Path(directory) / file_name
            if file_path.is_symlink():
                continue
            try:
                file_stat = file_path.stat()
                relative_path = file_path.relative_to(version_path).as_posix()
            except (OSError, ValueError):
                incomplete = True
                warnings.append(f"Could not inspect {file_name} inside {version_path.name}.")
                continue
            snapshot[relative_path] = {
                "modified_ns": int(file_stat.st_mtime_ns),
                "size": int(file_stat.st_size),
                "birth_ns": birth_timestamp_ns(file_stat),
            }
    return snapshot, warnings, incomplete


# Rewrites one absolute path if it belongs to a renamed project or version folder.
def remap_path(path_value: str, old_root: Path, new_root: Path) -> str:
    """Return path_value under new_root when it previously belonged to old_root."""

    raw_path = str(path_value or "").strip()
    if not raw_path:
        return ""
    try:
        relative_path = Path(raw_path).expanduser().resolve().relative_to(old_root)
    except (OSError, ValueError):
        return raw_path
    return str((new_root / relative_path).resolve())


# Owns private local activity state independently from general application preferences.
class LocalActivityStore:
    """Persist file fingerprints and detected edit history in an owner-only JSON file."""

    # Keeps the storage path explicit so tests and packaged settings use the same implementation.
    def __init__(self, path: Path) -> None:
        """Store activity state at path without writing until a scan or remap occurs."""

        self.path = path

    # Loads and sanitizes activity state, rejecting corruption instead of silently losing history.
    def load(self) -> dict[str, Any]:
        """Return clean events and version snapshots from the private activity file."""

        if not self.path.exists():
            return {"version": ACTIVITY_STATE_VERSION, "events": [], "files": {}}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise AppError("Local activity history could not be read.", "LOCAL_ACTIVITY_READ_FAILED") from error
        if not isinstance(loaded, dict) or loaded.get("version") != ACTIVITY_STATE_VERSION:
            raise AppError("Local activity history uses an unsupported format.", "LOCAL_ACTIVITY_FORMAT_INVALID")

        events = []
        raw_events = loaded.get("events") if isinstance(loaded.get("events"), list) else []
        for value in raw_events[:MAX_STORED_EVENTS]:
            event = clean_file_event(value)
            if event:
                events.append(event)
        files = {}
        raw_files = loaded.get("files") if isinstance(loaded.get("files"), dict) else {}
        for version_path, raw_snapshot in raw_files.items():
            if not isinstance(raw_snapshot, dict):
                continue
            snapshot = {}
            for relative_path, raw_fingerprint in raw_snapshot.items():
                if len(snapshot) >= MAX_FILES_PER_VERSION:
                    break
                fingerprint = clean_fingerprint(raw_fingerprint)
                if fingerprint and str(relative_path or "").strip():
                    snapshot[str(relative_path)] = fingerprint
            files[str(version_path)] = snapshot
        return {"version": ACTIVITY_STATE_VERSION, "events": events[:MAX_STORED_EVENTS], "files": files}

    # Saves complete state atomically with owner-only permissions.
    def save(self, state: dict[str, Any]) -> None:
        """Persist clean bounded activity state without exposing local paths to other users."""

        atomic_write_private_json(
            self.path,
            state,
            ACTIVITY_DIRECTORY_MODE,
            ACTIVITY_FILE_MODE,
        )

    # Removes the scan baseline for a version while preserving its factual historical events.
    def remove_version_snapshot(self, version_path: str) -> dict[str, dict[str, int]] | None:
        """Delete and return one version snapshot from private activity metadata."""

        with APP_STORAGE_LOCK:
            if not self.path.exists():
                return None
            state = self.load()
            snapshot = state["files"].pop(version_path, None)
            if snapshot is not None:
                self.save(state)
            return snapshot

    # Restores a scan baseline when a later physical-version deletion step fails.
    def restore_version_snapshot(self, version_path: str, snapshot: dict[str, Any] | None) -> None:
        """Restore a previously removed version snapshot without changing historical events."""

        if snapshot is None:
            return
        with APP_STORAGE_LOCK:
            state = self.load()
            state["files"][version_path] = snapshot
            self.save(state)

    # Detects new and modified files relative to the previous version snapshots.
    def scan(self, contexts: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[str]]:
        """Update fingerprints and return complete detected file history plus scan warnings."""

        with APP_STORAGE_LOCK:
            return self.scan_locked(contexts)

    # Performs one scan while the shared private-storage transaction lock is held.
    def scan_locked(self, contexts: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[str]]:
        """Compare and persist version snapshots without losing concurrent activity updates."""

        creating_baseline = not self.path.exists()
        state = self.load()
        previous_files = state["files"]
        next_files = {}
        detected_events = []
        warnings = []
        if creating_baseline and any(context["versions"] for context in contexts):
            warnings.append("Local file activity was baselined; subsequent additions and edits will be tracked.")
        for context in contexts:
            for version in context["versions"]:
                version_path = Path(version["path"])
                snapshot, scan_warnings, incomplete = version_snapshot(version_path)
                warnings.extend(scan_warnings)
                previous_snapshot = previous_files.get(version["path"])
                if incomplete:
                    if previous_snapshot is not None:
                        next_files[version["path"]] = previous_snapshot
                    continue
                # A previously unseen version is baselined so copied files cannot masquerade as fresh edits.
                if previous_snapshot is not None:
                    detected_events.extend(
                        self.changed_files(context, version, previous_snapshot, snapshot)
                    )
                next_files[version["path"]] = snapshot

        event_map = {event["id"]: event for event in state["events"]}
        for event in detected_events:
            event_map[event["id"]] = event
        events = sorted(event_map.values(), key=lambda event: event["occurred_at"], reverse=True)
        self.save({
            "version": ACTIVITY_STATE_VERSION,
            "events": events[:MAX_STORED_EVENTS],
            "files": next_files,
        })
        return events[:MAX_STORED_EVENTS], sorted(set(warnings))

    # Compares a known version snapshot without treating unchanged copied files as new edits.
    def changed_files(
        self,
        context: dict[str, Any],
        version: dict[str, Any],
        previous: dict[str, dict[str, int]],
        current: dict[str, dict[str, int]],
    ) -> list[dict[str, str]]:
        """Return file-added and file-modified events observed since the previous scan."""

        events = []
        for relative_path, fingerprint in current.items():
            old_fingerprint = previous.get(relative_path)
            if old_fingerprint is None:
                occurred_ns = fingerprint["birth_ns"] or fingerprint["modified_ns"]
                kind = "file_added"
            elif (
                fingerprint["modified_ns"] != old_fingerprint["modified_ns"]
                or fingerprint["size"] != old_fingerprint["size"]
            ):
                occurred_ns = fingerprint["modified_ns"]
                kind = "file_modified"
            else:
                continue
            events.append(build_file_event(context, version, relative_path, fingerprint, kind, occurred_ns))
        return events

    # Remaps stored paths after an authorized Local Mode folder rename.
    def remap_paths(self, old_path: Path, new_path: Path) -> None:
        """Rewrite event and snapshot ownership after old_path moves to new_path."""

        with APP_STORAGE_LOCK:
            self.remap_paths_locked(old_path, new_path)

    # Performs one path remap while the shared private-storage transaction lock is held.
    def remap_paths_locked(self, old_path: Path, new_path: Path) -> None:
        """Rewrite complete activity state without racing a simultaneous filesystem scan."""

        old_root = old_path.expanduser().resolve()
        new_root = new_path.expanduser().resolve()
        state = self.load()
        for event in state["events"]:
            for field in ("project_path", "feature_path", "version_path"):
                event[field] = remap_path(event[field], old_root, new_root)
        remapped_files = {
            remap_path(version_path, old_root, new_root): snapshot
            for version_path, snapshot in state["files"].items()
        }
        self.save({**state, "files": remapped_files})
