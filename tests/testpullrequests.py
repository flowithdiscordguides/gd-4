"""Regression coverage for selected-repository Pull Request and review workflows."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from gitdesk.errors import AppError
from gitdesk.frontend import INLINE_SCRIPTS, INLINE_STYLES
from gitdesk.pullrequest_bridge import handle_list_pull_requests
from gitdesk.pullrequests import create_pull_request, merge_pull_request, submit_pull_request_review


# RecordingClient captures exact GitHub REST requests without using the network.
class RecordingClient:
    """Return a configured response and retain method, path, and payload evidence."""

    # Initializes one response and an empty request ledger.
    def __init__(self, response: dict) -> None:
        self.response = response
        self.requests = []

    # Records one API request in the shape used by GitHubApiClient.
    def request(self, method: str, path: str, **kwargs):
        """Return the configured response after recording the exact call."""

        self.requests.append((method, path, kwargs))
        return self.response


# PullRequestTests protects owner routing, mutation validation, permissions, and asset delivery.
class PullRequestTests(unittest.TestCase):
    """Verify Pull Requests use one selected repository context and explicit review decisions."""

    # Confirms creation sends only bounded explicit Pull Request fields to the selected repository endpoint.
    def test_create_pull_request_uses_exact_repository_and_fields(self) -> None:
        """Create a draft Pull Request with explicit head, base, title, and body."""

        client = RecordingClient({
            "number": 7,
            "title": "Ship it",
            "head": {"ref": "feature"},
            "base": {"ref": "main"},
        })

        created = create_pull_request(client, "octocat", "hello-world", {
            "title": "Ship it",
            "body": "Review this change.",
            "head": "feature",
            "base": "main",
            "draft": True,
        })

        method, path, arguments = client.requests[0]
        self.assertEqual((method, path), ("POST", "/repos/octocat/hello-world/pulls"))
        self.assertEqual(arguments["json_body"]["head"], "feature")
        self.assertEqual(arguments["json_body"]["base"], "main")
        self.assertTrue(arguments["json_body"]["draft"])
        self.assertEqual(created["number"], 7)

    # Confirms review and merge values cannot escape GitHub's supported enumerations.
    def test_review_and_merge_require_supported_decisions(self) -> None:
        """Reject invented review events and merge strategies before an API request."""

        client = RecordingClient({})
        with self.assertRaises(AppError) as review_error:
            submit_pull_request_review(client, "octocat", "repo", 3, "dismiss", "")
        with self.assertRaises(AppError) as merge_error:
            merge_pull_request(client, "octocat", "repo", 3, "overwrite")

        self.assertEqual(review_error.exception.code, "PULL_REQUEST_REVIEW_INVALID")
        self.assertEqual(merge_error.exception.code, "PULL_REQUEST_MERGE_METHOD_INVALID")
        self.assertEqual(client.requests, [])

    # Confirms owner/repository resolution and PAT routing receive the same selected-path payload.
    @patch("gitdesk.pullrequest_bridge.pullrequests.list_pull_requests")
    def test_bridge_uses_one_payload_for_pair_and_client(self, list_pulls: Mock) -> None:
        """Resolve the selected repository origin and owner-keyed client from the identical payload."""

        payload = {"repository_path": "/repos/alpha", "account_login": "octocat"}
        controller = Mock()
        controller.github_pair_from_payload.return_value = ("octocat", "alpha")
        client = object()
        controller.github_client.return_value = client
        list_pulls.return_value = {"pull_requests": []}

        result = handle_list_pull_requests(controller, payload)

        controller.github_pair_from_payload.assert_called_once_with(payload)
        controller.github_client.assert_called_once_with(payload)
        list_pulls.assert_called_once_with(client, "octocat", "alpha")
        self.assertEqual(result, {"pull_requests": []})

    # Confirms UI delivery and the official fine-grained repository permission stay wired together.
    def test_pull_request_assets_and_pat_permission_are_delivered(self) -> None:
        """Package the review UI and request Pull requests write permission."""

        accounts = (
            Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "ui" / "accounts.js"
        ).read_text(encoding="utf-8")

        self.assertIn("pull-requests.css", INLINE_STYLES)
        self.assertLess(
            INLINE_SCRIPTS.index("pull-requests-ui.js"),
            INLINE_SCRIPTS.index("pull-requests.js"),
        )
        self.assertIn('pull_requests: "write"', accounts)


if __name__ == "__main__":
    unittest.main()
