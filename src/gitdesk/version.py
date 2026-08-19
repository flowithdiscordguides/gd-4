"""Version resolution for source checkouts, installed packages, and packaged builds."""

from __future__ import annotations

# Standard-library helpers read installed package metadata and source checkout metadata.
from importlib import metadata
from pathlib import Path

try:
    # Python 3.11+ can parse pyproject.toml without adding a runtime dependency.
    import tomllib
except ModuleNotFoundError:
    tomllib = None

try:
    # Packaged release builds write this generated module from the GitHub release tag.
    from gitdesk._build_version import APP_VERSION as BUILD_APP_VERSION
except ImportError:
    BUILD_APP_VERSION = ""


# The distribution name matches pyproject.toml and installed package metadata.
PACKAGE_NAME = "gitdesk"

# This fallback is intentionally low so malformed local metadata never suppresses real releases.
UNKNOWN_VERSION = "0.0.0"


# Normalizes version values from generated modules, package metadata, or TOML.
def clean_version(value: object) -> str:
    """Return a stripped version string, or an empty string when the value is unusable."""

    return str(value or "").strip()


# Returns the generated build version embedded by release packaging.
def generated_build_version() -> str:
    """Return the packaged build version when the generated module exists."""

    return clean_version(BUILD_APP_VERSION)


# Reads the installed distribution version when GitDesk is installed as a package.
def installed_package_version() -> str:
    """Return the installed package version, or an empty string outside installed metadata."""

    try:
        return clean_version(metadata.version(PACKAGE_NAME))
    except metadata.PackageNotFoundError:
        return ""


# Locates the source checkout pyproject.toml beside the src directory.
def source_pyproject_path() -> Path:
    """Return the expected pyproject.toml path for direct source execution."""

    return Path(__file__).resolve().parents[2] / "pyproject.toml"


# Parses project.version from pyproject.toml when a source checkout is available.
def pyproject_version() -> str:
    """Return the source checkout version from pyproject.toml, or an empty string."""

    project_file = source_pyproject_path()
    # Packaged apps normally do not carry pyproject.toml, so absence simply moves to the next source.
    if not project_file.exists():
        return ""
    # Prefer the standard TOML parser when it is available so source metadata is read structurally.
    if tomllib is not None:
        try:
            payload = tomllib.loads(project_file.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return ""
        project = payload.get("project") if isinstance(payload, dict) else {}
        # A malformed project table is ignored so the updater can still try installed metadata.
        if not isinstance(project, dict):
            return ""
        return clean_version(project.get("version"))
    return fallback_pyproject_version(project_file)


# Provides a tiny project.version fallback for Python 3.10 source runs without tomllib.
def fallback_pyproject_version(project_file: Path) -> str:
    """Return project.version by scanning pyproject.toml when tomllib is unavailable."""

    try:
        lines = project_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    in_project = False
    # The fallback only accepts a simple project.version assignment inside the [project] table.
    for line in lines:
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        # Leaving the [project] table before finding version means the fallback should not guess.
        if in_project and stripped.startswith("["):
            return ""
        if in_project and stripped.startswith("version"):
            parts = stripped.split("=", 1)
            # A version line without an assignment is malformed and should not be trusted.
            if len(parts) != 2:
                return ""
            return clean_version(parts[1].strip().strip('"').strip("'"))
    return ""


# Chooses the best available version source in release, installed, then source order.
def resolve_app_version() -> str:
    """Return the version GitDesk should report to update checks and user agents."""

    generated_version = generated_build_version()
    # Release artifacts should always report the tag baked into their generated module.
    if generated_version:
        return generated_version

    installed_version = installed_package_version()
    # Installed package metadata is the next most reliable source when no generated tag exists.
    if installed_version:
        return installed_version

    source_version = pyproject_version()
    # Direct source checkouts can still report the version declared in pyproject.toml.
    if source_version:
        return source_version

    return UNKNOWN_VERSION


APP_VERSION = resolve_app_version()
