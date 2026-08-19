"""Write the generated GitDesk build version used by packaged release artifacts."""

from __future__ import annotations

# Standard-library modules provide environment access, paths, CLI arguments, and optional TOML parsing.
import os
import sys
from pathlib import Path

try:
    # Python 3.11+ can read pyproject.toml directly during CI and local packaging.
    import tomllib
except ModuleNotFoundError:
    tomllib = None


# Paths are resolved from this helper so the workflow can call it from the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = PROJECT_ROOT / "pyproject.toml"
BUILD_VERSION_PATH = PROJECT_ROOT / "src" / "gitdesk" / "_build_version.py"


# Normalizes a candidate release tag or version into a safe string literal value.
def clean_version(value: object) -> str:
    """Return a stripped version string, or an empty string when no version is available."""

    return str(value or "").strip()


# Reads project.version through tomllib when the runner provides Python 3.11+.
def tomllib_pyproject_version() -> str:
    """Return pyproject.toml project.version using tomllib, or an empty string."""

    # Older Python versions fall through to the narrow scanner below instead of importing a dependency.
    if tomllib is None:
        return ""
    try:
        payload = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ""
    project = payload.get("project") if isinstance(payload, dict) else {}
    # If the project table is malformed, the caller should try the fallback scanner.
    if not isinstance(project, dict):
        return ""
    return clean_version(project.get("version"))


# Provides a narrow fallback for reading project.version without third-party packages.
def fallback_pyproject_version() -> str:
    """Return project.version by scanning pyproject.toml when tomllib is unavailable."""

    try:
        lines = PYPROJECT_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    in_project = False
    # The fallback intentionally scans only project.version, which is all the generated module needs.
    for line in lines:
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        # Reaching another table before version means the project version was not found safely.
        if in_project and stripped.startswith("["):
            return ""
        if in_project and stripped.startswith("version"):
            parts = stripped.split("=", 1)
            # Malformed version assignments are ignored rather than written into generated code.
            if len(parts) != 2:
                return ""
            return clean_version(parts[1].strip().strip('"').strip("'"))
    return ""


# Returns the pyproject version used for non-tagged manual packaging builds.
def pyproject_version() -> str:
    """Return the source package version from pyproject.toml."""

    return tomllib_pyproject_version() or fallback_pyproject_version()


# Adds the GitHub Actions run number so manual DMG updates get a fresh app version.
def workflow_build_version(base_version: str) -> str:
    """Return a per-build version for non-tagged CI artifacts, or an empty string outside CI."""

    run_number = clean_version(os.environ.get("GITHUB_RUN_NUMBER"))
    if not base_version or not run_number:
        return ""
    run_attempt = clean_version(os.environ.get("GITHUB_RUN_ATTEMPT"))
    suffix = f"build.{run_number}"
    if run_attempt and run_attempt != "1":
        suffix = f"{suffix}.{run_attempt}"
    return f"{base_version}+{suffix}"


# Selects the release tag for tagged builds, then falls back to source package metadata.
def selected_build_version(argv: list[str]) -> str:
    """Return the version that should be written into the generated build module."""

    # An explicit CLI version lets local packaging scripts override CI environment metadata.
    if len(argv) > 1:
        return clean_version(argv[1])

    ref_type = clean_version(os.environ.get("GITHUB_REF_TYPE"))
    ref_name = clean_version(os.environ.get("GITHUB_REF_NAME"))
    # Tagged GitHub Actions builds should report the exact release tag that produced the binary.
    if ref_type == "tag" and ref_name:
        return ref_name

    source_version = pyproject_version()
    return workflow_build_version(source_version) or source_version


# Writes a Python module that packaged builds import before installed/source metadata.
def write_build_version(version: str) -> None:
    """Write the generated `_build_version.py` module for packaged artifacts."""

    # Refuse to create an empty generated module because that would hide real release updates.
    if not version:
        raise SystemExit("Unable to determine a GitDesk build version.")
    BUILD_VERSION_PATH.write_text(
        '"""Generated build version for packaged GitDesk artifacts."""\n\n'
        f"APP_VERSION = {version!r}\n",
        encoding="utf-8",
    )


# Script entry point used by GitHub Actions before package installation and PyInstaller.
def main(argv: list[str]) -> None:
    """Write the build version selected from CLI, release tag, or pyproject.toml."""

    write_build_version(selected_build_version(argv))


if __name__ == "__main__":
    main(sys.argv)
