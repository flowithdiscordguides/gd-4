"""Non-interactive packaged-runtime checks used before GitDesk artifacts are published."""

from __future__ import annotations

# Standard-library modules serialize the report, compare metadata paths, and detect frozen execution.
import json
from pathlib import Path
import ssl
import sys
from typing import Any

# GitDesk stores expose only non-secret paths and the stable credential-service name to this diagnostic.
from gitdesk import APP_VERSION
from gitdesk.config import SettingsStore
from gitdesk.reposettings import RepoSettingsStore
from gitdesk.secrets import TOKEN_SERVICE_NAME, TokenStore


# Resolves only non-secret LocalApp metadata paths without creating or reading settings or credential values.
def storage_path_report() -> dict[str, str]:
    """Return the settings and repository-metadata paths used by this runtime."""

    settings_store = SettingsStore()
    repository_store = RepoSettingsStore()
    return {
        "settings": settings_store.location(),
        "repository_settings": repository_store.location(),
    }


# Describes the configured credential boundary without querying the system keyring or triggering a security prompt.
def credential_store_report() -> dict[str, str]:
    """Return non-secret facts identifying GitDesk's operating-system credential service."""

    token_store = TokenStore()
    return {
        "kind": "system-keyring",
        "service": token_store.service_name,
    }


# Confirms both metadata files share one LocalApp directory while PAT storage remains outside that directory.
def storage_paths_share_parent(paths: dict[str, str]) -> bool:
    """Return whether every non-secret metadata file resolves under one application config directory."""

    parents = {str(Path(path_value).expanduser().parent) for path_value in paths.values()}
    return len(parents) == 1


# Builds the report consumed by the bundle verifier without reading metadata contents or any PAT.
def self_check_report() -> dict[str, Any]:
    """Return packaged runtime, OpenSSL, metadata-path, credential-service, and version verification results."""

    paths = storage_path_report()
    credential_store = credential_store_report()
    frozen = bool(getattr(sys, "frozen", False))
    paths_share_parent = storage_paths_share_parent(paths)
    # Importing Python's ssl module before gitdesk.secrets proves both native consumers share one OpenSSL 3 ABI.
    ssl_runtime_configured = ssl.OPENSSL_VERSION.startswith("OpenSSL 3.")
    credential_store_configured = credential_store == {
        "kind": "system-keyring",
        "service": TOKEN_SERVICE_NAME,
    }
    return {
        "ok": frozen and paths_share_parent and ssl_runtime_configured and credential_store_configured,
        "frozen": frozen,
        "app_version": APP_VERSION,
        "ssl_runtime": {
            "configured": ssl_runtime_configured,
            "version": ssl.OPENSSL_VERSION,
        },
        "storage_paths": paths,
        "storage_paths_share_parent": paths_share_parent,
        "credential_store": credential_store,
        "credential_store_configured": credential_store_configured,
    }


# Writes the self-check report to an explicit CI-controlled path and returns a process status.
def run(output_path_value: str) -> int:
    """Write a non-secret JSON self-check report and return zero only when every check passes."""

    output_path = Path(str(output_path_value or "").strip()).expanduser()
    # The verifier must supply an explicit destination so diagnostics never write to an implicit user path.
    if not str(output_path_value or "").strip():
        return 2
    report = self_check_report()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1
