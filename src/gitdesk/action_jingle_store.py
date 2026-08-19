"""Validated audio paths and owner-only persistence for Repo Mode Actions jingles."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from gitdesk.errors import AppError
from gitdesk.reposettings_recovery import invalid_json_backup_path, load_recoverable_json
from gitdesk.reposettings_recovery import mark_backup_recovered
from gitdesk.storage import APP_STORAGE_LOCK, app_config_path, atomic_write_private_bytes
from gitdesk.storage import atomic_write_private_json


ACTION_JINGLE_SCHEMA_VERSION = 1
ACTION_JINGLE_KINDS = ("success", "failure")
MAX_ACTION_JINGLE_BYTES = 10 * 1024 * 1024
MAX_ACTION_JINGLE_PATH_CHARS = 4096
ACTION_JINGLE_DIRECTORY_MODE = 0o700
ACTION_JINGLE_FILE_MODE = 0o600

# Common desktop audio formats are signature-checked here and decoder-checked by Web Audio at playback.
ACTION_JINGLE_MIME_TYPES = {
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}


def clean_jingle_kind(value: Any) -> str:
    """Return one supported jingle kind or raise a structured request error."""

    kind = str(value or "").strip().lower()
    if kind not in ACTION_JINGLE_KINDS:
        raise AppError("Choose the success or failure jingle.", "ACTION_JINGLE_KIND_INVALID")
    return kind


def clean_registry(value: Any) -> dict[str, Any]:
    """Return a complete versioned registry without resolving stored external paths."""

    source = value if isinstance(value, dict) else {}
    return {
        "schema_version": ACTION_JINGLE_SCHEMA_VERSION,
        "success_path": str(source.get("success_path") or "").strip()[
            :MAX_ACTION_JINGLE_PATH_CHARS
        ],
        "failure_path": str(source.get("failure_path") or "").strip()[
            :MAX_ACTION_JINGLE_PATH_CHARS
        ],
    }


def audio_signature_matches(suffix: str, content: bytes) -> bool:
    """Return whether a bounded audio header matches its selected extension."""

    if suffix == ".aac":
        return len(content) >= 2 and content[0] == 0xFF and content[1] & 0xF6 == 0xF0
    if suffix == ".flac":
        return content.startswith(b"fLaC")
    if suffix == ".m4a":
        return len(content) >= 12 and content[4:8] == b"ftyp"
    if suffix == ".mp3":
        return content.startswith(b"ID3") or (
            len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0
        )
    if suffix == ".ogg":
        return content.startswith(b"OggS") and any(
            marker in content for marker in (b"vorbis", b"OpusHead", b"FLAC")
        )
    if suffix == ".wav":
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WAVE"
    return False


def validated_audio_file(path_value: Any, read_content: bool = False) -> tuple[Path, str, bytes]:
    """Return a regular bounded audio file, MIME type, and either its header or complete bytes."""

    raw_path = str(path_value or "").strip()
    if not raw_path:
        raise AppError("Choose an audio file.", "ACTION_JINGLE_PATH_EMPTY")
    if len(raw_path) > MAX_ACTION_JINGLE_PATH_CHARS:
        raise AppError("The selected jingle path is too long.", "ACTION_JINGLE_PATH_TOO_LONG")
    try:
        candidate = Path(raw_path).expanduser()
        if candidate.is_symlink():
            raise AppError("Jingle files cannot be symbolic links.", "ACTION_JINGLE_SYMLINK")
        path = candidate.resolve()
        stat = path.stat()
    except AppError:
        raise
    except (OSError, RuntimeError) as error:
        raise AppError("The selected jingle file is unavailable.", "ACTION_JINGLE_MISSING") from error
    if not path.is_file():
        raise AppError("The selected jingle file is unavailable.", "ACTION_JINGLE_MISSING")
    if len(str(path)) > MAX_ACTION_JINGLE_PATH_CHARS:
        raise AppError("The selected jingle path is too long.", "ACTION_JINGLE_PATH_TOO_LONG")
    suffix = path.suffix.lower()
    if suffix not in ACTION_JINGLE_MIME_TYPES:
        raise AppError(
            "Choose an AAC, FLAC, M4A, MP3, OGG, or WAV audio file.",
            "ACTION_JINGLE_TYPE_INVALID",
        )
    if stat.st_size <= 0 or stat.st_size > MAX_ACTION_JINGLE_BYTES:
        raise AppError("Jingle files must be between 1 byte and 10 MB.", "ACTION_JINGLE_SIZE_INVALID")
    try:
        with path.open("rb") as audio_file:
            content = audio_file.read(MAX_ACTION_JINGLE_BYTES + 1 if read_content else 64)
    except OSError as error:
        raise AppError("The selected jingle file could not be read.", "ACTION_JINGLE_READ_FAILED") from error
    if len(content) > MAX_ACTION_JINGLE_BYTES:
        raise AppError("Jingle files must be 10 MB or smaller.", "ACTION_JINGLE_SIZE_INVALID")
    if not audio_signature_matches(suffix, content):
        raise AppError("The selected audio content is invalid.", "ACTION_JINGLE_CONTENT_INVALID")
    return path, ACTION_JINGLE_MIME_TYPES[suffix], content


class ActionJingleStore:
    """Persist success and failure audio paths beside GitDesk's other private JSON files."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path or app_config_path() / "action-jingles.json"

    def defaults(self) -> dict[str, Any]:
        """Return fresh built-in-jingle settings without creating the registry."""

        return clean_registry({})

    def preserve_invalid_json(self) -> Path:
        """Return a private backup containing unreadable jingle registry bytes."""

        backup_path = invalid_json_backup_path(self.config_path)
        try:
            atomic_write_private_bytes(
                backup_path,
                self.config_path.read_bytes(),
                ACTION_JINGLE_DIRECTORY_MODE,
                ACTION_JINGLE_FILE_MODE,
            )
        except OSError as error:
            raise AppError(
                "Jingle settings could not be preserved.",
                "ACTION_JINGLE_INVALID_JSON",
            ) from error
        return backup_path

    def load(self) -> dict[str, Any]:
        """Return sanitized jingle settings, recovering malformed JSON before replacement."""

        with APP_STORAGE_LOCK:
            if not self.config_path.exists():
                return self.defaults()
            try:
                raw_registry = json.loads(self.config_path.read_text(encoding="utf-8"))
            except OSError as error:
                raise AppError("Unable to read jingle settings.", "ACTION_JINGLE_READ_FAILED") from error
            except json.JSONDecodeError:
                backup_path = self.preserve_invalid_json()
                registry = clean_registry(load_recoverable_json(backup_path))
                self.write(registry)
                mark_backup_recovered(backup_path)
                return registry
            registry = clean_registry(raw_registry)
            if registry != raw_registry:
                self.write(registry)
            return registry

    def write(self, registry: dict[str, Any]) -> None:
        """Persist complete sanitized jingle settings atomically with owner-only permissions."""

        try:
            atomic_write_private_json(
                self.config_path,
                clean_registry(registry),
                ACTION_JINGLE_DIRECTORY_MODE,
                ACTION_JINGLE_FILE_MODE,
            )
        except OSError as error:
            raise AppError("Unable to save jingle settings.", "ACTION_JINGLE_WRITE_FAILED") from error

    def replace(self, kind_value: Any, path_value: Any) -> dict[str, Any]:
        """Validate and persist one selected success or failure audio path."""

        kind = clean_jingle_kind(kind_value)
        path, _, _ = validated_audio_file(path_value)
        with APP_STORAGE_LOCK:
            registry = self.load()
            registry[f"{kind}_path"] = str(path)
            self.write(registry)
            return self.load()

    def public_settings(self, registry: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return basename-only availability state for the Settings interface."""

        saved = clean_registry(registry) if registry is not None else self.load()
        result = {}
        for kind in ACTION_JINGLE_KINDS:
            path_value = saved[f"{kind}_path"]
            available = False
            if path_value:
                try:
                    validated_audio_file(path_value)
                    available = True
                except AppError:
                    available = False
            result[kind] = {
                "custom": bool(path_value),
                "available": available,
                "file_name": Path(path_value).name if path_value else "",
            }
        return result

    def audio_payload(self, kind_value: Any) -> dict[str, Any]:
        """Return a bounded data URL for one configured jingle without exposing its saved path."""

        kind = clean_jingle_kind(kind_value)
        path_value = self.load()[f"{kind}_path"]
        if not path_value:
            return {"custom": False, "data_url": "", "file_name": ""}
        path, mime_type, content = validated_audio_file(path_value, read_content=True)
        encoded = base64.b64encode(content).decode("ascii")
        return {
            "custom": True,
            "data_url": f"data:{mime_type};base64,{encoded}",
            "file_name": path.name,
        }
