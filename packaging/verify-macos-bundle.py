"""Verify GitDesk's finished macOS app bundle before the workflow creates a DMG."""

from __future__ import annotations

import json
import plistlib
from pathlib import Path
import subprocess
import sys
from typing import Any


# The verifier enforces the bundle, architecture, and credential identities expected across packaged releases.
EXPECTED_BUNDLE_IDENTIFIER = "com.xander.gitdesk"
EXPECTED_CREDENTIAL_SERVICE = "GitDesk"

# Each separately labeled DMG must contain exactly its declared native architecture.
SUPPORTED_ARCHITECTURES = {"arm64", "x86_64"}

# WebUI's directory names differ from Mach-O architecture labels and must remain exact for its runtime loader.
WEBUI_RUNTIME_FOLDERS = {
    "arm64": "webui-macos-clang-arm64",
    "x86_64": "webui-macos-clang-x64",
}

# The Intel cryptography extension and Python runtime must share this exact staged OpenSSL 3 pair.
OPENSSL_RUNTIME_FILENAMES = ("libssl.3.dylib", "libcrypto.3.dylib")
REQUIRED_INTEL_SSL_SYMBOL = "_SSL_get0_group_name"

# Every protected folder used by Local Mode needs its explanatory privacy string in the shipped bundle.
REQUIRED_PRIVACY_KEYS = {
    "NSAppleEventsUsageDescription",
    "NSDesktopFolderUsageDescription",
    "NSDocumentsFolderUsageDescription",
    "NSDownloadsFolderUsageDescription",
    "NSNetworkVolumesUsageDescription",
    "NSRemovableVolumesUsageDescription",
}

# The modular guide and its existing screenshots must all survive PyInstaller collection into the app bundle.
REQUIRED_GUIDE_ASSETS = {
    "gitdesk-readme.html",
    "gitdesk-guide-layout.css",
    "gitdesk-guide-responsive.css",
    "gitdesk-guide-learning.css",
    "gitdesk-guide-learning-responsive.css",
    "gitdesk-guide-media.js",
    "gitdesk-guide-topics-local.js",
    "gitdesk-guide-topics-primary.js",
    "gitdesk-guide-topics-secondary.js",
    "gitdesk-guide-topic-contracts.js",
    "gitdesk-guide-core.js",
    "gitdesk-guide-interactions.js",
    "1)header.png",
    "2) toolbar.png",
    "3) settings.png",
    "4) devtools.png",
}


# Stops the build with one precise verifier message instead of allowing an incomplete DMG to publish.
def fail(message: str) -> None:
    """Raise a verifier failure with a concise workflow-facing message."""

    raise SystemExit(f"macOS bundle verification failed: {message}")


# Resolves the generated app structure and rejects a workflow path that is not a complete bundle.
def bundle_paths(app_path_value: str) -> tuple[Path, Path, Path]:
    """Return the app, Info.plist, and executable paths for a generated GitDesk bundle."""

    app_path = Path(app_path_value).expanduser()
    plist_path = app_path / "Contents" / "Info.plist"
    executable_path = app_path / "Contents" / "MacOS" / "GitDesk"
    if not app_path.is_dir():
        fail(f"app bundle was not found: {app_path}")
    if not plist_path.is_file():
        fail(f"Info.plist was not found: {plist_path}")
    if not executable_path.is_file():
        fail(f"app executable was not found: {executable_path}")
    return app_path, plist_path, executable_path


# Reads the generated plist as a dictionary so identity and privacy values are validated structurally.
def load_plist(plist_path: Path) -> dict[str, Any]:
    """Return the generated app's Info.plist dictionary."""

    try:
        with plist_path.open("rb") as input_file:
            payload = plistlib.load(input_file)
    except (OSError, plistlib.InvalidFileException) as error:
        fail(f"Info.plist could not be read ({error.__class__.__name__})")
    if not isinstance(payload, dict):
        fail("Info.plist root is not a dictionary")
    return payload


# Verifies the stable bundle identity and every privacy description required by protected Local Mode folders.
def verify_plist(payload: dict[str, Any]) -> None:
    """Validate the bundle identifier and required macOS privacy usage descriptions."""

    if payload.get("CFBundleIdentifier") != EXPECTED_BUNDLE_IDENTIFIER:
        fail("CFBundleIdentifier does not match GitDesk's stable identity")
    missing_keys = sorted(
        key for key in REQUIRED_PRIVACY_KEYS
        if not str(payload.get(key) or "").strip()
    )
    if missing_keys:
        fail(f"Info.plist is missing privacy descriptions: {', '.join(missing_keys)}")


# Reads one Mach-O binary through Apple's architecture inspector without executing bundled code.
def binary_architectures(binary_path: Path) -> set[str]:
    """Return every architecture reported by lipo for the provided Mach-O binary."""

    result = subprocess.run(
        ["lipo", "-archs", str(binary_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"lipo could not inspect {binary_path.name} ({result.stderr.strip()})")
    return set(result.stdout.split())


# Uses Apple's architecture inspector so Intel, Apple Silicon, and universal binaries cannot be mislabeled.
def verify_architecture(binary_path: Path, expected_architecture: str) -> None:
    """Require one Mach-O binary to contain only the architecture declared by its workflow job."""

    if expected_architecture not in SUPPORTED_ARCHITECTURES:
        fail(f"unsupported expected architecture: {expected_architecture or 'empty'}")

    architectures = binary_architectures(binary_path)
    if architectures != {expected_architecture}:
        found_architectures = " ".join(sorted(architectures)) or "unknown"
        fail(
            f"{binary_path.name} expected only {expected_architecture}, found: {found_architectures}"
        )


# Rejects cross-architecture WebUI libraries that collect-all would otherwise place in the same app bundle.
def verify_webui_runtime(app_path: Path, expected_architecture: str) -> None:
    """Require exactly one macOS WebUI dylib in the folder matching the declared app architecture."""

    expected_folder = WEBUI_RUNTIME_FOLDERS.get(expected_architecture)
    if expected_folder is None:
        fail(f"unsupported WebUI architecture: {expected_architecture or 'empty'}")

    runtime_paths = [
        path for path in app_path.rglob("libwebui-2.dylib")
        if path.is_file() and path.parent.name.startswith("webui-macos-clang-")
    ]
    if len(runtime_paths) != 1:
        found_paths = ", ".join(str(path.relative_to(app_path)) for path in runtime_paths) or "none"
        fail(f"expected one macOS WebUI runtime, found: {found_paths}")

    runtime_path = runtime_paths[0]
    if runtime_path.parent.name != expected_folder:
        fail(
            f"expected WebUI runtime folder {expected_folder}, found: {runtime_path.parent.name}"
        )
    verify_architecture(runtime_path, expected_architecture)


# Reads exported symbols from one Mach-O library without loading untrusted bundle code into the verifier process.
def exported_symbols(binary_path: Path) -> set[str]:
    """Return the global defined symbols reported by Apple's nm tool for one bundled library."""

    result = subprocess.run(
        ["nm", "-gU", str(binary_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        fail(f"nm could not inspect {binary_path.name} ({result.stderr.strip()})")
    return set(result.stdout.split())


# Guards the Intel-only replacement against the exact stale-libssl collision that broke cryptography startup.
def verify_openssl_runtime(app_path: Path, expected_architecture: str) -> None:
    """Require an x86_64 OpenSSL pair whose libssl exports cryptography's required group-name API."""

    # Apple Silicon cryptography does not use the Intel runner's dynamic OpenSSL replacement path.
    if expected_architecture != "x86_64":
        return

    frameworks_path = app_path / "Contents" / "Frameworks"
    runtime_paths = {
        filename: frameworks_path / filename
        for filename in OPENSSL_RUNTIME_FILENAMES
    }
    missing_files = [filename for filename, path in runtime_paths.items() if not path.is_file()]
    if missing_files:
        fail(f"Intel OpenSSL runtime files are missing: {', '.join(missing_files)}")
    for runtime_path in runtime_paths.values():
        verify_architecture(runtime_path, expected_architecture)
    if REQUIRED_INTEL_SSL_SYMBOL not in exported_symbols(runtime_paths["libssl.3.dylib"]):
        fail(f"Intel libssl does not export {REQUIRED_INTEL_SSL_SYMBOL}")


# Confirms PyInstaller copied the modular Guide and screenshot assets used by its in-app route.
def verify_guide_asset(app_path: Path) -> None:
    """Require every non-empty HTML, CSS, JavaScript, and PNG asset used by the GitDesk Guide."""

    missing_assets = []
    # Check by fixed basename because PyInstaller's internal bundle directory differs across target platforms.
    for asset_name in sorted(REQUIRED_GUIDE_ASSETS):
        asset_paths = list(app_path.rglob(asset_name))
        if not any(path.is_file() and path.stat().st_size > 0 for path in asset_paths):
            missing_assets.append(asset_name)
    if missing_assets:
        fail(f"GitDesk Guide assets are missing: {', '.join(missing_assets)}")


# Formats bounded subprocess output so a frozen import or loader failure remains visible in GitHub Actions.
def runtime_process_details(result: subprocess.CompletedProcess[str]) -> str:
    """Return concise stdout and stderr details from a failed packaged self-check process."""

    details = []
    for label, output in (("stdout", result.stdout), ("stderr", result.stderr)):
        cleaned_output = str(output or "").strip()
        if cleaned_output:
            details.append(f"{label}: {cleaned_output[-2000:]}")
    return "; ".join(details) or "no stdout or stderr was produced"


# Reads a generated report independently from process status so failed checks still identify their exact condition.
def load_runtime_report(report_path: Path) -> dict[str, Any]:
    """Return the packaged runtime JSON report after validating its file and root shape."""

    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"packaged runtime report could not be read ({error.__class__.__name__})")
    if not isinstance(payload, dict):
        fail("packaged runtime report is not a JSON object")
    return payload


# Validates each non-secret runtime fact separately so one false field produces an actionable Actions error.
def verify_runtime_report(payload: dict[str, Any]) -> None:
    """Require frozen execution, OpenSSL 3, one metadata parent, OS keyring configuration, and a build version."""

    if payload.get("frozen") is not True:
        fail("packaged runtime did not identify itself as a frozen build")
    if payload.get("storage_paths_share_parent") is not True:
        fail("packaged persistence paths do not share one app config directory")
    ssl_runtime = payload.get("ssl_runtime")
    if not isinstance(ssl_runtime, dict) or ssl_runtime.get("configured") is not True:
        fail("packaged Python ssl runtime is not using an OpenSSL 3 ABI")
    if not str(ssl_runtime.get("version") or "").startswith("OpenSSL 3."):
        fail("packaged Python ssl runtime did not report its OpenSSL 3 version")
    credential_store = payload.get("credential_store")
    if payload.get("credential_store_configured") is not True or credential_store != {
        "kind": "system-keyring",
        "service": EXPECTED_CREDENTIAL_SERVICE,
    }:
        fail("packaged runtime does not use GitDesk's operating-system credential service")
    if str(payload.get("app_version") or "").strip() in {"", "0.0.0"}:
        fail("packaged runtime does not contain a generated build version")
    if payload.get("ok") is not True:
        fail("packaged runtime report is inconsistent with its successful component checks")


# Launches only the packaged diagnostic mode, which does not create a window or access any credential item.
def run_packaged_self_check(executable_path: Path, report_path: Path) -> dict[str, Any]:
    """Return the packaged runtime report or expose the process evidence that prevented its creation."""

    # Remove a prior local diagnostic so a startup failure can never be mistaken for a newly generated report.
    report_path.unlink(missing_ok=True)
    result = subprocess.run(
        [str(executable_path), "--gitdesk-self-check", str(report_path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    # A status-one self-check normally writes a valid report whose false field explains the failure precisely.
    if report_path.is_file():
        payload = load_runtime_report(report_path)
        verify_runtime_report(payload)
        if result.returncode != 0:
            details = runtime_process_details(result)
            fail(f"packaged runtime exited with status {result.returncode} after a valid report; {details}")
        return payload

    # Import, loader, or startup failures occur before report creation, so surface their captured process output.
    if result.returncode != 0:
        details = runtime_process_details(result)
        fail(f"packaged runtime exited with status {result.returncode} before writing its report; {details}")
    fail("packaged runtime exited successfully without writing its report")


# Coordinates static bundle inspection and the packaged non-UI runtime check.
def main(argv: list[str]) -> int:
    """Verify the app path and declared architecture before the workflow packages a DMG."""

    if len(argv) != 3:
        raise SystemExit(
            "Usage: python packaging/verify-macos-bundle.py dist/GitDesk.app <arm64|x86_64>"
        )
    app_path, plist_path, executable_path = bundle_paths(argv[1])
    verify_plist(load_plist(plist_path))
    verify_architecture(executable_path, argv[2])
    verify_webui_runtime(app_path, argv[2])
    verify_openssl_runtime(app_path, argv[2])
    verify_guide_asset(app_path)
    report_path = app_path.parent / "gitdesk-packaged-self-check.json"
    run_packaged_self_check(executable_path, report_path)
    print(
        f"Verified macOS {argv[2]} identity, privacy metadata, assets, metadata paths, and keyring service."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
