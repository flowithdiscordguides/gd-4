"""Native folder and file selection helpers for GitDesk desktop workflows."""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

from gitdesk.errors import AppError


# Escapes user-facing values before embedding them in AppleScript source strings.
def applescript_string(value: str) -> str:
    """Return a quoted AppleScript string literal for a prompt or POSIX path."""

    escaped_value = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped_value}"'


# Resolves a best-effort initial folder without requiring it to exist.
def normalize_initial_directory(path_value: str) -> str:
    """Return an existing directory path suitable for native folder picker defaults."""

    cleaned_path = str(path_value or "").strip()
    if not cleaned_path:
        return ""

    candidate = Path(cleaned_path).expanduser()
    if candidate.is_file():
        candidate = candidate.parent
    if candidate.is_dir():
        return str(candidate.resolve())
    return ""


# Opens macOS' built-in folder picker through AppleScript without adding GUI dependencies.
def choose_directory_macos(initial_path: str, title: str) -> str:
    """Return a selected macOS folder path, or an empty string when the dialog is cancelled."""

    default_clause = ""
    if initial_path:
        default_clause = f" default location POSIX file {applescript_string(initial_path)}"
    script = f"POSIX path of (choose folder with prompt {applescript_string(title)}{default_clause})"
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode == 0:
        return result.stdout.strip().rstrip("/")
    if "-128" in result.stderr:
        return ""
    raise AppError("Could not open the destination folder picker.", "FOLDER_DIALOG_FAILED")


# Opens Windows' folder picker through PowerShell's standard FolderBrowserDialog.
def choose_directory_windows(initial_path: str, title: str) -> str:
    """Return a selected Windows folder path, or an empty string when the dialog is cancelled."""

    selected_path = initial_path.replace("'", "''")
    description = title.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
        f"$dialog.Description = '{description}'; "
        f"$dialog.SelectedPath = '{selected_path}'; "
        "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
        "{ $dialog.SelectedPath }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-Command", script],
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode == 0:
        return result.stdout.strip()
    raise AppError("Could not open the destination folder picker.", "FOLDER_DIALOG_FAILED")


# Opens Linux folder pickers that are commonly available in desktop environments.
def choose_directory_linux(initial_path: str, title: str) -> str:
    """Return a selected Linux folder path, or an empty string when the dialog is cancelled."""

    zenity = shutil.which("zenity")
    if zenity:
        command = [zenity, "--file-selection", "--directory", f"--title={title}"]
        if initial_path:
            command.append(f"--filename={initial_path}/")
        return run_optional_dialog(command)

    kdialog = shutil.which("kdialog")
    if kdialog:
        command = [kdialog, "--getexistingdirectory", initial_path or str(Path.home()), title]
        return run_optional_dialog(command)

    return choose_directory_tk(initial_path, title)


# Runs optional desktop dialog commands where cancellation is expected and not an application error.
def run_optional_dialog(command: list[str]) -> str:
    """Return stdout from a dialog command while treating user cancellation as no selection."""

    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode == 0:
        return result.stdout.strip()
    if result.returncode in {1, 130}:
        return ""
    raise AppError("Could not open the destination folder picker.", "FOLDER_DIALOG_FAILED")


# Tk is a last-resort fallback for platforms without scriptable native folder picker commands.
def choose_directory_tk(initial_path: str, title: str) -> str:
    """Return a selected folder through Tk's directory dialog, or an empty string when cancelled."""

    try:
        import tkinter
        from tkinter import filedialog
    except ImportError as error:
        raise AppError("No folder picker is available on this system.", "FOLDER_DIALOG_UNAVAILABLE") from error

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(initialdir=initial_path or str(Path.home()), title=title) or ""
    finally:
        root.destroy()


# Chooses a destination folder with the best native picker available for the current platform.
def choose_directory(initial_path: str = "", title: str = "Choose destination folder") -> str:
    """Return the selected destination folder path, or an empty string when the user cancels."""

    normalized_initial = normalize_initial_directory(initial_path)
    system_name = platform.system()
    if system_name == "Darwin":
        return choose_directory_macos(normalized_initial, title)
    if system_name == "Windows":
        return choose_directory_windows(normalized_initial, title)
    return choose_directory_linux(normalized_initial, title)


# Opens macOS' native file picker while backend validation remains responsible for accepted content.
def choose_file_macos(initial_path: str, title: str) -> str:
    """Return a selected macOS file path, or an empty string when the dialog is cancelled."""

    default_clause = ""
    if initial_path:
        default_clause = f" default location POSIX file {applescript_string(initial_path)}"
    script = f"POSIX path of (choose file with prompt {applescript_string(title)}{default_clause})"
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    if "-128" in result.stderr:
        return ""
    raise AppError("Could not open the file picker.", "FILE_DIALOG_FAILED")


# Opens Windows' native file picker with a discoverability filter for the requested extensions.
def choose_file_windows(initial_path: str, title: str, patterns: tuple[str, ...], filter_label: str) -> str:
    """Return a selected Windows file path, or an empty string when the dialog is cancelled."""

    initial_directory = initial_path.replace("'", "''")
    dialog_title = title.replace("'", "''")
    pattern_text = ";".join(patterns or ("*.*",)).replace("'", "''")
    safe_filter_label = filter_label.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$dialog = New-Object System.Windows.Forms.OpenFileDialog; "
        f"$dialog.Title = '{dialog_title}'; "
        f"$dialog.InitialDirectory = '{initial_directory}'; "
        f"$dialog.Filter = '{safe_filter_label}|{pattern_text}|All files|*.*'; "
        "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
        "{ $dialog.FileName }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-Command", script],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    raise AppError("Could not open the file picker.", "FILE_DIALOG_FAILED")


# Opens a common Linux file picker and falls back to Tk when no desktop helper is installed.
def choose_file_linux(initial_path: str, title: str, patterns: tuple[str, ...], filter_label: str) -> str:
    """Return a selected Linux file path, or an empty string when the dialog is cancelled."""

    zenity = shutil.which("zenity")
    if zenity:
        command = [zenity, "--file-selection", f"--title={title}"]
        if patterns:
            command.append(f"--file-filter={filter_label} | {' '.join(patterns)}")
        if initial_path:
            command.append(f"--filename={initial_path}/")
        return run_optional_dialog(command)

    kdialog = shutil.which("kdialog")
    if kdialog:
        filter_text = f"{' '.join(patterns)}|{filter_label}" if patterns else "*|All files"
        command = [kdialog, "--getopenfilename", initial_path or str(Path.home()), filter_text, title]
        return run_optional_dialog(command)
    return choose_file_tk(initial_path, title, patterns, filter_label)


# Tk provides the portable fallback when native scriptable file pickers are unavailable.
def choose_file_tk(initial_path: str, title: str, patterns: tuple[str, ...], filter_label: str) -> str:
    """Return a selected file through Tk, or an empty string when the dialog is cancelled."""

    try:
        import tkinter
        from tkinter import filedialog
    except ImportError as error:
        raise AppError("No file picker is available on this system.", "FILE_DIALOG_UNAVAILABLE") from error

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        filetypes = [(filter_label, " ".join(patterns)), ("All files", "*.*")]
        return filedialog.askopenfilename(
            initialdir=initial_path or str(Path.home()),
            title=title,
            filetypes=filetypes,
        ) or ""
    finally:
        root.destroy()


# Chooses one file with the best available platform picker and a normalized initial directory.
def choose_file(
    initial_path: str = "",
    title: str = "Choose file",
    patterns: tuple[str, ...] = (),
    filter_label: str = "Supported images",
) -> str:
    """Return a selected file path, or an empty string when the user cancels."""

    normalized_initial = normalize_initial_directory(initial_path)
    system_name = platform.system()
    if system_name == "Darwin":
        return choose_file_macos(normalized_initial, title)
    if system_name == "Windows":
        return choose_file_windows(normalized_initial, title, patterns, filter_label)
    return choose_file_linux(normalized_initial, title, patterns, filter_label)


def choose_save_file_macos(default_name: str, title: str) -> str:
    """Return a destination from macOS' save dialog, or an empty string when cancelled."""

    script = (
        f"POSIX path of (choose file name with prompt {applescript_string(title)} "
        f"default name {applescript_string(default_name)})"
    )
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=300)
    if result.returncode == 0:
        return result.stdout.strip()
    if "-128" in result.stderr:
        return ""
    raise AppError("Could not open the save-file picker.", "SAVE_DIALOG_FAILED")


def choose_save_file_windows(default_name: str, title: str, file_types: tuple[tuple[str, str], ...]) -> str:
    """Return a destination from Windows' standard SaveFileDialog."""

    safe_name = default_name.replace("'", "''")
    safe_title = title.replace("'", "''")
    filters = "|".join(f"{label}|{pattern}" for label, pattern in file_types).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$dialog = New-Object System.Windows.Forms.SaveFileDialog; "
        f"$dialog.Title = '{safe_title}'; $dialog.FileName = '{safe_name}'; "
        f"$dialog.Filter = '{filters}'; $dialog.OverwritePrompt = $true; "
        "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { $dialog.FileName }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-STA", "-Command", script],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    raise AppError("Could not open the save-file picker.", "SAVE_DIALOG_FAILED")


def choose_save_file_tk(default_name: str, title: str, file_types: tuple[tuple[str, str], ...]) -> str:
    """Return a destination through Tk's portable save dialog."""

    try:
        import tkinter
        from tkinter import filedialog
    except ImportError as error:
        raise AppError("No save-file picker is available on this system.", "SAVE_DIALOG_UNAVAILABLE") from error
    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.asksaveasfilename(
            initialfile=default_name,
            title=title,
            filetypes=list(file_types),
            confirmoverwrite=True,
        ) or ""
    finally:
        root.destroy()


def choose_save_file_linux(default_name: str, title: str, file_types: tuple[tuple[str, str], ...]) -> str:
    """Return a destination from a Linux save dialog with a Tk fallback."""

    zenity = shutil.which("zenity")
    if zenity:
        command = [zenity, "--file-selection", "--save", "--confirm-overwrite", f"--title={title}"]
        command.append(f"--filename={default_name}")
        for label, pattern in file_types:
            command.append(f"--file-filter={label} | {pattern}")
        return run_optional_save_dialog(command)
    kdialog = shutil.which("kdialog")
    if kdialog:
        filter_text = "\n".join(f"{pattern}|{label}" for label, pattern in file_types)
        return run_optional_save_dialog([kdialog, "--getsavefilename", default_name, filter_text, title])
    return choose_save_file_tk(default_name, title, file_types)


def run_optional_save_dialog(command: list[str]) -> str:
    """Run a save dialog command while treating cancellation as an empty selection."""

    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode == 0:
        return result.stdout.strip()
    if result.returncode in {1, 130}:
        return ""
    raise AppError("Could not open the save-file picker.", "SAVE_DIALOG_FAILED")


def choose_save_file(
    default_name: str,
    title: str = "Save file",
    file_types: tuple[tuple[str, str], ...] = (("JSON files", "*.json"),),
) -> str:
    """Return a user-selected save path through the best platform picker."""

    system_name = platform.system()
    if system_name == "Darwin":
        return choose_save_file_macos(default_name, title)
    if system_name == "Windows":
        return choose_save_file_windows(default_name, title, file_types)
    return choose_save_file_linux(default_name, title, file_types)
