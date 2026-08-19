"""Native bridge handlers for app-owned text clipboard paste."""

from __future__ import annotations

from typing import Any, Callable

from gitdesk.desktop_clipboard import read_desktop_clipboard_text


# Registers clipboard actions separately from Media because every text control uses this boundary.
def desktop_clipboard_handlers(controller: Any) -> dict[str, Callable[[dict[str, Any]], Any]]:
    """Return native clipboard actions shared across GitDesk modes."""

    del controller
    return {
        "readClipboardText": lambda payload: {
            "text": read_desktop_clipboard_text(),
        },
    }
