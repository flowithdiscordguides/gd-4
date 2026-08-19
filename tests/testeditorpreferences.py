"""Regression coverage for safe VS Code and VSCodium preference routing."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gitdesk.editor_preferences import clean_editor_preferences
from gitdesk.errors import AppError
from gitdesk.nativeopen import editor_command, open_in_editor


class EditorPreferenceTests(unittest.TestCase):
    """Verify sanitation, trusted executable launch arguments, and frontend routing contracts."""

    def test_editor_preference_is_allowlisted(self) -> None:
        """Reject arbitrary editor identifiers while retaining an inert VSCodium path string."""

        self.assertEqual(clean_editor_preferences({"editor": "shell", "vscodium_path": 12}), {
            "editor": "vscode",
            "vscodium_path": "12",
        })
        self.assertEqual(clean_editor_preferences({"editor": "vscodium"})["editor"], "vscodium")

    @patch("gitdesk.nativeopen.platform.system", return_value="Linux")
    @patch("gitdesk.nativeopen.subprocess.Popen")
    def test_selected_vscodium_executable_receives_exact_path(self, popen, system) -> None:
        """Launch without a shell and preserve the exact existing target path argument."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            executable = root / "codium"
            executable.write_text("binary placeholder", encoding="utf-8")
            executable.chmod(0o755)
            target = root / "project"
            target.mkdir()
            result = open_in_editor(str(target), {
                "editor": "vscodium",
                "vscodium_path": str(executable),
            })

        self.assertEqual(result["editor"], "VSCodium")
        popen.assert_called_once_with([str(executable.resolve()), str(target.resolve())])

    @patch("gitdesk.nativeopen.platform.system", return_value="Linux")
    def test_arbitrary_executable_is_not_accepted_as_vscodium(self, system) -> None:
        """Reject a real file whose basename is not an allowlisted VSCodium executable."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            executable = Path(temporary_directory) / "dangerous-script"
            executable.write_text("not codium", encoding="utf-8")
            with self.assertRaises(AppError) as raised:
                editor_command({"editor": "vscodium", "vscodium_path": str(executable)})
        self.assertEqual(raised.exception.code, "VSCODIUM_NOT_FOUND")

    def test_all_editor_surfaces_use_saved_preference_and_dynamic_copy(self) -> None:
        """Protect repository, exact version, and document routing plus tooltip-manager ownership."""

        root = Path(__file__).resolve().parents[1]
        source_root = root / "src/gitdesk"
        ui = source_root / "ui"
        repository_bridge = (source_root / "repoaction_bridge.py").read_text(encoding="utf-8")
        version_bridge = (source_root / "localversion_bridge.py").read_text(encoding="utf-8")
        document_bridge = (source_root / "documentbuilder_bridge.py").read_text(encoding="utf-8")
        editor_ui = (ui / "editor-settings.js").read_text(encoding="utf-8")
        editor_css = (ui / "editor-settings.css").read_text(encoding="utf-8")
        picker = (ui / "local-project-picker.js").read_text(encoding="utf-8")
        version_actions = (ui / "local-version-actions.js").read_text(encoding="utf-8")

        self.assertIn('get("editor_preferences")', repository_bridge)
        self.assertIn('payload.get("version_path")', version_bridge)
        self.assertIn("open_in_editor(str(file_path), preferences)", document_bridge)
        self.assertIn("setTooltipText(element", editor_ui)
        self.assertIn('document.getElementById("editor-settings-card")', editor_ui)
        self.assertNotIn('if (byId("editor-settings-card"))', editor_ui)
        self.assertIn('document.getElementById("settings-user-content")', editor_ui)
        self.assertIn('document.getElementById("category-folders-card")', editor_ui)
        self.assertIn('categoryCard ? "afterend" : "afterbegin"', editor_ui)
        self.assertIn('editorState.platform !== "Darwin"', editor_ui)
        self.assertIn(".editor-path-control[hidden]", editor_css)
        self.assertIn('data-editor-tooltip-template="Open current version in {editor}"', picker)
        self.assertIn('addEventListener("click", () => controller.onOpenVSCode())', version_actions)


if __name__ == "__main__":
    unittest.main()
