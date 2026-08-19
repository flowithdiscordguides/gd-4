"""macOS app bundle replacement support for GitDesk self-updates."""

from __future__ import annotations

# Standard-library helpers handle process launch, plist parsing, scripts, permissions, and paths.
import os
import plistlib
import shlex
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# Third-party platformdirs keeps updater staging inside GitDesk's app cache location.
from platformdirs import PlatformDirs

from gitdesk import APP_NAME
from gitdesk.errors import AppError


APP_BUNDLE_NAME = "GitDesk.app"
APP_EXECUTABLE_NAME = "GitDesk"
HELPER_TIMEOUT_SECONDS = 120
STAGE_DIRECTORY_MODE = 0o700
HELPER_SCRIPT_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR


# Keeps stage directory names filesystem-safe while preserving enough release context for diagnostics.
def clean_stage_name(value: str) -> str:
    """Return a safe update staging name."""

    cleaned = "".join(char if char.isalnum() or char in {".", "_", "-"} else "-" for char in str(value or ""))
    return cleaned.strip(".-_") or "update"


# Creates a one-update staging directory under the user's GitDesk cache folder.
def prepare_update_stage(version_value: str) -> Path:
    """Return a private staging directory for one updater attempt."""

    dirs = PlatformDirs(APP_NAME, "XanderApps")
    root_path = dirs.user_cache_path / "updates"
    try:
        root_path.mkdir(parents=True, exist_ok=True)
        root_path.chmod(STAGE_DIRECTORY_MODE)
        stage_path = Path(tempfile.mkdtemp(prefix=f"{clean_stage_name(version_value)}-", dir=root_path))
        stage_path.chmod(STAGE_DIRECTORY_MODE)
    except OSError as error:
        raise AppError("Unable to prepare the GitDesk update staging folder.", "UPDATER_STAGE_FAILED") from error
    return stage_path


# Finds the currently running PyInstaller app bundle so the helper knows what to replace.
def current_macos_app_bundle() -> Path:
    """Return the current packaged GitDesk .app bundle path."""

    if sys.platform != "darwin":
        message = "Automatic restart updates are currently available only on macOS."
        raise AppError(message, "UPDATER_INSTALL_UNSUPPORTED")
    if not getattr(sys, "frozen", False):
        message = "Automatic restart updates are available only from the packaged GitDesk macOS app."
        raise AppError(message, "UPDATER_INSTALL_NOT_PACKAGED")

    executable_path = Path(sys.executable).resolve()
    for parent_path in executable_path.parents:
        if parent_path.suffix == ".app" and (parent_path / "Contents" / "MacOS").is_dir():
            return parent_path
    raise AppError("GitDesk could not locate its current macOS app bundle.", "UPDATER_APP_BUNDLE_NOT_FOUND")


# Running directly from a mounted DMG cannot replace itself, so install into Applications instead.
def running_from_mounted_volume(app_path: Path) -> bool:
    """Return whether the app bundle is being launched from /Volumes."""

    return len(app_path.parts) > 2 and app_path.parts[1] == "Volumes"


# Chooses the app bundle path that the helper should replace or create.
def target_app_bundle(current_app: Path) -> Path:
    """Return the destination app bundle for the update install."""

    if running_from_mounted_volume(current_app):
        applications_path = Path("/Applications")
        if os.access(applications_path, os.W_OK):
            return applications_path / APP_BUNDLE_NAME
        return Path.home() / "Applications" / APP_BUNDLE_NAME

    if os.access(current_app.parent, os.W_OK):
        return current_app

    user_app = Path.home() / "Applications" / APP_BUNDLE_NAME
    if current_app != user_app:
        return user_app
    raise AppError("GitDesk's app location is not writable for automatic updates.", "UPDATER_INSTALL_LOCATION_LOCKED")


# Validates the install context before downloading a large update asset.
def macos_install_context() -> tuple[Path, Path]:
    """Return the current and target app bundles for a macOS self-update."""

    current_app = current_macos_app_bundle()
    return current_app, target_app_bundle(current_app)


# Parses hdiutil's binary plist output into mounted volume paths.
def mount_points_from_plist(payload: dict[str, Any]) -> list[Path]:
    """Return mounted volume paths from hdiutil attach output."""

    entities = payload.get("system-entities")
    if not isinstance(entities, list):
        return []

    mount_points = []
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        mount_point = str(entity.get("mount-point") or "").strip()
        if mount_point:
            mount_points.append(Path(mount_point))
    return mount_points


# Mounts the downloaded DMG read-only so the helper can copy the bundled app.
def mount_dmg(dmg_path: Path) -> list[Path]:
    """Mount the downloaded update DMG and return its mount points."""

    try:
        result = subprocess.run(
            ["/usr/bin/hdiutil", "attach", "-nobrowse", "-readonly", "-plist", str(dmg_path)],
            capture_output=True,
            timeout=HELPER_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise AppError("Unable to mount the GitDesk update DMG.", "UPDATER_DMG_MOUNT_FAILED") from error

    if result.returncode != 0:
        raise AppError("Unable to mount the GitDesk update DMG.", "UPDATER_DMG_MOUNT_FAILED")
    try:
        payload = plistlib.loads(result.stdout)
    except (plistlib.InvalidFileException, ValueError) as error:
        raise AppError("The update DMG mount response was invalid.", "UPDATER_DMG_MOUNT_INVALID") from error

    mount_points = [path for path in mount_points_from_plist(payload) if path.is_dir()]
    if not mount_points:
        raise AppError("The update DMG did not expose a mounted volume.", "UPDATER_DMG_MOUNT_MISSING")
    return mount_points


# Best-effort cleanup for a DMG mount when staging fails before the helper takes ownership.
def detach_mounts(mount_points: list[Path]) -> None:
    """Detach mounted update volumes without masking the original error."""

    for mount_point in mount_points:
        try:
            subprocess.run(
                ["/usr/bin/hdiutil", "detach", str(mount_point)],
                capture_output=True,
                timeout=HELPER_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue


# Validates the app bundle shape inside the mounted DMG before handing it to the helper script.
def valid_gitdesk_app_bundle(app_path: Path) -> bool:
    """Return whether the path looks like a GitDesk macOS app bundle."""

    return (
        app_path.is_dir()
        and (app_path / "Contents" / "Info.plist").is_file()
        and (app_path / "Contents" / "MacOS" / APP_EXECUTABLE_NAME).is_file()
    )


# Locates the GitDesk.app bundle in the mounted release DMG.
def find_update_app(mount_points: list[Path]) -> tuple[Path, Path]:
    """Return the GitDesk.app path and owning mount point from the mounted update DMG."""

    for mount_point in mount_points:
        candidate = mount_point / APP_BUNDLE_NAME
        if valid_gitdesk_app_bundle(candidate):
            return candidate, mount_point
    raise AppError("The update DMG did not contain GitDesk.app at its root.", "UPDATER_DMG_APP_MISSING")


# Quotes shell variable assignments for the one-shot helper script.
def shell_assignment(name: str, value: str | int | Path) -> str:
    """Return a POSIX shell assignment for a literal value."""

    return f"{name}={shlex.quote(str(value))}"


# Builds the shell helper that waits for GitDesk to close, replaces the app, and relaunches it.
def helper_script_text(
    current_app: Path,
    target_app: Path,
    source_app: Path,
    backup_app: Path,
    mount_point: Path,
    log_path: Path,
) -> str:
    """Return the macOS replacement helper script."""

    return f"""#!/bin/sh
set -u
{shell_assignment("parent_pid", os.getpid())}
{shell_assignment("current_app", current_app)}
{shell_assignment("target_app", target_app)}
{shell_assignment("source_app", source_app)}
{shell_assignment("backup_app", backup_app)}
{shell_assignment("mount_point", mount_point)}
{shell_assignment("log_path", log_path)}
exec >> "$log_path" 2>&1

log() {{
  /usr/bin/printf "%s %s\\n" "$(/bin/date '+%Y-%m-%d %H:%M:%S')" "$*"
}}

detach_update_dmg() {{
  /usr/bin/hdiutil detach "$mount_point" >/dev/null 2>&1 \\
    || /usr/bin/hdiutil detach -force "$mount_point" >/dev/null 2>&1 \\
    || true
}}

fail_before_replace() {{
  log "$1"
  detach_update_dmg
  if [ -d "$current_app" ]; then
    /usr/bin/open "$current_app" >/dev/null 2>&1 || true
  fi
  exit 1
}}

log "GitDesk update helper started."
remaining={HELPER_TIMEOUT_SECONDS}
while /bin/kill -0 "$parent_pid" 2>/dev/null; do
  if [ "$remaining" -le 0 ]; then
    fail_before_replace "Timed out waiting for GitDesk to close."
  fi
  /bin/sleep 1
  remaining=$((remaining - 1))
done
/bin/sleep 1

if [ ! -d "$source_app" ]; then
  fail_before_replace "Mounted update app bundle was missing."
fi

target_parent=$(/usr/bin/dirname "$target_app")
/bin/mkdir -p "$target_parent" || fail_before_replace "Unable to create the target Applications folder."

if [ -e "$backup_app" ] || [ -L "$backup_app" ]; then
  /bin/rm -rf "$backup_app" || fail_before_replace "Unable to clear the previous update backup."
fi

had_backup=0
if [ -e "$target_app" ] || [ -L "$target_app" ]; then
  /bin/mv "$target_app" "$backup_app" || fail_before_replace "Unable to move the existing GitDesk app aside."
  had_backup=1
fi

if /usr/bin/ditto "$source_app" "$target_app"; then
  if [ "$had_backup" = "1" ]; then
    /bin/rm -rf "$backup_app" || log "Could not remove update backup."
  fi
  detach_update_dmg
  /usr/bin/open "$target_app" || exit 1
  log "GitDesk update installed and relaunched."
  exit 0
fi

log "Copy failed; restoring previous GitDesk app."
/bin/rm -rf "$target_app" >/dev/null 2>&1 || true
if [ "$had_backup" = "1" ]; then
  /bin/mv "$backup_app" "$target_app" || true
fi
detach_update_dmg
if [ -d "$target_app" ]; then
  /usr/bin/open "$target_app" >/dev/null 2>&1 || true
elif [ -d "$current_app" ]; then
  /usr/bin/open "$current_app" >/dev/null 2>&1 || true
fi
exit 1
"""


# Writes the one-shot helper with owner-only execute permissions.
def write_helper_script(stage_dir: Path, script_text: str) -> Path:
    """Create the macOS updater helper script and return its path."""

    script_path = stage_dir / "install-and-relaunch.sh"
    try:
        script_path.write_text(script_text, encoding="utf-8")
        script_path.chmod(HELPER_SCRIPT_MODE)
    except OSError as error:
        raise AppError("Unable to write the GitDesk update helper.", "UPDATER_HELPER_WRITE_FAILED") from error
    return script_path


# Launches the helper as an independent process so it survives after GitDesk exits.
def launch_helper(script_path: Path) -> None:
    """Start the update helper script."""

    try:
        subprocess.Popen(
            ["/bin/sh", str(script_path)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
    except OSError as error:
        raise AppError("Unable to start the GitDesk update helper.", "UPDATER_HELPER_START_FAILED") from error


# Stages the mounted update and starts the helper that performs replacement after app shutdown.
def stage_macos_update(dmg_path: Path, stage_dir: Path) -> dict[str, Any]:
    """Prepare a downloaded macOS DMG update for automatic install and relaunch."""

    current_app, target_app = macos_install_context()
    backup_app = target_app.with_name(f".{target_app.name}.update-backup-{os.getpid()}")
    log_path = stage_dir / "install-and-relaunch.log"
    mount_points = mount_dmg(dmg_path)
    helper_started = False

    try:
        source_app, source_mount = find_update_app(mount_points)
        script_text = helper_script_text(
            current_app=current_app,
            target_app=target_app,
            source_app=source_app,
            backup_app=backup_app,
            mount_point=source_mount,
            log_path=log_path,
        )
        script_path = write_helper_script(stage_dir, script_text)
        launch_helper(script_path)
        helper_started = True
        return {
            "mode": "macos_dmg",
            "current_app": str(current_app),
            "target_app": str(target_app),
            "source_app": str(source_app),
            "helper_script": str(script_path),
            "helper_log": str(log_path),
        }
    finally:
        if not helper_started:
            detach_mounts(mount_points)
