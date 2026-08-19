"""Patch GitDesk's generated macOS app bundle with required privacy metadata.

This packaging helper runs after PyInstaller creates ``dist/GitDesk.app`` and before
the workflow wraps that app in a DMG. macOS uses these Info.plist values to decide
which privacy prompts can be shown when GitDesk accesses Local Mode folders.
"""

from __future__ import annotations

import plistlib
import sys
from pathlib import Path

# GitDesk needs a stable bundle identifier so macOS TCC and Keychain decisions
# attach to the app across rebuilds instead of a transient PyInstaller identity.
BUNDLE_IDENTIFIER = "com.xander.gitdesk"

# These strings are intentionally explicit because macOS shows them in privacy
# prompts when the packaged app accesses protected user folders or AppleScript.
PERMISSION_DESCRIPTIONS = {
    "NSAppleEventsUsageDescription": (
        "GitDesk uses the macOS folder picker so you can choose project and "
        "repository folders."
    ),
    "NSDesktopFolderUsageDescription": (
        "GitDesk needs access to selected Desktop folders to load Local Mode "
        "projects and versions."
    ),
    "NSDocumentsFolderUsageDescription": (
        "GitDesk needs access to selected Documents folders to load Local Mode "
        "projects and versions."
    ),
    "NSDownloadsFolderUsageDescription": (
        "GitDesk needs access to selected Downloads folders used as local "
        "project folders."
    ),
    "NSNetworkVolumesUsageDescription": (
        "GitDesk needs access to selected network volume folders used as local "
        "project folders."
    ),
    "NSRemovableVolumesUsageDescription": (
        "GitDesk needs access to selected removable drive folders used as local "
        "project folders."
    ),
}


# Resolves the Info.plist inside the generated .app bundle and fails clearly if
# PyInstaller did not create the expected macOS application structure.
def info_plist_path(app_path_value: str) -> Path:
    """Return the Info.plist path for a generated macOS .app bundle."""

    app_path = Path(app_path_value).expanduser()
    plist_path = app_path / "Contents" / "Info.plist"
    if not plist_path.is_file():
        raise SystemExit(f"Info.plist was not found: {plist_path}")
    return plist_path


# Loads the existing PyInstaller plist and overlays only the identity/privacy
# fields GitDesk needs, preserving the rest of PyInstaller's generated metadata.
def patched_plist_payload(plist_path: Path) -> dict[str, object]:
    """Return Info.plist contents with GitDesk's macOS privacy metadata."""

    with plist_path.open("rb") as input_file:
        payload = plistlib.load(input_file)

    if not isinstance(payload, dict):
        raise SystemExit("Info.plist root must be a dictionary.")

    payload["CFBundleIdentifier"] = BUNDLE_IDENTIFIER
    payload.update(PERMISSION_DESCRIPTIONS)
    return payload


# Writes XML plist output so the bundle remains easy to inspect in packaged
# artifacts and in GitHub Actions build logs if future diagnostics are needed.
def write_plist(plist_path: Path, payload: dict[str, object]) -> None:
    """Write patched Info.plist contents back to disk."""

    with plist_path.open("wb") as output_file:
        plistlib.dump(payload, output_file, sort_keys=True)


# Provides a tiny command-line boundary for the GitHub Actions workflow.
def main(argv: list[str]) -> int:
    """Patch the .app bundle path supplied by the workflow and return an exit code."""

    if len(argv) != 2:
        raise SystemExit(
            "Usage: python packaging/patch-macos-permissions.py dist/GitDesk.app"
        )

    plist_path = info_plist_path(argv[1])
    write_plist(plist_path, patched_plist_payload(plist_path))
    print(f"Patched macOS permissions in {plist_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
