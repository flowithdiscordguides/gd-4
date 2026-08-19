"""User-safe formatting for Git command failures."""

from __future__ import annotations

import re
from typing import Any


# Git remotes can contain HTTP userinfo; never echo that back into the WebView.
CREDENTIAL_URL_PATTERN = re.compile(r"(https?://)[^\s/@]+(?::[^\s/@]*)?@")


# Removes embedded HTTP credentials from text returned by Git.
def redact_embedded_credentials(value: str) -> str:
    """Return Git output with HTTP(S) URL userinfo removed."""

    return CREDENTIAL_URL_PATTERN.sub(r"\1", value)


# Extracts the useful stderr/stdout text from GitPython without exposing command wrappers.
def git_error_output(error: Exception) -> str:
    """Return concise, sanitized output from a GitPython command failure."""

    chunks = []
    for attribute in ("stderr", "stdout"):
        value = getattr(error, attribute, "")
        if value:
            chunks.append(str(value))
    if not chunks:
        chunks.append(str(error))

    lines = []
    for raw_line in "\n".join(chunks).replace("\r", "\n").splitlines():
        line = redact_embedded_credentials(raw_line.strip().strip("'"))
        for prefix in ("stderr:", "stdout:"):
            if line.startswith(prefix):
                line = line[len(prefix):].strip().strip("'")
        if line and not line.startswith("Cmd(") and not line.startswith("cmdline:"):
            lines.append(line)
    return " ".join(lines)[:800]


# Combines a stable app message with the useful Git reason when one is available.
def git_failure_message(prefix: str, error: Exception) -> str:
    """Return a user-facing Git failure message with sanitized command output."""

    detail = git_error_output(error)
    return f"{prefix} {detail}" if detail else prefix


# Builds structured details for Git errors that may help future UI diagnostics.
def git_error_details(error: Exception, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return JSON-safe Git error details."""

    details = dict(extra or {})
    output = git_error_output(error)
    if output:
        details["git_output"] = output
    status = getattr(error, "status", None)
    if status is not None:
        details["status"] = status
    return details
