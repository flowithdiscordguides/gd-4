"""Secure Git credential handoff helpers for clone, push, and pull operations."""

from __future__ import annotations

import os
import shlex
import stat
import sys
from pathlib import Path

from gitdesk.errors import AppError
from gitdesk.giturls import redact_url_credentials
from gitdesk.storage import app_config_path, atomic_write_private_bytes


# Resolves the non-secret helper script path under the user's app config directory.
def askpass_script_path() -> Path:
    """Return the path where GitDesk stores its non-secret Git askpass helper."""

    helper_name = "gitdesk-askpass.cmd" if os.name == "nt" else "gitdesk-askpass"
    return app_config_path() / helper_name


# Returns whether GitDesk is running from a PyInstaller bundle.
def running_frozen_app() -> bool:
    """Return whether the current process is a packaged app executable."""

    return bool(getattr(sys, "frozen", False))


# Builds a source-run launcher script that contains no token and calls the app-owned askpass module.
def askpass_script_text() -> str:
    """Return the non-secret launcher script Git uses as GIT_ASKPASS."""

    source_root = Path(__file__).resolve().parents[1]
    if os.name == "nt":
        return (
            "@echo off\r\n"
            f"set \"PYTHONPATH={source_root}\"\r\n"
            f"\"{sys.executable}\" -m gitdesk.askpass %*\r\n"
        )

    command = [sys.executable, "-m", "gitdesk.askpass"]
    prefix = f"PYTHONPATH={shlex.quote(str(source_root))} "
    quoted_command = " ".join(shlex.quote(part) for part in command)
    return f"#!/bin/sh\n{prefix}exec {quoted_command} \"$@\"\n"


# Creates or refreshes the helper script that Git executes when it needs HTTPS credentials.
def ensure_askpass_script() -> Path:
    """Create the Git askpass helper script and return its executable path."""

    script_path = askpass_script_path()
    try:
        atomic_write_private_bytes(
            script_path,
            askpass_script_text().encode("utf-8"),
            stat.S_IRWXU,
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR,
        )
    except OSError as error:
        raise AppError("Unable to prepare Git credential helper.", "GIT_ASKPASS_PREP_FAILED") from error
    return script_path


# Adds a process-local Git config entry without editing the user's global or repository config.
def add_git_config(environment: dict[str, str], key: str, value: str) -> None:
    """Append one Git config key/value pair to the command environment."""

    try:
        config_count = int(environment.get("GIT_CONFIG_COUNT", "0"))
    except ValueError:
        config_count = 0

    environment[f"GIT_CONFIG_KEY_{config_count}"] = key
    environment[f"GIT_CONFIG_VALUE_{config_count}"] = value
    environment["GIT_CONFIG_COUNT"] = str(config_count + 1)


# Makes GitDesk's selected account win over cached system GitHub credentials.
def force_gitdesk_https_credentials(environment: dict[str, str]) -> None:
    """Disable Git credential helpers for this process and set a neutral GitHub username."""

    add_git_config(environment, "credential.helper", "")
    add_git_config(environment, "credential.https://github.com.username", "x-access-token")


# Returns a remote argument that cannot carry a stale embedded GitHub username.
def git_remote_argument(origin_url: str, login: str | None) -> str:
    """Return origin or a sanitized GitHub HTTPS URL for selected-account auth."""

    safe_url = redact_url_credentials(origin_url)
    return safe_url if login and safe_url.startswith("https://github.com/") else "origin"


# Builds a Git environment that can use a saved PAT without placing the PAT in process variables.
def git_auth_environment(login: str | None = None) -> dict[str, str]:
    """Return environment variables for non-interactive Git authentication."""

    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment.pop("GITDESK_ASKPASS_TOKEN", None)
    environment.pop("GITDESK_ASKPASS_USERNAME", None)
    environment.pop("GITDESK_ASKPASS_MODE", None)
    environment.pop("GITDESK_ASKPASS_LOGIN", None)

    if login:
        force_gitdesk_https_credentials(environment)
        environment["GITDESK_ASKPASS_LOGIN"] = login
        if running_frozen_app():
            environment["GITDESK_ASKPASS_MODE"] = "1"
            environment["GIT_ASKPASS"] = sys.executable
        else:
            environment["GIT_ASKPASS"] = str(ensure_askpass_script())

    return environment
