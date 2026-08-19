"""Stage only the WebUI native library required by one macOS PyInstaller target."""

from __future__ import annotations

# Standard-library modules locate the installed package, copy its runtime, and inspect Mach-O architecture metadata.
import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys


# Resolve generated staging output from this script so GitHub Actions can invoke it from the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
STAGING_ROOT = PROJECT_ROOT / "build" / "webui-runtime"

# WebUI names Intel directories as x64 even though Mach-O and PyInstaller identify the architecture as x86_64.
SUPPORTED_RUNTIME_FOLDERS = {
    "webui-macos-clang-arm64": "arm64",
    "webui-macos-clang-x64": "x86_64",
}
RUNTIME_FILENAME = "libwebui-2.dylib"


# Locates the installed WebUI package without importing it, which would load its native library during staging.
def webui_package_root() -> Path:
    """Return the installed WebUI package directory or stop when the dependency is unavailable."""

    package_spec = importlib.util.find_spec("webui")
    if package_spec is None or not package_spec.origin:
        raise SystemExit("The installed webui package could not be located.")
    return Path(package_spec.origin).resolve().parent


# Reads the source dylib architecture before copying it into an architecture-labeled app bundle.
def dylib_architectures(dylib_path: Path) -> set[str]:
    """Return the Mach-O architectures reported by lipo for the provided WebUI dylib."""

    result = subprocess.run(
        ["lipo", "-archs", str(dylib_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"Unable to inspect the WebUI runtime: {result.stderr.strip()}")
    return set(result.stdout.split())


# Copies one proven native runtime while preserving the directory name expected by webui.load_library.
def stage_runtime(runtime_folder: str) -> Path:
    """Stage the requested macOS WebUI runtime and return its generated binary path."""

    expected_architecture = SUPPORTED_RUNTIME_FOLDERS.get(runtime_folder)
    if expected_architecture is None:
        supported = ", ".join(sorted(SUPPORTED_RUNTIME_FOLDERS))
        raise SystemExit(f"Unsupported WebUI runtime folder. Expected one of: {supported}")

    source_path = webui_package_root() / runtime_folder / RUNTIME_FILENAME
    if not source_path.is_file():
        raise SystemExit(f"The requested WebUI runtime was not found: {source_path}")

    architectures = dylib_architectures(source_path)
    if architectures != {expected_architecture}:
        found = " ".join(sorted(architectures)) or "unknown"
        raise SystemExit(
            f"WebUI runtime {runtime_folder} must contain only {expected_architecture}; found: {found}"
        )

    destination_path = STAGING_ROOT / runtime_folder / RUNTIME_FILENAME
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination_path)
    return destination_path


# Provides the command-line boundary used by both native macOS matrix entries.
def main(argv: list[str]) -> int:
    """Stage the runtime folder supplied by GitHub Actions and report its repository-relative path."""

    if len(argv) != 2:
        raise SystemExit(
            "Usage: python packaging/stage-macos-webui-runtime.py "
            "<webui-macos-clang-arm64|webui-macos-clang-x64>"
        )
    staged_path = stage_runtime(argv[1])
    print(f"Staged {staged_path.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
