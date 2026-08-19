"""Regression coverage for repository browser, editor, and ignore actions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gitdesk.errors import AppError
from gitdesk.repoactions import gitignore_pattern_for_path, open_external_url, open_in_vscode


# ExternalBrowserTests protects the validation and operating-system handoff used by published-site buttons.
class ExternalBrowserTests(unittest.TestCase):
    """Verify website targets are validated before the default browser receives them."""

    # Confirms an authoritative Pages-style HTTPS target reaches Python's browser service.
    @patch("gitdesk.repoactions.webbrowser.open", return_value=True)
    def test_https_site_opens_in_default_browser(self, browser_open) -> None:
        """Open a valid site URL in a new default-browser tab or window."""

        result = open_external_url("https://octocat.github.io/example/")

        self.assertEqual(result, {"url": "https://octocat.github.io/example/"})
        browser_open.assert_called_once_with("https://octocat.github.io/example/", new=2)

    # Confirms executable and credential-bearing URL forms never reach the operating system.
    @patch("gitdesk.repoactions.webbrowser.open")
    def test_unsafe_urls_are_rejected(self, browser_open) -> None:
        """Reject non-web schemes and embedded credentials before browser launch."""

        invalid_urls = [
            "javascript:alert(1)",
            "https://user:secret@example.com/",
            "https://example.com:notaport/",
            "https://[broken",
        ]

        for url in invalid_urls:
            with self.subTest(url=url), self.assertRaises(AppError) as raised:
                open_external_url(url)
            self.assertEqual(raised.exception.code, "EXTERNAL_URL_INVALID")
        browser_open.assert_not_called()

    # Confirms the UI receives a real error when the platform has no usable default browser.
    @patch("gitdesk.repoactions.webbrowser.open", return_value=False)
    def test_browser_launch_failure_is_reported(self, browser_open) -> None:
        """Raise an actionable error when Python cannot launch a browser."""

        with self.assertRaises(AppError) as raised:
            open_external_url("https://example.com/")

        self.assertEqual(raised.exception.code, "BROWSER_OPEN_FAILED")
        browser_open.assert_called_once_with("https://example.com/", new=2)


# RepositoryFolderOpenTests keeps native folder access independent from optional Git metadata.
class RepositoryFolderOpenTests(unittest.TestCase):
    """Verify the selected editor receives an existing managed directory."""

    # Confirms the editor can repair or inspect an existing saved folder whose Git metadata is unavailable.
    @patch("gitdesk.repoactions.open_in_editor")
    def test_editor_open_does_not_require_git_metadata(self, editor_open) -> None:
        """Open the selected directory without pre-validating it as a Git repository."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            editor_open.return_value = {"path": temporary_directory, "editor": "VS Code"}

            result = open_in_vscode(temporary_directory, {"editor": "vscode"})

        self.assertEqual(result["editor"], "VS Code")
        editor_open.assert_called_once_with(str(Path(temporary_directory).resolve()), {"editor": "vscode"})


# GitignoreActionTests protects the exact three reserved targets and ordinary-path ignore behavior.
class GitignoreActionTests(unittest.TestCase):
    """Verify ordinary files and folders remain eligible for .gitignore."""

    # Allows every ordinary path while protecting only the three exact repository-relative targets.
    def test_only_git_control_paths_are_protected(self) -> None:
        """Accept ordinary targets and reject .gitignore, root .git, and root .github."""

        self.assertEqual(gitignore_pattern_for_path(".codex/"), "/.codex/")
        self.assertEqual(gitignore_pattern_for_path("build/output.log"), "/build/output.log")
        self.assertEqual(gitignore_pattern_for_path(".git/config"), "/.git/config")
        self.assertEqual(gitignore_pattern_for_path(".github/workflows/check.yml"), "/.github/workflows/check.yml")
        self.assertEqual(gitignore_pattern_for_path("nested/.gitignore"), "/nested/.gitignore")
        for path in (".gitignore", ".git/", ".github/"):
            with self.subTest(path=path), self.assertRaises(AppError) as raised:
                gitignore_pattern_for_path(path)
            self.assertEqual(raised.exception.code, "GITIGNORE_PATH_PROTECTED")

    # Confirms successful ignore handling purges the ignored target before applying refreshed status.
    def test_frontend_removes_ignored_paths_before_status_refresh(self) -> None:
        """Require ignored folders and descendants to leave the commit selection immediately."""

        source_path = Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "ui" / "overview.js"
        source = source_path.read_text(encoding="utf-8")
        remove_call = source.index("state.selectedFiles = withoutIgnoredPath(state.selectedFiles, filePath);")
        status_call = source.index("applyStatus(data.status);", remove_call)

        self.assertLess(remove_call, status_call)


if __name__ == "__main__":
    unittest.main()
