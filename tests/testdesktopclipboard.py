"""Regression coverage for GitDesk's app-owned text and native-file clipboard boundaries."""

from __future__ import annotations

from pathlib import Path
import subprocess
import unittest
from unittest import mock

from gitdesk.desktop_clipboard import (
    MAX_CLIPBOARD_TEXT_CHARACTERS,
    bounded_clipboard_text,
    linux_file_clipboard_payload,
    read_macos_clipboard_file_urls,
    read_macos_clipboard_text,
    write_macos_clipboard_files,
    write_windows_clipboard_files,
)
from gitdesk.errors import AppError


# DesktopClipboardTests isolates OS process reads while preserving exact commands and bridge-facing results.
class DesktopClipboardTests(unittest.TestCase):
    """Verify bounded text, file-list writers, and dependency-free macOS fallbacks."""

    # Confirms normal text comes from the OS pasteboard utility rather than the browser clipboard API.
    @mock.patch("gitdesk.desktop_clipboard.subprocess.run")
    def test_macos_text_reader_uses_builtin_pbpaste(self, run: mock.Mock) -> None:
        """Return multiline UTF-8 text from macOS' fixed clipboard command."""

        run.return_value = subprocess.CompletedProcess([], 0, "one\ntwo".encode(), b"")

        result = read_macos_clipboard_text()

        self.assertEqual(result, "one\ntwo")
        self.assertEqual(run.call_args.args[0], ["/usr/bin/pbpaste"])
        self.assertNotIn("shell", run.call_args.kwargs)

    # Confirms copied Finder paths still work when an editable source checkout has no PyObjC installation.
    @mock.patch("gitdesk.desktop_clipboard.read_macos_file_urls_with_appkit", return_value=None)
    @mock.patch("gitdesk.desktop_clipboard.subprocess.run")
    def test_macos_file_reader_falls_back_to_system_jxa(
        self,
        run: mock.Mock,
        appkit_reader: mock.Mock,
    ) -> None:
        """Decode multiple Finder file URLs from the built-in JXA bridge."""

        run.return_value = subprocess.CompletedProcess(
            [],
            0,
            b'["/Users/person/One.png","/Users/person/Two.jpg"]\n',
            b"",
        )

        paths = read_macos_clipboard_file_urls()

        self.assertEqual(paths, ["/Users/person/One.png", "/Users/person/Two.jpg"])
        self.assertEqual(run.call_args.args[0][:3], ["/usr/bin/osascript", "-l", "JavaScript"])
        appkit_reader.assert_called_once_with()

    # Confirms oversized clipboard text never crosses into the embedded frontend as one unbounded response.
    def test_clipboard_text_has_a_native_bridge_ceiling(self) -> None:
        """Reject clipboard text above the shared bridge limit."""

        with self.assertRaises(AppError) as raised:
            bounded_clipboard_text("x" * (MAX_CLIPBOARD_TEXT_CHARACTERS + 1))

        self.assertEqual(raised.exception.code, "CLIPBOARD_TEXT_TOO_LARGE")

    # Confirms macOS writes NSURL pasteboard objects through JXA when source PyObjC is unavailable.
    @mock.patch("gitdesk.desktop_clipboard.run_clipboard_writer")
    @mock.patch("gitdesk.desktop_clipboard.write_macos_files_with_appkit", return_value=None)
    def test_macos_file_writer_falls_back_to_system_jxa(
        self,
        appkit_writer: mock.Mock,
        command_writer: mock.Mock,
    ) -> None:
        """Pass exact file paths as arguments to the fixed AppKit JXA writer."""

        paths = ["/Users/person/One.png", "/Users/person/Two.jpg"]

        write_macos_clipboard_files(paths)

        command = command_writer.call_args.args[0]
        self.assertEqual(command[:3], ["/usr/bin/osascript", "-l", "JavaScript"])
        self.assertEqual(command[-2:], paths)
        appkit_writer.assert_called_once_with(paths)

    # Confirms Windows receives literal file paths over stdin rather than interpolated PowerShell source.
    @mock.patch("gitdesk.desktop_clipboard.run_clipboard_writer")
    @mock.patch("gitdesk.desktop_clipboard.shutil.which", return_value="powershell.exe")
    def test_windows_file_writer_uses_literal_path_json(
        self,
        find_executable: mock.Mock,
        command_writer: mock.Mock,
    ) -> None:
        """Send the file list to the fixed STA clipboard command as JSON stdin."""

        paths = [r"C:\Media\One image.png"]

        write_windows_clipboard_files(paths)

        command, payload = command_writer.call_args.args
        self.assertIn("-STA", command)
        self.assertIn("Set-Clipboard -LiteralPath $paths", command[-1])
        self.assertEqual(payload, b'["C:\\\\Media\\\\One image.png"]')
        find_executable.assert_called_once_with("powershell.exe")

    # Confirms Linux advertises copy, not cut, for file-aware GNOME paste targets.
    @mock.patch.dict("gitdesk.desktop_clipboard.os.environ", {"XDG_CURRENT_DESKTOP": "GNOME"}, clear=True)
    def test_linux_file_payload_uses_gnome_copy_target(self) -> None:
        """Encode an absolute file URI with the explicit GNOME copy operation marker."""

        mime_type, payload = linux_file_clipboard_payload(["/home/person/One image.png"])

        self.assertEqual(mime_type, "x-special/gnome-copied-files")
        self.assertEqual(payload, b"copy\nfile:///home/person/One%20image.png")

    # Protects shortcut, right-click, and bridge registration from returning to WebView-native paste.
    def test_frontend_and_bridge_own_text_paste(self) -> None:
        """Require one app-owned editable Paste action and one native read route."""

        project_root = Path(__file__).resolve().parents[1]
        editing = (project_root / "src" / "gitdesk" / "ui" / "editing.js").read_text(encoding="utf-8")
        bridge = (project_root / "src" / "gitdesk" / "bridge.py").read_text(encoding="utf-8")

        self.assertIn("isPasteShortcut(event)", editing)
        self.assertIn('bridge.callNative("readClipboardText", {})', editing)
        self.assertIn("setRangeText", editing)
        self.assertEqual(editing.count('label: "Paste"'), 1)
        self.assertIn("desktop_clipboard_handlers(self)", bridge)


if __name__ == "__main__":
    unittest.main()
