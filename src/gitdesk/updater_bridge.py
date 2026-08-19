"""Bridge handlers for separate public GitDesk update checks and installations."""

from __future__ import annotations

import threading
from typing import Any

from webui import webui

from gitdesk.updater import check_latest_update, install_latest_update


# The frontend needs a moment to receive the restart response before WebUI closes the window.
UPDATE_EXIT_DELAY_SECONDS = 1.0


# Returns updater bridge actions without expanding the central BridgeController class.
def updater_handlers(_controller: Any) -> dict[str, Any]:
    """Return native bridge actions for GitDesk updater workflows."""

    return {
        "checkGitDeskUpdate": handle_check_gitdesk_update,
        "installGitDeskUpdate": handle_install_gitdesk_update,
    }


# Checks the fixed public release repository without reading any saved GitHub credential.
def handle_check_gitdesk_update(_payload: dict[str, Any]) -> dict[str, Any]:
    """Return public updater status without downloading or staging an installer."""

    return check_latest_update()


# Closes the WebUI window after the helper has been started and the response has reached JavaScript.
def schedule_update_exit() -> None:
    """Schedule GitDesk shutdown so the external updater helper can replace the app bundle."""

    timer = threading.Timer(UPDATE_EXIT_DELAY_SECONDS, webui.exit)
    timer.daemon = True
    timer.start()


# Performs the update check, stages install, and asks the current app process to exit.
def handle_install_gitdesk_update(payload: dict[str, Any]) -> dict[str, Any]:
    """Stage the exact release tag returned by the preceding public update check."""

    expected_version = str(payload.get("expected_version") or "").strip()
    result = install_latest_update(expected_version)
    if result.get("status") == "restarting":
        schedule_update_exit()
    return result
