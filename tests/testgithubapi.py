"""Regression coverage for GitHub authentication failure reporting."""

from __future__ import annotations

# Standard-library test tools replace the HTTP request boundary deterministically.
import unittest
from unittest.mock import Mock

# Requests supplies the real response object shape consumed by GitHubApiClient.
from requests import Response

# GitDesk classes under test expose the structured authentication error contract.
from gitdesk.errors import AppError
from gitdesk.githubapi import GitHubApiClient


# GitHubAuthenticationTests isolates HTTP responses so token errors are verified without network access.
class GitHubAuthenticationTests(unittest.TestCase):
    """Verify GitHub's 401 response is distinguished from storage and permission failures."""

    # Builds the exact response shape returned when GitHub rejects an invalid, expired, or revoked PAT.
    def test_unauthorized_response_reports_rejected_pat(self) -> None:
        """Return GITHUB_TOKEN_REJECTED with HTTP status details for a 401 response."""

        response = Response()
        response.status_code = 401
        response._content = b'{"message":"Bad credentials"}'
        client = GitHubApiClient("invalid-test-token")
        client.session.request = Mock(return_value=response)

        with self.assertRaises(AppError) as raised:
            client.current_user()

        self.assertEqual(raised.exception.code, "GITHUB_TOKEN_REJECTED")
        self.assertEqual(raised.exception.details, {"status": 401})
        self.assertIn("invalid, expired, or revoked", raised.exception.message)

    # Confirms the explicit PAT resource owner is resolved independently from the authenticated user endpoint.
    def test_resource_owner_returns_canonical_organization_identity(self) -> None:
        """Resolve an organization login and type from GitHub's public user-or-organization endpoint."""

        response = Response()
        response.status_code = 200
        response._content = (
            b'{"login":"xandland","type":"Organization","html_url":"https://github.com/xandland"}'
        )
        client = GitHubApiClient("organization-test-token")
        client.session.request = Mock(return_value=response)

        owner = client.resource_owner("xandland")

        self.assertEqual(owner["login"], "xandland")
        self.assertEqual(owner["type"], "Organization")
        self.assertEqual(owner["html_url"], "https://github.com/xandland")

    # Captures GitHub's documented non-secret PAT expiration header for account metadata and Settings display.
    def test_authenticated_response_records_token_expiration(self) -> None:
        """Normalize the GitHub expiration header without exposing the submitted PAT."""

        response = Response()
        response.status_code = 200
        response._content = b'{"login":"octocat","id":1}'
        response.headers["GitHub-Authentication-Token-Expiration"] = "2026-08-21 04:00:00 UTC"
        client = GitHubApiClient("expiration-test-token")
        client.session.request = Mock(return_value=response)

        client.current_user()

        self.assertEqual(client.token_expires_at, "2026-08-21T04:00:00Z")


if __name__ == "__main__":
    unittest.main()
