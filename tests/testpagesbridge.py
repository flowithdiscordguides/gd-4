"""Regression coverage for efficient GitHub tag enrichment in the History modal."""

from __future__ import annotations

import unittest

from gitdesk.pages_bridge import github_tag_context


# FakeTagClient models only the authenticated request contract used by github_tag_context.
class FakeTagClient:
    """Return deterministic repository-tag pages while recording every requested endpoint."""

    # Stores page payloads so tests can assert both mapping accuracy and request count.
    def __init__(self, pages: dict[int, list[dict]]) -> None:
        """Initialize the client with page-number keyed GitHub response payloads."""

        self.pages = pages
        self.calls: list[tuple[str, str, dict]] = []

    # Returns one configured tag page and fails if production code reintroduces tag-object requests.
    def request(self, method: str, path: str, params: dict | None = None) -> list[dict]:
        """Record one request and return its configured repository-tags page."""

        request_params = dict(params or {})
        self.calls.append((method, path, request_params))
        if path != "/repos/octocat/example/tags":
            raise AssertionError(f"Unexpected History tag endpoint: {path}")
        return self.pages.get(int(request_params.get("page") or 1), [])


# HistoryTagContextTests guards the network-call shape that keeps History responsive.
class HistoryTagContextTests(unittest.TestCase):
    """Verify tag-to-commit enrichment without one request per annotated tag."""

    # Confirms one repository-tags response maps every tag directly to its target commit.
    def test_tag_context_uses_one_request_for_up_to_one_hundred_tags(self) -> None:
        """Map lightweight and annotated tag rows without requesting individual Git tag objects."""

        client = FakeTagClient({
            1: [
                {"name": "v0.0.1", "commit": {"sha": "ABC123"}},
                {"name": "release-candidate", "commit": {"sha": "DEF456"}},
            ],
        })

        context = github_tag_context(client, "octocat", "example")

        self.assertEqual(context["by_commit"]["abc123"], ["v0.0.1"])
        self.assertEqual(context["by_commit"]["def456"], ["release-candidate"])
        self.assertEqual(context["next_tag"], "v0.0.2")
        self.assertEqual(len(client.calls), 1)

    # Confirms repositories with more than one hundred tags still retain complete version context.
    def test_tag_context_follows_repository_tag_pages(self) -> None:
        """Request the next page only when GitHub fills the current one hundred-row page."""

        first_page = [
            {"name": f"build-{index}", "commit": {"sha": f"sha-{index}"}}
            for index in range(100)
        ]
        client = FakeTagClient({
            1: first_page,
            2: [{"name": "v1.2.3", "commit": {"sha": "LATEST"}}],
        })

        context = github_tag_context(client, "octocat", "example")

        self.assertEqual(context["by_commit"]["latest"], ["v1.2.3"])
        self.assertEqual(context["next_tag"], "v1.2.4")
        self.assertEqual([call[2]["page"] for call in client.calls], [1, 2])


if __name__ == "__main__":
    unittest.main()
