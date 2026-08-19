"""Physical document, numbered-folder, and numbered-file operations for Document Builder."""

from __future__ import annotations

import os
from pathlib import Path
import re
import tempfile
from threading import RLock
from typing import Any

from gitdesk.errors import AppError
from gitdesk.reposettings import clean_category_name


# User-facing names become one path component, so separators and hidden/control-like names are rejected.
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ ()'&+-]{0,119}$")

# Managed child names begin with a decimal sequence and a space, such as 01 Research or 02 notes.md.
NUMBERED_NAME_PATTERN = re.compile(r"^(?P<number>0*[1-9][0-9]*)\s+(?P<label>.+)$")

# Pasted text is bounded so one frontend request cannot exhaust the desktop process's memory or storage.
MAX_TEXT_BYTES = 10 * 1024 * 1024

# Recursive state scans are bounded so an unexpectedly deep external tree cannot exhaust the WebView payload.
MAX_FOLDER_DEPTH = 32

# File creation is serialized so simultaneous bridge requests cannot claim the same sequence number.
DOCUMENT_FILESYSTEM_LOCK = RLock()


# Removes an already-entered sequence prefix before the app assigns the authoritative next number.
def unnumbered_label(value: Any) -> str:
    """Return a trimmed user label without an optional leading numeric sequence."""

    label = str(value or "").strip()
    match = NUMBERED_NAME_PATTERN.match(label)
    return match.group("label").strip() if match else label


# Validates a single document, folder, or file name without allowing path traversal.
def clean_name(value: Any, kind: str) -> str:
    """Return a safe single path-component label for the requested object kind."""

    name = unnumbered_label(value)
    if not name or name in {".", ".."}:
        raise AppError(f"{kind.title()} name is required.", f"DOCUMENT_{kind.upper()}_NAME_EMPTY")
    if "/" in name or "\\" in name or name.startswith(".") or not NAME_PATTERN.fullmatch(name):
        raise AppError(
            f"{kind.title()} name contains invalid characters.",
            f"DOCUMENT_{kind.upper()}_NAME_INVALID",
        )
    return name


# Sanitizes a saved registry record without requiring disconnected folders to be mounted.
def clean_document_record(value: Any) -> dict[str, str] | None:
    """Return safe document metadata, or None when a stored record is malformed."""

    if not isinstance(value, dict):
        return None
    path = str(value.get("path") or "").strip()
    if not path:
        return None
    try:
        category = clean_category_name(value.get("category"))
    except AppError:
        category = ""
    return {
        "path": path,
        "name": str(value.get("name") or Path(path).name).strip() or Path(path).name,
        "category": category,
    }


# De-duplicates registry records by path while preserving deterministic name ordering.
def clean_document_records(value: Any) -> list[dict[str, str]]:
    """Return a sorted list of safe saved document records."""

    if not isinstance(value, list):
        return []
    records = []
    seen_paths = set()
    for raw_record in value:
        record = clean_document_record(raw_record)
        if record and record["path"] not in seen_paths:
            records.append(record)
            seen_paths.add(record["path"])
    return sorted(records, key=lambda item: item["name"].lower())


# Resolves an existing normal directory while rejecting symlink roots from the managed hierarchy.
def existing_directory(path_value: Any, kind: str) -> Path:
    """Return an existing non-symlink directory for a document hierarchy operation."""

    raw_path = str(path_value or "").strip()
    if not raw_path:
        raise AppError(f"{kind.title()} path is required.", f"DOCUMENT_{kind.upper()}_PATH_EMPTY")
    source_path = Path(raw_path).expanduser()
    if source_path.is_symlink():
        raise AppError(f"{kind.title()} path cannot be a symbolic link.", "DOCUMENT_SYMLINK_REJECTED")
    path = source_path.resolve()
    if not path.is_dir():
        raise AppError(f"{kind.title()} path must be an existing folder.", f"DOCUMENT_{kind.upper()}_PATH_INVALID")
    return path


# Confirms that an existing child is directly owned by its expected parent and is not a symbolic link.
def direct_child(parent: Path, path_value: Any, kind: str, require_directory: bool) -> Path:
    """Return a validated direct child file or folder inside parent."""

    raw_path = str(path_value or "").strip()
    source_path = Path(raw_path).expanduser() if raw_path else Path()
    if not raw_path or source_path.is_symlink():
        raise AppError(f"Selected {kind} is invalid.", f"DOCUMENT_{kind.upper()}_PATH_INVALID")
    path = source_path.resolve()
    valid_type = path.is_dir() if require_directory else path.is_file()
    if path.parent != parent or not valid_type:
        raise AppError(f"Selected {kind} must belong to its active parent.", f"DOCUMENT_{kind.upper()}_PATH_INVALID")
    return path


# Validates any nested folder while rejecting traversal and symbolic links at every hierarchy level.
def descendant_folder(document: Path, path_value: Any) -> Path:
    """Return an existing non-symlink folder contained anywhere below document."""

    raw_path = str(path_value or "").strip()
    if not raw_path:
        raise AppError("Selected folder is invalid.", "DOCUMENT_FOLDER_PATH_INVALID")
    lexical_path = Path(os.path.abspath(Path(raw_path).expanduser()))
    try:
        relative_path = lexical_path.relative_to(document)
    except ValueError as error:
        raise AppError(
            "Selected folder must belong to the active document.",
            "DOCUMENT_FOLDER_PATH_INVALID",
        ) from error
    if not relative_path.parts or relative_path == Path("."):
        raise AppError("Select a folder below the document root.", "DOCUMENT_FOLDER_PATH_INVALID")
    current_path = document
    for part in relative_path.parts:
        current_path = current_path / part
        if current_path.is_symlink():
            raise AppError("Document folders cannot use symbolic links.", "DOCUMENT_SYMLINK_REJECTED")
    resolved_path = lexical_path.resolve()
    if resolved_path.parent == resolved_path or not resolved_path.is_dir():
        raise AppError("Selected folder is invalid.", "DOCUMENT_FOLDER_PATH_INVALID")
    try:
        resolved_path.relative_to(document)
    except ValueError as error:
        raise AppError(
            "Selected folder must stay inside the active document.",
            "DOCUMENT_FOLDER_PATH_INVALID",
        ) from error
    return resolved_path


# Returns the sequence encoded in a managed name, or zero for externally created unnumbered entries.
def sequence_number(name: str) -> int:
    """Return the numeric prefix from a managed folder or file name."""

    match = NUMBERED_NAME_PATTERN.match(name)
    return int(match.group("number")) if match else 0


# Sorts managed entries numerically before any externally created unnumbered entries.
def numbered_sort_key(path: Path) -> tuple[int, int, str]:
    """Return the stable display order for a managed child path."""

    number = sequence_number(path.name)
    return (0 if number else 1, number, path.name.lower())


# Finds the next monotonic sequence without reusing gaps left by externally removed entries.
def next_number(parent: Path, want_directory: bool) -> int:
    """Return one greater than the highest numbered child of the requested type."""

    numbers = []
    for child in parent.iterdir():
        matching_type = child.is_dir() if want_directory else child.is_file()
        if not child.is_symlink() and matching_type:
            number = sequence_number(child.name)
            if number:
                numbers.append(number)
    return max(numbers or [0]) + 1


# Formats a sequence with at least two digits while continuing naturally beyond 99 entries.
def numbered_name(number: int, label: str) -> str:
    """Return a managed child name containing a padded numeric prefix."""

    width = max(2, len(str(number)))
    return f"{number:0{width}d} {label}"


# Builds a frontend payload for one physical file without reading its potentially large contents.
def file_payload(path: Path) -> dict[str, Any]:
    """Return display metadata for a document file."""

    return {"name": path.name, "number": sequence_number(path.name), "path": str(path.resolve())}


# Builds a frontend payload for one numbered folder and the regular files directly inside it.
def folder_payload(path: Path, depth: int = 0) -> dict[str, Any]:
    """Return recursive display metadata for a document folder, nested folders, and direct files."""

    files = [child for child in path.iterdir() if child.is_file() and not child.is_symlink()]
    folders = []
    if depth < MAX_FOLDER_DEPTH:
        child_folders = [child for child in path.iterdir() if child.is_dir() and not child.is_symlink()]
        folders = [folder_payload(child, depth + 1) for child in sorted(child_folders, key=numbered_sort_key)]
    return {
        "name": path.name,
        "number": sequence_number(path.name),
        "path": str(path.resolve()),
        "depth": depth,
        "files": [file_payload(child) for child in sorted(files, key=numbered_sort_key)],
        "folders": folders,
        "truncated": depth >= MAX_FOLDER_DEPTH,
    }


# Flattens recursive folder payloads for selection lookup while preserving display order.
def flatten_folders(folders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return every recursive folder payload in parent-before-child order."""

    flattened = []
    for folder in folders:
        flattened.append(folder)
        flattened.extend(flatten_folders(folder.get("folders") or []))
    return flattened


# Scans one registered document root into the nested state consumed by the frontend.
def document_payload(record: dict[str, str]) -> dict[str, Any]:
    """Return one registry record enriched with current physical folders and files."""

    source_path = Path(record["path"]).expanduser()
    exists = source_path.is_dir() and not source_path.is_symlink()
    folders = []
    if exists:
        document_path = source_path.resolve()
        children = [child for child in document_path.iterdir() if child.is_dir() and not child.is_symlink()]
        folders = [folder_payload(child) for child in sorted(children, key=numbered_sort_key)]
    return {**record, "exists": exists, "folders": folders}


# Produces registry state enriched from disk without trusting stale active child paths.
def documents_state(registry: dict[str, Any]) -> dict[str, Any]:
    """Return all document records and valid active hierarchy selections."""

    documents = [document_payload(record) for record in clean_document_records(registry.get("documents"))]
    active_document = str(registry.get("active_document") or "")
    document = next((item for item in documents if item["path"] == active_document), None)
    active_folder = str(registry.get("active_folder") or "")
    folders = flatten_folders((document or {}).get("folders", []))
    folder = next((item for item in folders if item["path"] == active_folder), None)
    active_file = str(registry.get("active_file") or "")
    file_exists = any(item["path"] == active_file for item in (folder or {}).get("files", []))
    return {
        "documents": documents,
        "categories": list(registry.get("categories") or []),
        "active_document": active_document if document else "",
        "active_folder": active_folder if folder else "",
        "active_file": active_file if file_exists else "",
    }


# Creates a registered document root inside a user-selected existing parent directory.
def create_document(parent_value: Any, name_value: Any) -> dict[str, str]:
    """Create an empty physical document root and return its registry record."""

    parent = existing_directory(parent_value, "parent")
    name = clean_name(name_value, "document")
    path = (parent / name).resolve()
    if path.parent != parent:
        raise AppError("Document must stay inside its selected parent.", "DOCUMENT_PATH_INVALID")
    if path.exists():
        raise AppError("A document with that name already exists.", "DOCUMENT_EXISTS")
    path.mkdir()
    return {"path": str(path), "name": name, "category": ""}


# Renames a document root and returns both paths for registry selection remapping.
def rename_document(path_value: Any, name_value: Any) -> dict[str, str]:
    """Rename an existing document root without moving it to another parent."""

    source = existing_directory(path_value, "document")
    target = (source.parent / clean_name(name_value, "document")).resolve()
    if target == source:
        return {"source": str(source), "target": str(target), "name": target.name}
    if target.exists():
        raise AppError("A document with that name already exists.", "DOCUMENT_EXISTS")
    source.rename(target)
    return {"source": str(source), "target": str(target), "name": target.name}


# Creates the next numbered child folder within the selected registered document.
def create_folder(document_value: Any, parent_value: Any, name_value: Any) -> dict[str, Any]:
    """Create a numbered root or nested folder and return its empty payload."""

    document = existing_directory(document_value, "document")
    raw_parent = str(parent_value or "").strip()
    parent = document if not raw_parent or raw_parent == str(document) else descendant_folder(document, raw_parent)
    label = clean_name(name_value, "folder")
    parent_depth = len(parent.relative_to(document).parts)
    if parent_depth > MAX_FOLDER_DEPTH:
        raise AppError("Document folders cannot be nested more than 33 levels.", "DOCUMENT_FOLDER_DEPTH_EXCEEDED")
    with DOCUMENT_FILESYSTEM_LOCK:
        path = parent / numbered_name(next_number(parent, True), label)
        path.mkdir()
    depth = len(path.relative_to(document).parents) - 1
    return folder_payload(path, depth)


# Writes a new numbered UTF-8 file atomically without replacing any existing external or managed file.
def create_file(document_value: Any, folder_value: Any, name_value: Any, content: Any) -> dict[str, Any]:
    """Create the next numbered file from pasted text and return its payload."""

    if not isinstance(content, str):
        raise AppError("Document text must be plain text.", "DOCUMENT_FILE_CONTENT_INVALID")
    encoded_content = content.encode("utf-8")
    if len(encoded_content) > MAX_TEXT_BYTES:
        raise AppError("Document text cannot exceed 10 MB.", "DOCUMENT_FILE_CONTENT_TOO_LARGE")
    document = existing_directory(document_value, "document")
    folder = descendant_folder(document, folder_value)
    label = clean_name(name_value, "file")
    with DOCUMENT_FILESYSTEM_LOCK:
        path = folder / numbered_name(next_number(folder, False), label)
        temporary_path: Path | None = None
        try:
            descriptor, raw_path = tempfile.mkstemp(prefix=".document-builder-", dir=folder)
            temporary_path = Path(raw_path)
            with os.fdopen(descriptor, "wb") as output_file:
                output_file.write(encoded_content)
                output_file.flush()
                os.fsync(output_file.fileno())
            temporary_path.chmod(0o644)
            os.link(temporary_path, path)
        except FileExistsError as error:
            raise AppError("The next numbered document file already exists.", "DOCUMENT_FILE_EXISTS") from error
        except OSError as error:
            raise AppError("Document file could not be saved.", "DOCUMENT_FILE_WRITE_FAILED") from error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    # The numbered destination is complete; a hidden temporary cleanup failure must not hide success.
                    pass
    return file_payload(path)


# Validates an active document folder for native opening actions.
def selected_document(path_value: Any) -> Path:
    """Return the selected existing document root."""

    return existing_directory(path_value, "document")


# Validates an active file against both its selected folder and registered document root.
def selected_file(document_value: Any, folder_value: Any, file_value: Any) -> Path:
    """Return a selected file after validating the complete owning hierarchy."""

    document = existing_directory(document_value, "document")
    folder = descendant_folder(document, folder_value)
    return direct_child(folder, file_value, "file", False)
