"""Validated Markdown-note storage for one selected Local Mode version."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
from typing import Any

from gitdesk.errors import AppError
from gitdesk import localfeatures
from gitdesk.localproject_records import clean_local_project_list


# Project notes use one visible direct-child Markdown filename.
NOTE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ ()'&+,-]{0,114}\.md$", re.IGNORECASE)

# The established Document Builder boundary also permits at most 10 MB of UTF-8 text.
MAX_NOTE_BYTES = 10 * 1024 * 1024

# Native bridge workers may save concurrently, so note create/replace operations share one lock.
LOCAL_NOTE_LOCK = RLock()


# Compares a saved path-like value with one canonical filesystem path.
def path_matches(candidate: Any, canonical_path: Path) -> bool:
    """Return whether candidate resolves to canonical_path."""

    try:
        return Path(str(candidate or "")).expanduser().resolve() == canonical_path
    except (OSError, RuntimeError):
        return False


# Resolves the complete saved-project, active-feature, and exact-version ownership chain.
def selected_version(settings: dict[str, Any], payload: dict[str, Any]) -> Path:
    """Return the exact selected version after validating its Local Mode ownership."""

    project_path = localfeatures.normalize_project_directory(
        payload.get("project_path") or settings.get("active_local_project"),
    )
    saved_project = next(
        (
            record
            for record in clean_local_project_list(settings.get("local_projects"))
            if path_matches(record["path"], project_path)
        ),
        None,
    )
    if not saved_project:
        raise AppError("Select a saved local project first.", "LOCAL_NOTE_PROJECT_NOT_FOUND")
    feature_path = localfeatures.normalize_feature_directory(
        project_path,
        payload.get("feature_path") or settings.get("active_local_feature"),
    )
    return localfeatures.validate_version_for_feature(
        project_path,
        feature_path,
        payload.get("version_path") or settings.get("active_local_version"),
    )


# Converts an Obsidian-style note title into one bounded Markdown filename.
def clean_note_name(value: Any) -> str:
    """Return a safe direct-child Markdown filename."""

    name = str(value or "").strip()
    if not name:
        raise AppError("Note name is required.", "LOCAL_NOTE_NAME_EMPTY")
    if not name.lower().endswith(".md"):
        name = f"{name}.md"
    if (
        name in {".", ".."}
        or name.startswith(".")
        or "/" in name
        or "\\" in name
        or not NOTE_NAME_PATTERN.fullmatch(name)
    ):
        raise AppError(
            "Use a visible Markdown filename without path separators.",
            "LOCAL_NOTE_NAME_INVALID",
        )
    return name


# Resolves one note as a direct version child and rejects symbolic-link targets.
def note_path(version_path: Path, name_value: Any, require_existing: bool) -> Path:
    """Return a safe note path directly inside version_path."""

    name = clean_note_name(name_value)
    lexical_path = version_path / name
    if lexical_path.is_symlink():
        raise AppError("Project notes cannot use symbolic links.", "LOCAL_NOTE_SYMLINK_REJECTED")
    path = lexical_path.resolve()
    if path.parent != version_path:
        raise AppError("Project note must stay inside the selected version.", "LOCAL_NOTE_PATH_INVALID")
    if require_existing and not path.is_file():
        raise AppError("The selected project note no longer exists.", "LOCAL_NOTE_NOT_FOUND")
    return path


# Hashes raw UTF-8 bytes so external edits can be detected before a replacement.
def content_revision(content: bytes) -> str:
    """Return the stable SHA-256 revision for note content."""

    return hashlib.sha256(content).hexdigest()


# Reads bounded UTF-8 content and rejects a file that changed into a symlink.
def read_note_file(path: Path) -> tuple[str, str]:
    """Return decoded note content and its content revision."""

    if path.is_symlink() or not path.is_file():
        raise AppError("The selected project note is invalid.", "LOCAL_NOTE_NOT_FOUND")
    try:
        if path.stat().st_size > MAX_NOTE_BYTES:
            raise AppError("Project notes cannot exceed 10 MB.", "LOCAL_NOTE_CONTENT_TOO_LARGE")
        content = path.read_bytes()
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AppError("Project notes must contain UTF-8 text.", "LOCAL_NOTE_ENCODING_INVALID") from error
    except OSError as error:
        raise AppError("Project note could not be read.", "LOCAL_NOTE_READ_FAILED") from error
    return text, content_revision(content)


# Validates and encodes note text without coercing non-string bridge values.
def encoded_note_content(value: Any) -> bytes:
    """Return bounded UTF-8 note bytes."""

    if not isinstance(value, str):
        raise AppError("Project note content must be plain text.", "LOCAL_NOTE_CONTENT_INVALID")
    content = value.encode("utf-8")
    if len(content) > MAX_NOTE_BYTES:
        raise AppError("Project notes cannot exceed 10 MB.", "LOCAL_NOTE_CONTENT_TOO_LARGE")
    return content


# Builds list metadata without exposing or preloading note contents.
def note_metadata(path: Path) -> dict[str, Any]:
    """Return safe display metadata for one regular Markdown note."""

    stat = path.stat()
    return {"name": path.name, "size": stat.st_size}


# Lists direct regular Markdown files in the exact selected version.
def notes_state(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Return selected-version identity and its direct Markdown note list."""

    version_path = selected_version(settings, payload)
    notes = [
        note_metadata(child)
        for child in version_path.iterdir()
        if not child.is_symlink() and child.is_file() and child.suffix.lower() == ".md"
    ]
    notes.sort(key=lambda item: item["name"].lower())
    return {
        "version_path": str(version_path),
        "version_name": version_path.name,
        "notes": notes,
    }


# Reads one exact direct-child note from the selected version.
def read_note(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Return one note's source text and revision."""

    version_path = selected_version(settings, payload)
    path = note_path(version_path, payload.get("name"), True)
    content, revision = read_note_file(path)
    return {
        **note_metadata(path),
        "content": content,
        "revision": revision,
    }


# Creates one empty or supplied note without replacing an existing project file.
def create_note(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Create a direct-child Markdown note exclusively and return its source."""

    version_path = selected_version(settings, payload)
    path = note_path(version_path, payload.get("name"), False)
    content = encoded_note_content(payload.get("content", ""))
    with LOCAL_NOTE_LOCK:
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(descriptor, "wb") as output_file:
                output_file.write(content)
                output_file.flush()
                os.fsync(output_file.fileno())
        except FileExistsError as error:
            raise AppError("A project note with that name already exists.", "LOCAL_NOTE_EXISTS") from error
        except OSError as error:
            raise AppError("Project note could not be created.", "LOCAL_NOTE_WRITE_FAILED") from error
    return read_note(settings, {**payload, "name": path.name})


# Atomically replaces one unchanged note and rejects stale frontend revisions.
def save_note(settings: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Save one note only when its expected revision still matches disk."""

    version_path = selected_version(settings, payload)
    path = note_path(version_path, payload.get("name"), True)
    expected_revision = str(payload.get("expected_revision") or "").strip()
    content = encoded_note_content(payload.get("content"))
    temporary_path: Path | None = None
    with LOCAL_NOTE_LOCK:
        _, current_revision = read_note_file(path)
        if not expected_revision or expected_revision != current_revision:
            raise AppError(
                "This note changed outside GitDesk. Reopen it before saving.",
                "LOCAL_NOTE_REVISION_CONFLICT",
            )
        try:
            descriptor, raw_path = tempfile.mkstemp(prefix=".gitdesk-note-", dir=version_path)
            temporary_path = Path(raw_path)
            with os.fdopen(descriptor, "wb") as output_file:
                output_file.write(content)
                output_file.flush()
                os.fsync(output_file.fileno())
            temporary_path.chmod(0o644)
            if path.is_symlink() or read_note_file(path)[1] != expected_revision:
                raise AppError(
                    "This note changed outside GitDesk. Reopen it before saving.",
                    "LOCAL_NOTE_REVISION_CONFLICT",
                )
            os.replace(temporary_path, path)
            temporary_path = None
        except AppError:
            raise
        except OSError as error:
            raise AppError("Project note could not be saved.", "LOCAL_NOTE_WRITE_FAILED") from error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
    return read_note(settings, {**payload, "name": path.name})
