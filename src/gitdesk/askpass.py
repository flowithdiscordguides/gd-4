"""Git askpass entry point for saved GitHub PAT authentication."""

from __future__ import annotations

import os
import sys

from gitdesk.secrets import TokenStore


# Git asks the helper separately for username and password, so answer only the prompt requested.
def askpass_response(prompt: str, login: str) -> str:
    """Return the Git credential response for the prompt Git supplied."""

    normalized_prompt = prompt.lower()
    if "username" in normalized_prompt:
        return "x-access-token"
    if "password" in normalized_prompt or "token" in normalized_prompt:
        if not login:
            return ""
        try:
            return TokenStore().get_token(login)
        except Exception:
            return ""
    return ""


# Runs as a tiny subprocess launched by Git, never exposing the PAT in the generated helper script.
def run() -> int:
    """Print the requested Git credential field and return a shell status."""

    prompt = " ".join(sys.argv[1:])
    login = os.environ.get("GITDESK_ASKPASS_LOGIN", "")
    print(askpass_response(prompt, login))
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
