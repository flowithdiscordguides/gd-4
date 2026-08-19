"""Regression coverage for branch transport prerequisites in Repo Mode."""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from git import GitCommandError

from gitdesk.errors import AppError
from gitdesk.gitops import GitService
from gitdesk.gittransport import GIT_PUSH_TIMEOUT_SECONDS, push_git_command


# PullRepository models an active local branch whose matching origin ref has not been fetched.
class PullRepository:
    """Provide the minimum Git adapter used by the missing-remote-branch Pull guard."""

    # Creates an origin remote and active main branch without a fetched origin/main reference.
    def __init__(self) -> None:
        self.active_branch = mock.Mock(name="main")
        self.active_branch.name = "main"
        origin = mock.Mock()
        origin.name = "origin"
        origin.url = "https://github.com/example/repository.git"
        self.remotes = [origin]
        self.git = mock.Mock()
        self.git.rev_parse.side_effect = GitCommandError("git rev-parse", 128)
        self.head = mock.Mock()
        self.head.commit = mock.Mock(hexsha="a" * 40)


# GitTransportTests protects empty-clone Pull behavior before the repository's first push.
class GitTransportTests(unittest.TestCase):
    """Verify Pull requires a fetched origin branch instead of guessing a remote ref."""

    # Confirms an empty remote produces an actionable app error without starting authentication or pull.
    def test_pull_rejects_missing_fetched_origin_branch(self) -> None:
        """Reject Pull before invoking the network command when origin/main does not exist locally."""

        repository = PullRepository()
        with mock.patch("gitdesk.gitops.open_repository", return_value=repository):
            with self.assertRaises(AppError) as raised:
                GitService().pull("/repository", "example")

        self.assertEqual(raised.exception.code, "GIT_REMOTE_BRANCH_MISSING")
        self.assertEqual(raised.exception.details, {"branch": "main"})
        repository.git.pull.assert_not_called()

    # Confirms the missing remote ref guard never blocks the first push that creates that branch.
    def test_push_allows_missing_fetched_origin_branch(self) -> None:
        """Push the local branch without requiring origin/main to exist first."""

        repository = PullRepository()
        service = GitService()
        service.status = mock.Mock(return_value={"files": [], "summary": {"changed": 0}})
        with mock.patch("gitdesk.gitops.open_repository", return_value=repository), mock.patch(
            "gitdesk.gitops.push_git_command",
            return_value="",
        ) as push_command:
            result = service.push("/repository")

        repository.git.rev_parse.assert_not_called()
        push_command.assert_called_once()
        self.assertEqual(result["head_sha"], "a" * 40)

    # Confirms the backend child process settles before JavaScript's push-specific native deadline.
    def test_push_timeout_reports_ambiguous_remote_state(self) -> None:
        """Stop an unresponsive Git child while preserving explicit retry guidance."""

        repository = PullRepository()
        repository.working_tree_dir = "/repository"
        timeout = subprocess.TimeoutExpired(["git", "push"], GIT_PUSH_TIMEOUT_SECONDS)
        with mock.patch("gitdesk.gittransport.subprocess.run", side_effect=timeout):
            with self.assertRaises(AppError) as raised:
                push_git_command(repository, "origin", "main:main", {})

        self.assertEqual(raised.exception.code, "GIT_PUSH_TIMEOUT")
        self.assertEqual(raised.exception.details["remote_state"], "unknown")
        self.assertIn(f"after {GIT_PUSH_TIMEOUT_SECONDS} seconds", raised.exception.message)
        native_source = (
            Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "ui" / "native.js"
        ).read_text(encoding="utf-8")
        timeout_match = re.search(r"const GIT_PUSH_REQUEST_TIMEOUT_MS = (\d+);", native_source)
        self.assertIsNotNone(timeout_match)
        native_timeout_ms = int(timeout_match.group(1)) if timeout_match else 0
        self.assertLess(GIT_PUSH_TIMEOUT_SECONDS * 1000, native_timeout_ms)
        self.assertIn('action === "push"', native_source)
        self.assertIn('action === "commit" && payload && payload.push', native_source)

    # Confirms Overview disables Pull from syncStatus while preserving Fetch for remote discovery.
    def test_overview_requires_upstream_before_enabling_pull(self) -> None:
        """Require the frontend to bind Pull availability to the fetched-upstream state."""

        source_path = Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "ui" / "overview.js"
        source = source_path.read_text(encoding="utf-8")

        self.assertIn("state.pullAvailable = Boolean(sync && sync.has_upstream);", source)
        self.assertIn('byId("pull-button").disabled = noRepository || !state.pullAvailable;', source)


if __name__ == "__main__":
    unittest.main()
