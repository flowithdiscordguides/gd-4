"""Regression coverage for Local Mode's macOS folder-access verification gate."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gitdesk.errors import AppError
from gitdesk.localpermissions import local_permission_settings_update, request_project_permission
from gitdesk.localproject_bridge import handle_request_local_mode_permissions


# LocalPermissionTests ensures cached JSON never overrides the operating system's current access decision.
class LocalPermissionTests(unittest.TestCase):
    """Verify real path probes, missing-folder cleanup, and actionable permission denial."""

    # Confirms a current-version cached grant still performs a real folder access probe.
    def test_cached_grant_does_not_skip_actual_access_check(self) -> None:
        """Probe every saved path even when settings contains a matching grant receipt."""

        project = {"path": "/Documents/example", "name": "example", "category": ""}
        settings = {
            "local_projects": [project],
            "local_permission_grants": {
                project["path"]: {
                    "project_path": project["path"],
                    "granted_path": project["path"],
                    "app_version": "current",
                    "granted_at": "earlier",
                },
            },
        }
        replacement_grant = {
            "project_path": project["path"],
            "granted_path": project["path"],
            "app_version": "verified",
            "granted_at": "now",
        }

        with mock.patch("gitdesk.localpermissions.request_project_permission", return_value=replacement_grant) as probe:
            updates = local_permission_settings_update(settings)

        # Permission checks consume the canonical record shape produced by the shared project sanitizer.
        expected_project = {**project, "icon_path": "", "category_foldered": False}
        probe.assert_called_once_with(expected_project)
        self.assertEqual(updates["local_permission_verified_paths"], [project["path"]])
        self.assertEqual(updates["local_permission_grants"][project["path"]], replacement_grant)

    # Confirms folders deleted or disconnected since the prior grant no longer retain a misleading access receipt.
    def test_missing_folder_removes_cached_grant(self) -> None:
        """Remove stale permission metadata when a saved project path no longer exists."""

        project = {"path": "/missing/example", "name": "example", "category": ""}
        settings = {
            "local_projects": [project],
            "local_permission_grants": {
                project["path"]: {
                    "project_path": project["path"],
                    "granted_path": project["path"],
                    "app_version": "old",
                    "granted_at": "earlier",
                },
            },
        }

        with mock.patch("gitdesk.localpermissions.request_project_permission", return_value={}):
            updates = local_permission_settings_update(settings)

        self.assertNotIn(project["path"], updates["local_permission_grants"])
        self.assertEqual(updates["local_permission_missing_paths"], [project["path"]])

    # Confirms a successful real directory scan produces a last-verified receipt for the exact saved project.
    def test_accessible_folder_returns_verified_grant(self) -> None:
        """Record successful operating-system access without relying on an earlier JSON grant."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            project_path = Path(temporary_directory)
            grant = request_project_permission({"path": str(project_path), "name": "example", "category": ""})

        self.assertEqual(grant["project_path"], str(project_path))
        self.assertEqual(grant["granted_path"], str(project_path.resolve()))

    # Confirms macOS denial includes the route users need after the system remembers a prior decision.
    def test_permission_denial_includes_system_settings_recovery(self) -> None:
        """Return LOCAL_PERMISSION_DENIED with actionable Files and Folders guidance."""

        project = {"path": "/Documents/example", "name": "example", "category": ""}
        with mock.patch("gitdesk.localpermissions.os.scandir", side_effect=PermissionError("denied")):
            with self.assertRaises(AppError) as raised:
                request_project_permission(project)

        self.assertEqual(raised.exception.code, "LOCAL_PERMISSION_DENIED")
        self.assertIn("Files & Folders", raised.exception.message)

    # Confirms permission success cannot return Repo Mode settings to a click that is entering Local Mode.
    def test_permission_entry_activates_local_mode_atomically(self) -> None:
        """Save Local Mode with verified permission metadata before returning refreshed local state."""

        settings = {"workspace_mode": "repo", "local_projects": []}
        controller = mock.Mock()
        controller.settings_store.load.return_value = settings
        controller.settings_store.save.side_effect = lambda updates: {**settings, **updates}
        permission_updates = {
            "local_permission_grants": {},
            "local_permission_verified_paths": [],
            "local_permission_missing_paths": [],
        }
        with mock.patch(
            "gitdesk.localproject_bridge.localpermissions.local_permission_settings_update",
            return_value=permission_updates,
        ), mock.patch(
            "gitdesk.localproject_bridge.localprojects.local_projects_state",
            return_value={"projects": []},
        ):
            response = handle_request_local_mode_permissions(controller, {})

        saved_updates = controller.settings_store.save.call_args.args[0]
        self.assertEqual(saved_updates["workspace_mode"], "local")
        self.assertEqual(response["settings"]["workspace_mode"], "local")
        self.assertEqual(response["local"], {"projects": []})

    # Protects the three visible diagnostic surfaces owned by the frontend permission gate.
    def test_permission_gate_reports_activation_failures_everywhere(self) -> None:
        """Require invalid activation responses to reach console, Status, and Activity output."""

        script_path = Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "ui" / "local-permissions.js"
        script = script_path.read_text(encoding="utf-8")

        self.assertIn('"LOCAL_MODE_ACTIVATION_FAILED"', script)
        self.assertIn('console.error("Local Mode entry failed", error);', script)
        self.assertIn("showMessage(message, true);", script)
        self.assertIn("appendActivity(message, true);", script)
        self.assertIn("window.GitDeskDebug.open();", script)

    # Confirms an active Local workspace bypasses the permission entry gate and reaches normal tab handlers.
    def test_active_local_mode_allows_ordinary_tab_reentry(self) -> None:
        """Leave active Local Mode clicks untouched so its existing page can reopen immediately."""

        script_path = Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "ui" / "local-permissions.js"
        script = script_path.read_text(encoding="utf-8")

        self.assertIn("if (workspaceMode && workspaceMode.isLocalMode())", script)
        self.assertLess(
            script.index("if (workspaceMode && workspaceMode.isLocalMode())"),
            script.index("event.preventDefault();"),
        )

    # Protects immediate cached presentation while the authoritative permission response remains pending.
    def test_repo_to_local_entry_presents_before_native_wait(self) -> None:
        """Reveal Local Mode before awaiting Python, then reuse its returned state or restore Repo Mode."""

        root = Path(__file__).resolve().parents[1]
        gate = (root / "src" / "gitdesk" / "ui" / "local-permissions.js").read_text(encoding="utf-8")
        controller = (root / "src" / "gitdesk" / "ui" / "workspace-mode.js").read_text(encoding="utf-8")

        self.assertLess(gate.index("previewLocalMode();"), gate.index('await callNative("requestLocalModePermissions"'))
        self.assertIn('workspaceMode.previewMode("local", true);', gate)
        self.assertIn("workspaceMode.applyLocalResponse(data);", gate)
        self.assertIn("workspaceMode.previewMode(previousMode, true);", gate)
        self.assertNotIn("workspaceMode.applySettings(data.settings);", gate)
        self.assertIn("applyLocalResponse,", controller)

    # Protects the shared paint boundary, button acknowledgement, and deterministic tooltip response.
    def test_native_actions_allow_immediate_button_feedback_to_paint(self) -> None:
        """Yield before native work, acknowledge presses, and reveal app-owned tooltips within 0.2 seconds."""

        root = Path(__file__).resolve().parents[1]
        native = (root / "src" / "gitdesk" / "ui" / "native.js").read_text(encoding="utf-8")
        renderer = (root / "src" / "gitdesk" / "ui" / "render.js").read_text(encoding="utf-8")
        polish = (root / "src" / "gitdesk" / "ui" / "polish.css").read_text(encoding="utf-8")

        self.assertIn("Promise.all([waitForNativeInvoke(), waitForUiPaint()])", native)
        self.assertIn("window.requestAnimationFrame(() => window.setTimeout(resolve, 0));", native)
        self.assertIn("button:active:not(:disabled)", polish)
        self.assertIn("filter: brightness(0.9);", polish)
        self.assertIn("transform: translateY(1px);", polish)
        self.assertIn("const TOOLTIP_DELAY_MS = 200;", renderer)
        self.assertIn('target.removeAttribute("title");', renderer)
        self.assertIn('tooltipElement.setAttribute("role", "tooltip");', renderer)
        self.assertIn(".gitdesk-tooltip[data-visible]", polish)


if __name__ == "__main__":
    unittest.main()
