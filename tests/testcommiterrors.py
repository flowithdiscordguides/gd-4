"""Regression coverage for actionable commit and staging diagnostics."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from git import GitCommandError

from gitdesk.errors import AppError
from gitdesk.gitops import GitService


# FailingGit records the requested stage command and returns Git's concrete failure output.
class FailingGit:
    """Provide the Git command methods reached before commit creation."""

    # Reports the selected file as current so the fixture reaches its intended staging failure.
    def status(self, *arguments: str) -> str:
        """Return one untracked porcelain record for the selected file."""

        return "?? file.txt\0"

    # Raises the same structured command error GitPython returns when staging fails.
    def add(self, *arguments: str) -> None:
        """Fail staging with a diagnostic that must cross the native bridge."""

        raise GitCommandError("git add", 128, stderr="fatal: Unable to create '.git/index.lock': File exists.")


# FailingRepository provides only the Git command adapter required by GitService.commit.
class FailingRepository:
    """Represent an opened repository whose staging command fails."""

    git = FailingGit()

    # Reports no ignored paths so this fixture reaches the intended staging failure boundary.
    def ignored(self, *paths: str) -> list[str]:
        """Return no ignored paths for the selected stage-error fixture."""

        return []


# SelectiveIgnoreRepository reports one stale ignored selection and records the paths staged after filtering.
class SelectiveIgnoreRepository:
    """Provide the ignored-path and successful commit behavior used by the staging safeguard."""

    # Creates native Git command results for a successful first commit without touching a real repository.
    def __init__(self) -> None:
        self.git = mock.Mock()
        self.git.status.return_value = "?? .codex/\0?? .gitignore\0"
        self.git.diff.return_value = ".gitignore"
        self.git.rev_parse.side_effect = GitCommandError("git rev-parse", 128)
        self.git.write_tree.return_value = "b" * 40
        self.git.commit_tree.return_value = "a" * 40
        self.head = mock.Mock()
        self.head.commit = mock.Mock(hexsha="a" * 40, message="Ignore .codex")

    # Mirrors Git check-ignore output for the stale .codex folder selection.
    def ignored(self, *paths: str) -> list[str]:
        """Return only the ignored folder while leaving .gitignore stageable."""

        return [".codex"]


# CommitErrorTests protects both visible and structured diagnostic output.
class CommitErrorTests(unittest.TestCase):
    """Verify staging failures retain Git's safe reason for the frontend."""

    # Confirms commit staging no longer replaces Git stderr with a generic sentence.
    def test_stage_failure_preserves_git_reason_and_details(self) -> None:
        """Return sanitized Git output in the AppError message and details."""

        service = GitService()
        service.status = mock.Mock(return_value={
            "files": [{"path": "file.txt"}],
            "summary": {"changed": 1},
        })
        with mock.patch("gitdesk.gitops.open_repository", return_value=FailingRepository()):
            with self.assertRaises(AppError) as raised:
                service.commit("/repository", "Update file", ["file.txt"])

        error = raised.exception
        self.assertEqual(error.code, "GIT_STAGE_FAILED")
        self.assertIn("Unable to create '.git/index.lock'", error.message)
        self.assertIn("Unable to create '.git/index.lock'", error.details["git_output"])

    # Protects the in-app console transcript from collapsing Error objects to stack-only text.
    def test_devtools_error_capture_includes_code_and_details(self) -> None:
        """Require copied DevTools output to retain structured native error fields."""

        script = Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "ui" / "debug.js"
        source = script.read_text(encoding="utf-8")

        self.assertIn('fields.push(`Code: ${value.code}`);', source)
        self.assertIn('fields.push(`Details: ${JSON.stringify(value.details)}`);', source)

    # Confirms a stale ignored selection cannot block staging of remaining selected changes.
    def test_commit_filters_ignored_paths_before_staging(self) -> None:
        """Stage .gitignore without passing the newly ignored .codex folder to git add."""

        repository = SelectiveIgnoreRepository()
        service = GitService()
        service.status = mock.Mock(return_value={
            "files": [{"path": ".codex/"}, {"path": ".gitignore"}],
            "summary": {"changed": 2},
        })
        with mock.patch("gitdesk.gitops.open_repository", return_value=repository):
            result = service.commit(
                "/repository",
                "Ignore .codex",
                [".codex/", ".gitignore"],
                account={"name": "Example User", "email": "user@example.com"},
            )

        repository.git.add.assert_called_once_with("-A", "--", ".gitignore")
        repository.git.commit_tree.assert_called_once()
        repository.git.update_ref.assert_called_once()
        commit_environment = repository.git.commit_tree.call_args.kwargs["env"]
        self.assertEqual(commit_environment["GIT_AUTHOR_EMAIL"], "user@example.com")
        self.assertEqual(commit_environment["GIT_COMMITTER_EMAIL"], "user@example.com")
        self.assertEqual(result["short_sha"], "aaaaaaa")

    # Confirms a serialized repeat request drops paths no longer present after the first commit.
    def test_commit_treats_fully_stale_selection_as_noop(self) -> None:
        """Return refreshed status without invoking git add for an already-consumed selection."""

        repository = SelectiveIgnoreRepository()
        service = GitService()
        current_status = {"files": [], "summary": {"changed": 0}}
        service.status = mock.Mock(return_value=current_status)
        repository.git.status.return_value = ""
        with mock.patch("gitdesk.gitops.open_repository", return_value=repository):
            result = service.commit("/repository", "Old request", [".github/workflows/build-app.yml"])

        repository.git.add.assert_not_called()
        self.assertTrue(result["noop"])
        self.assertIs(result["status"], current_status)

    # Confirms a deleted path from a prior request cannot prevent another current selection from staging.
    def test_commit_drops_stale_path_and_stages_remaining_current_path(self) -> None:
        """Stage a current file while omitting a deleted workflow path from the same old selection."""

        repository = SelectiveIgnoreRepository()
        service = GitService()
        service.status = mock.Mock(return_value={
            "files": [{"path": ".gitignore"}],
            "summary": {"changed": 1},
        })
        repository.git.status.return_value = "?? .gitignore\0"
        with mock.patch("gitdesk.gitops.open_repository", return_value=repository):
            result = service.commit(
                "/repository",
                "Update ignore rules",
                [".github/workflows/build-app.yml", ".gitignore"],
            )

        repository.git.add.assert_called_once_with("-A", "--", ".gitignore")
        self.assertEqual(result["short_sha"], "aaaaaaa")

    # Protects commit-and-push from full-tree scans before staging and after the nested push response.
    def test_commit_push_reuses_authoritative_push_status(self) -> None:
        """Use targeted pre-commit status and return the authoritative nested push status."""

        repository = SelectiveIgnoreRepository()
        current_status = {"files": [{"path": ".gitignore"}], "summary": {"changed": 1}}
        pushed_status = {"files": [], "summary": {"changed": 0}}
        service = GitService()
        service.status = mock.Mock(return_value=current_status)
        service.push = mock.Mock(return_value={"status": pushed_status, "head_sha": "a" * 40})
        with mock.patch("gitdesk.gitops.open_repository", return_value=repository):
            result = service.commit("/repository", "Ignore .codex", [".gitignore"], push_after=True)

        self.assertEqual(service.status.call_count, 0)
        repository.git.status.assert_called_once_with(
            "--porcelain=v1", "-z", "--untracked-files=all", "--", ".gitignore",
        )
        self.assertIs(result["status"], pushed_status)

    # Confirms a bulk initial commit avoids one giant pathspec and stages the proven all-current tree once.
    def test_bulk_commit_uses_full_status_and_single_root_stage(self) -> None:
        """Use one complete freshness scan and one root stage when every current path is selected."""

        repository = SelectiveIgnoreRepository()
        selected_paths = [f"project/generated-file-{index:04d}.txt" for index in range(500)]
        repository.git.status.return_value = "".join(f"?? {path}\0" for path in selected_paths)
        repository.git.diff.return_value = "\n".join(selected_paths)
        service = GitService()
        service.status = mock.Mock(return_value={"files": [], "summary": {"changed": 0}})
        with mock.patch("gitdesk.gitops.open_repository", return_value=repository):
            result = service.commit("/repository", "Initial project import", selected_paths)

        repository.git.status.assert_called_once_with("--porcelain=v1", "-z", "--untracked-files=all")
        repository.git.add.assert_called_once_with("-A", "--", ".")
        self.assertEqual(result["short_sha"], "aaaaaaa")

    # Protects the frontend against duplicate clicks and false success messages for stale no-op responses.
    def test_frontend_serializes_commit_interaction_and_handles_noop(self) -> None:
        """Require a running guard, disabled controls, and explicit no-op status refresh behavior."""

        script = Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "ui" / "overview.js"
        source = script.read_text(encoding="utf-8")

        self.assertIn("if (state.commitRunning) return;", source)
        self.assertIn("state.commitRunning || noRepository", source)
        self.assertIn("if (data.noop)", source)
        self.assertIn("applyStatus(data.status);", source[source.index("if (data.noop)"):])


if __name__ == "__main__":
    unittest.main()
