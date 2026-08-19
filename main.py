"""Desktop entry point for launching the GitDesk webui2 application."""

from __future__ import annotations

import os
import sys
from pathlib import Path


# Adds the source directory when the app is launched directly from a checkout instead of an installed wheel.
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"

# This path insertion is limited to local source execution and avoids requiring an editable install.
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Starts the desktop shell when the file is executed directly by Python.
if __name__ == "__main__":
    # CI invokes this non-UI path from the frozen executable to prove packaged imports and storage identities.
    self_check_mode = "--gitdesk-self-check" in sys.argv
    if self_check_mode:
        argument_index = sys.argv.index("--gitdesk-self-check")
        output_path = sys.argv[argument_index + 1] if len(sys.argv) > argument_index + 1 else ""
        from gitdesk.selfcheck import run as run_self_check

        raise SystemExit(run_self_check(output_path))

    askpass_mode = "--gitdesk-askpass" in sys.argv or (
        os.environ.get("GITDESK_ASKPASS_MODE") == "1"
        and bool(os.environ.get("GITDESK_ASKPASS_LOGIN"))
    )
    if askpass_mode:
        from gitdesk.askpass import run as run_askpass

        if "--gitdesk-askpass" in sys.argv:
            sys.argv.remove("--gitdesk-askpass")
        raise SystemExit(run_askpass())

    from gitdesk.app import run_app

    run_app()
