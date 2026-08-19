"""Cross-platform native opening helpers for trusted local files and folders."""

from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import subprocess

from gitdesk.editor_preferences import clean_editor_preferences, editor_name
from gitdesk.errors import AppError


MAC_EDITOR_APPS = {
    "vscode": ("Visual Studio Code.app",),
    "vscodium": ("VSCodium.app",),
}
VSCODIUM_EXECUTABLE_NAMES = {"codium", "codium.exe", "vscodium", "vscodium.exe"}


# Resolves an existing filesystem path before it is handed to an operating-system launcher.
def existing_path(path_value: str, require_directory: bool = False) -> Path:
    """Return an existing resolved path, optionally requiring a directory."""

    cleaned_path = str(path_value or "").strip()
    if not cleaned_path:
        raise AppError("A local path is required.", "LOCAL_OPEN_PATH_EMPTY")
    path = Path(cleaned_path).expanduser().resolve()
    valid = path.is_dir() if require_directory else path.exists()
    if not valid:
        kind = "folder" if require_directory else "file or folder"
        raise AppError(f"The selected {kind} does not exist.", "LOCAL_OPEN_PATH_INVALID")
    return path


# Opens a directory in the host platform's normal graphical file manager.
def open_folder(path_value: str) -> dict[str, str]:
    """Open an existing folder in Finder, Explorer, or the Linux desktop file manager."""

    folder_path = existing_path(path_value, require_directory=True)
    system_name = platform.system()
    if system_name == "Darwin":
        subprocess.Popen(["open", str(folder_path)])
    elif system_name == "Windows":
        os.startfile(str(folder_path))
    else:
        subprocess.Popen(["xdg-open", str(folder_path)])
    return {"path": str(folder_path)}


# Opens a trusted existing file or folder through the operating system's default application.
def open_path(path_value: str) -> dict[str, str]:
    """Open an existing path with its platform-default application."""

    path = existing_path(path_value)
    system_name = platform.system()
    if system_name == "Darwin":
        subprocess.Popen(["open", str(path)])
    elif system_name == "Windows":
        os.startfile(str(path))
    else:
        subprocess.Popen(["xdg-open", str(path)])
    return {"path": str(path)}


# Reveals an existing file or folder in its containing native file manager for manual recovery work.
def reveal_path(path_value: str) -> dict[str, str]:
    """Reveal an existing path in Finder, Explorer, or its containing Linux folder."""

    path = existing_path(path_value)
    system_name = platform.system()
    if system_name == "Darwin":
        subprocess.Popen(["open", "-R", str(path)])
    elif system_name == "Windows":
        subprocess.Popen(["explorer", f"/select,{path}"])
    else:
        folder = path if path.is_dir() else path.parent
        subprocess.Popen(["xdg-open", str(folder)])
    return {"path": str(path)}


def mac_editor_bundle(editor: str) -> Path | None:
    """Return an installed macOS editor bundle from system or user Applications."""

    for app_name in MAC_EDITOR_APPS[editor]:
        for parent in (Path("/Applications"), Path.home() / "Applications"):
            bundle = parent / app_name
            if bundle.is_dir():
                return bundle
    return None


def valid_vscodium_executable(path_value: str) -> Path | None:
    """Return a resolved trusted VSCodium executable selected by the user."""

    try:
        path = Path(str(path_value or "").strip()).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
    executable = platform.system() == "Windows" or os.access(path, os.X_OK)
    if path.is_file() and executable and path.name.lower() in VSCODIUM_EXECUTABLE_NAMES:
        return path
    return None


def editor_status(preferences: dict[str, str] | None = None) -> dict[str, object]:
    """Return platform discovery and current editor availability for User settings."""

    cleaned = clean_editor_preferences(preferences)
    system_name = platform.system()
    vscode_path = mac_editor_bundle("vscode") if system_name == "Darwin" else shutil.which("code")
    if system_name == "Windows" and not vscode_path:
        vscode_path = shutil.which("code.cmd")
    vscodium_path = (
        mac_editor_bundle("vscodium")
        if system_name == "Darwin"
        else valid_vscodium_executable(cleaned["vscodium_path"])
    )
    return {
        "platform": system_name,
        "preferences": cleaned,
        "editors": {
            "vscode": {"name": "VS Code", "available": bool(vscode_path), "path": str(vscode_path or "")},
            "vscodium": {
                "name": "VSCodium",
                "available": bool(vscodium_path),
                "path": str(vscodium_path or ""),
            },
        },
    }


def editor_command(preferences: dict[str, str]) -> tuple[list[str], str]:
    """Return a non-shell launch prefix for the selected installed editor."""

    cleaned = clean_editor_preferences(preferences)
    editor = cleaned["editor"]
    name = editor_name(editor)
    if platform.system() == "Darwin":
        bundle = mac_editor_bundle(editor)
        if bundle:
            return ["open", "-a", str(bundle)], name
    elif editor == "vscode":
        command = shutil.which("code") or shutil.which("code.cmd")
        if command:
            return [command], name
    else:
        command = valid_vscodium_executable(cleaned["vscodium_path"])
        if command:
            return [str(command)], name
    raise AppError(f"{name} was not found on this system.", f"{editor.upper()}_NOT_FOUND")


def open_in_editor(path_value: str, preferences: dict[str, str] | None = None) -> dict[str, str]:
    """Open an existing file or folder in the selected validated code editor."""

    path = existing_path(path_value)
    command, name = editor_command(clean_editor_preferences(preferences))
    subprocess.Popen([*command, str(path)])
    return {"path": str(path), "editor": name}


def open_in_vscode(path_value: str) -> dict[str, str]:
    """Retain the legacy VS Code helper for callers that require the fixed editor."""

    return open_in_editor(path_value, {"editor": "vscode"})
