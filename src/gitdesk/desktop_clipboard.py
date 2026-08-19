"""Read desktop clipboard content and write native file references outside the embedded WebView."""

from __future__ import annotations

# Standard-library platform adapters avoid browser clipboard permissions and optional GUI dependencies.
import ctypes
import json
import os
import platform
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import time
from typing import Any

from gitdesk.errors import AppError


MAX_CLIPBOARD_TEXT_CHARACTERS = 4_000_000
MAX_CLIPBOARD_FILE_URLS = 512
CLIPBOARD_COMMAND_TIMEOUT_SECONDS = 5
WINDOWS_CLIPBOARD_OPEN_ATTEMPTS = 5

# File-copy payloads use native file-list formats and never send file bytes through the WebView bridge.
WINDOWS_FILE_CLIPBOARD_SCRIPT = (
    "$ErrorActionPreference = 'Stop'; "
    "$paths = @([Console]::In.ReadToEnd() | ConvertFrom-Json); "
    "Set-Clipboard -LiteralPath $paths"
)

MACOS_FILE_URL_SCRIPT = """
function run() {
  ObjC.import("AppKit");
  const items = $.NSPasteboard.generalPasteboard.pasteboardItems.js || [];
  const paths = [];
  items.forEach((item) => {
    const value = item.stringForType("public.file-url");
    if (!value) return;
    const url = $.NSURL.URLWithString(value);
    if (url && url.isFileURL) paths.push(ObjC.unwrap(url.path));
  });
  return JSON.stringify(paths);
}
""".strip()

# JXA is the dependency-free macOS fallback when source checkouts do not have PyObjC installed.
MACOS_FILE_WRITE_SCRIPT = """
function run(paths) {
  ObjC.import("AppKit");
  const urls = paths.map((path) => $.NSURL.fileURLWithPath(path));
  const pasteboard = $.NSPasteboard.generalPasteboard;
  pasteboard.clearContents;
  if (!pasteboard.writeObjects(urls)) throw new Error("Unable to write file URLs");
}
""".strip()


# Applies the same text ceiling to every platform before clipboard content crosses the native bridge.
def bounded_clipboard_text(value: Any) -> str:
    """Return clipboard text when it is small enough for one form-field insertion."""

    text = str(value or "")
    if len(text) > MAX_CLIPBOARD_TEXT_CHARACTERS:
        raise AppError(
            "The copied text is too large to paste safely.",
            "CLIPBOARD_TEXT_TOO_LARGE",
        )
    return text


# Runs a fixed clipboard reader without a shell and returns its UTF-8 output.
def read_clipboard_command(command: list[str], empty_exit_codes: set[int] | None = None) -> str:
    """Return bounded text emitted by one trusted desktop clipboard command."""

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            timeout=CLIPBOARD_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AppError("The desktop clipboard could not be read.", "CLIPBOARD_READ_FAILED") from error
    if result.returncode != 0:
        if result.returncode in (empty_exit_codes or set()):
            return ""
        raise AppError("The desktop clipboard could not be read.", "CLIPBOARD_READ_FAILED")
    return bounded_clipboard_text(result.stdout.decode("utf-8", errors="replace"))


# Uses macOS' built-in pasteboard utility so text paste does not depend on PyObjC or WebKit permission prompts.
def read_macos_clipboard_text() -> str:
    """Return plain text from the macOS general pasteboard."""

    return read_clipboard_command(["/usr/bin/pbpaste"])


# Opens the Windows clipboard with bounded retries because another app may briefly own the open handle.
def open_windows_clipboard(user32: Any) -> None:
    """Open the Windows clipboard or raise a structured read error."""

    for attempt in range(WINDOWS_CLIPBOARD_OPEN_ATTEMPTS):
        if user32.OpenClipboard(None):
            return
        if attempt + 1 < WINDOWS_CLIPBOARD_OPEN_ATTEMPTS:
            time.sleep(0.02)
    raise AppError("The desktop clipboard is busy.", "CLIPBOARD_BUSY")


# Reads CF_UNICODETEXT through Win32 without launching a shell or adding a runtime package.
def read_windows_clipboard_text() -> str:
    """Return Unicode text from the Windows clipboard."""

    from ctypes import wintypes

    cf_unicode_text = 13
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    open_windows_clipboard(user32)
    try:
        if not user32.IsClipboardFormatAvailable(cf_unicode_text):
            return ""
        handle = user32.GetClipboardData(cf_unicode_text)
        pointer = kernel32.GlobalLock(handle) if handle else None
        if not pointer:
            raise AppError("The desktop clipboard could not be read.", "CLIPBOARD_READ_FAILED")
        try:
            return bounded_clipboard_text(ctypes.wstring_at(pointer))
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


# Reads common Wayland or X11 clipboard helpers, falling back to Tk only when neither helper exists.
def read_linux_clipboard_text() -> str:
    """Return text from the active Linux desktop clipboard."""

    commands = (
        ("wl-paste", ["--no-newline", "--type", "text"]),
        ("xclip", ["-selection", "clipboard", "-out"]),
        ("xsel", ["--clipboard", "--output"]),
    )
    for executable, arguments in commands:
        command_path = shutil.which(executable)
        if command_path:
            return read_clipboard_command([command_path, *arguments], {1})
    try:
        import tkinter
    except ImportError as error:
        raise AppError(
            "No desktop clipboard reader is available on this system.",
            "CLIPBOARD_READER_UNAVAILABLE",
        ) from error
    try:
        root = tkinter.Tk()
        root.withdraw()
        try:
            return bounded_clipboard_text(root.clipboard_get())
        except tkinter.TclError:
            return ""
        finally:
            root.destroy()
    except tkinter.TclError as error:
        raise AppError(
            "No desktop clipboard reader is available on this system.",
            "CLIPBOARD_READER_UNAVAILABLE",
        ) from error


# Dispatches text reads to an OS-owned path rather than the embedded browser Clipboard API.
def read_desktop_clipboard_text() -> str:
    """Return bounded plain text from the current operating-system clipboard."""

    system_name = platform.system()
    if system_name == "Darwin":
        return read_macos_clipboard_text()
    if system_name == "Windows":
        return read_windows_clipboard_text()
    return read_linux_clipboard_text()


# Uses PyObjC when present and returns None only when that optional binding cannot be loaded.
def read_macos_file_urls_with_appkit() -> list[str] | None:
    """Return Finder file paths through PyObjC, or None when PyObjC is unavailable."""

    try:
        from AppKit import NSPasteboard, NSPasteboardURLReadingFileURLsOnlyKey
        from Foundation import NSURL
        from objc import autorelease_pool
    except ImportError:
        return None

    with autorelease_pool():
        options = {NSPasteboardURLReadingFileURLsOnlyKey: True}
        urls = NSPasteboard.generalPasteboard().readObjectsForClasses_options_([NSURL], options) or []
        return [str(url.path()) for url in urls if bool(url.isFileURL()) and str(url.path() or "")]


# Falls back to macOS' bundled JavaScript-to-AppKit bridge when the local Python environment lacks PyObjC.
def read_macos_file_urls_with_jxa() -> list[str]:
    """Return Finder file paths through the system JXA runtime."""

    output = read_clipboard_command(
        ["/usr/bin/osascript", "-l", "JavaScript", "-e", MACOS_FILE_URL_SCRIPT],
    )
    try:
        payload = json.loads(output or "[]")
    except json.JSONDecodeError as error:
        raise AppError("The desktop clipboard returned invalid file data.", "CLIPBOARD_READ_FAILED") from error
    if not isinstance(payload, list) or len(payload) > MAX_CLIPBOARD_FILE_URLS:
        raise AppError("The desktop clipboard returned invalid file data.", "CLIPBOARD_READ_FAILED")
    if any(not isinstance(path, str) or not path for path in payload):
        raise AppError("The desktop clipboard returned invalid file data.", "CLIPBOARD_READ_FAILED")
    return payload


# Reads Finder's file URL representations without making PyObjC a requirement for source runs.
def read_macos_clipboard_file_urls() -> list[str]:
    """Return paths for files currently copied in Finder."""

    try:
        appkit_paths = read_macos_file_urls_with_appkit()
    except (AttributeError, RuntimeError, TypeError, ValueError):
        appkit_paths = None
    if appkit_paths is not None:
        return appkit_paths
    return read_macos_file_urls_with_jxa()


# Verifies clipboard file references before any platform adapter replaces the user's current clipboard contents.
def validated_clipboard_file_paths(values: list[str]) -> list[str]:
    """Return bounded absolute regular-file paths for a desktop file clipboard write."""

    if not isinstance(values, list) or not values or len(values) > MAX_CLIPBOARD_FILE_URLS:
        raise AppError("No supported file was selected to copy.", "CLIPBOARD_FILE_LIST_INVALID")
    paths = []
    for value in values:
        candidate = Path(str(value or ""))
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise AppError("The selected file is unavailable.", "CLIPBOARD_FILE_UNAVAILABLE") from error
        if not candidate.is_absolute() or candidate.is_symlink() or not resolved.is_file():
            raise AppError("The selected file is unavailable.", "CLIPBOARD_FILE_UNAVAILABLE")
        paths.append(str(resolved))
    return paths


# Runs one fixed clipboard writer without a shell and fails before reporting a successful Copy action.
def run_clipboard_writer(command: list[str], payload: bytes | None = None) -> None:
    """Run a trusted desktop clipboard writer with optional stdin payload bytes."""

    try:
        result = subprocess.run(
            command,
            input=payload,
            capture_output=True,
            timeout=CLIPBOARD_COMMAND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise AppError("The selected file could not be copied.", "CLIPBOARD_FILE_WRITE_FAILED") from error
    if result.returncode != 0:
        raise AppError("The selected file could not be copied.", "CLIPBOARD_FILE_WRITE_FAILED")


# Uses NSURL pasteboard objects so Finder and other macOS apps receive a real file reference.
def write_macos_files_with_appkit(paths: list[str]) -> bool | None:
    """Write file URLs through PyObjC, or return None when PyObjC is unavailable."""

    try:
        from AppKit import NSPasteboard
        from Foundation import NSURL
        from objc import autorelease_pool
    except ImportError:
        return None

    with autorelease_pool():
        urls = [NSURL.fileURLWithPath_(path) for path in paths]
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        return bool(pasteboard.writeObjects_(urls))


# Falls back to the system JXA-to-AppKit bridge while preserving exact paths as process arguments.
def write_macos_clipboard_files(paths: list[str]) -> None:
    """Place regular files on the macOS general pasteboard as file URLs."""

    try:
        appkit_written = write_macos_files_with_appkit(paths)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        appkit_written = None
    if appkit_written:
        return
    run_clipboard_writer([
        "/usr/bin/osascript",
        "-l",
        "JavaScript",
        "-e",
        MACOS_FILE_WRITE_SCRIPT,
        *paths,
    ])


# Uses Windows PowerShell's native FileDrop writer with JSON stdin so path characters are never interpreted as code.
def write_windows_clipboard_files(paths: list[str]) -> None:
    """Place regular files on the Windows clipboard as a file-drop list."""

    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if not powershell:
        raise AppError("The Windows clipboard writer is unavailable.", "CLIPBOARD_FILE_WRITER_UNAVAILABLE")
    run_clipboard_writer(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-STA",
            "-Command",
            WINDOWS_FILE_CLIPBOARD_SCRIPT,
        ],
        json.dumps(paths).encode("utf-8"),
    )


# Chooses the file-list target recognized by the active Linux desktop without turning paths into shell input.
def linux_file_clipboard_payload(paths: list[str]) -> tuple[str, bytes]:
    """Return a Linux file-manager clipboard MIME type and encoded copy payload."""

    file_uris = [PurePosixPath(path).as_uri() for path in paths]
    desktop = str(os.environ.get("XDG_CURRENT_DESKTOP") or "").casefold()
    uses_gnome_target = any(name in desktop for name in ("gnome", "cinnamon", "mate", "pantheon"))
    if uses_gnome_target:
        return "x-special/gnome-copied-files", ("copy\n" + "\n".join(file_uris)).encode("utf-8")
    return "text/uri-list", ("\r\n".join(file_uris) + "\r\n").encode("utf-8")


# Uses the user's existing Wayland or X11 clipboard helper because X selections require a live clipboard owner.
def write_linux_clipboard_files(paths: list[str]) -> None:
    """Place regular file URIs on the Linux desktop clipboard."""

    mime_type, payload = linux_file_clipboard_payload(paths)
    wayland_writer = shutil.which("wl-copy")
    x11_writer = shutil.which("xclip")
    if wayland_writer and os.environ.get("WAYLAND_DISPLAY"):
        run_clipboard_writer([wayland_writer, "--type", mime_type], payload)
        return
    if x11_writer:
        run_clipboard_writer([x11_writer, "-selection", "clipboard", "-t", mime_type, "-in"], payload)
        return
    raise AppError(
        "No desktop file clipboard writer is available on this system.",
        "CLIPBOARD_FILE_WRITER_UNAVAILABLE",
    )


# Dispatches verified file references to the current platform without exposing those paths to browser APIs.
def write_desktop_clipboard_files(values: list[str]) -> None:
    """Place existing regular files on the operating-system clipboard for file-aware paste targets."""

    paths = validated_clipboard_file_paths(values)
    system_name = platform.system()
    if system_name == "Darwin":
        write_macos_clipboard_files(paths)
        return
    if system_name == "Windows":
        write_windows_clipboard_files(paths)
        return
    write_linux_clipboard_files(paths)
