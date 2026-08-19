"""Regression coverage for operation-aware artifact-only Stage 3 GitHub failures."""

from __future__ import annotations

from io import BytesIO
import unittest
from unittest.mock import Mock

from gitdesk.errors import AppError
from gitdesk.githubreleaseassets import ReleaseAssetTransport, destination_asset_matches, release_assets
from gitdesk.githubreleaseerrors import delete_destination_release_asset, validate_release_repositories
from gitdesk.syncreleaseresolution import destination_release_for_tag
from gitdesk.syncreleasepublication import prepare_destination_draft, publish_destination_release


# MissingResponse models GitHub's message-free binary 404 response.
class MissingResponse:
    """Expose the response contract used by release-asset transfer code."""

    def __init__(self) -> None:
        self.headers = {}
        self.status_code = 404
        self.closed = False

    def __enter__(self) -> "MissingResponse":
        return self

    def __exit__(self, exception_type, exception, traceback) -> bool:
        return False

    def close(self) -> None:
        self.closed = True


# StageThreeRepositoryErrorTests protects independent owner-PAT diagnostics.
class StageThreeRepositoryErrorTests(unittest.TestCase):
    """Verify repository preflight identifies the failing Stage 3 owner boundary."""

    def test_source_repository_404_names_public_beta_read_requirement(self) -> None:
        """Map source invisibility to the Public Beta profile and Contents read."""

        source_client = Mock()
        destination_client = Mock()
        source_client.repository.side_effect = AppError("Not Found", "GITHUB_API_FAILED", {"status": 404})

        with self.assertRaises(AppError) as raised:
            validate_release_repositories(
                source_client,
                destination_client,
                ("beta-owner", "app-beta"),
                ("public-owner", "app"),
            )

        self.assertEqual(raised.exception.code, "SYNC_RELEASE_SOURCE_REPOSITORY_UNAVAILABLE")
        self.assertEqual(raised.exception.details["operation"], "repository_access")
        self.assertEqual(raised.exception.details["required_permissions"], ["contents:read"])
        self.assertIn("beta-owner/app-beta", raised.exception.message)
        destination_client.repository.assert_not_called()

    def test_destination_repository_404_names_public_write_requirement(self) -> None:
        """Map destination invisibility to the Public profile and Contents write."""

        source_client = Mock()
        destination_client = Mock()
        source_client.repository.return_value = {"private": False}
        destination_client.repository.side_effect = AppError("Not Found", "GITHUB_API_FAILED", {"status": 404})

        with self.assertRaises(AppError) as raised:
            validate_release_repositories(
                source_client,
                destination_client,
                ("beta-owner", "app-beta"),
                ("public-owner", "app"),
            )

        self.assertEqual(raised.exception.code, "SYNC_RELEASE_DESTINATION_REPOSITORY_UNAVAILABLE")
        self.assertEqual(raised.exception.details["required_permissions"], ["contents:write"])
        self.assertIn("public-owner/app", raised.exception.message)


# StageThreeReleaseMutationErrorTests protects release-write permission guidance.
class StageThreeReleaseMutationErrorTests(unittest.TestCase):
    """Verify release 404s explain GitHub's required Public PAT permissions."""

    def test_release_draft_404_requires_contents_and_workflows_write(self) -> None:
        """Translate GitHub's release-creation 404 without exposing request secrets."""

        client = Mock()
        client.request.side_effect = AppError("HTTP 404", "GITHUB_API_FAILED", {"status": 404})

        with self.assertRaises(AppError) as raised:
            prepare_destination_draft(
                client,
                ("public-owner", "app"),
                {"tag_name": "v1.0.0", "name": "v1.0.0", "body": ""},
                None,
            )

        self.assertEqual(raised.exception.code, "SYNC_RELEASE_DESTINATION_PERMISSION_REQUIRED")
        self.assertEqual(raised.exception.details["operation"], "create_release_draft")
        self.assertEqual(
            raised.exception.details["required_permissions"],
            ["contents:write", "workflows:write"],
        )
        self.assertIn("Settings > GitHub Settings", raised.exception.message)

    def test_non_404_release_failure_keeps_original_error(self) -> None:
        """Preserve existing GitHub semantics outside the confirmed ambiguous 404 class."""

        client = Mock()
        original = AppError("Validation failed", "GITHUB_API_FAILED", {"status": 422})
        client.request.side_effect = original

        with self.assertRaises(AppError) as raised:
            prepare_destination_draft(
                client,
                ("public-owner", "app"),
                {"tag_name": "v1.0.0", "name": "v1.0.0", "body": ""},
                None,
            )

        self.assertIs(raised.exception, original)

    def test_publication_confirmation_404_retains_operation(self) -> None:
        """Distinguish successful mutation follow-up from the publish request itself."""

        client = Mock()
        client.request.side_effect = [
            {"id": 7, "tag_name": "v1.0.0"},
            AppError("HTTP 404", "GITHUB_API_FAILED", {"status": 404}),
        ]

        with self.assertRaises(AppError) as raised:
            publish_destination_release(
                client,
                ("public-owner", "app"),
                {"tag_name": "v1.0.0", "name": "v1.0.0", "body": ""},
                7,
            )

        self.assertEqual(raised.exception.details["operation"], "confirm_latest_release")
        self.assertEqual(raised.exception.code, "SYNC_RELEASE_PUBLICATION_UNCONFIRMED")
        self.assertEqual(raised.exception.details["required_permissions"], ["contents:read"])


# StageThreeAssetErrorTests protects source-download and Public-upload distinction.
class StageThreeAssetErrorTests(unittest.TestCase):
    """Verify message-free binary 404s retain their exact transfer direction."""

    def test_source_asset_download_404_names_contents_read(self) -> None:
        """Identify a listed Public Beta asset that cannot be downloaded."""

        client = Mock()
        client.token_expires_at = ""
        client.session.get.return_value = MissingResponse()

        with self.assertRaises(AppError) as raised:
            ReleaseAssetTransport(client).download(
                "beta-owner",
                "app-beta",
                {"id": 2, "size": 5},
                BytesIO(),
            )

        self.assertEqual(raised.exception.code, "SYNC_RELEASE_SOURCE_ASSET_UNAVAILABLE")
        self.assertEqual(raised.exception.details["operation"], "download_source_asset")
        self.assertEqual(raised.exception.details["required_permissions"], ["contents:read"])

    def test_destination_asset_upload_404_names_contents_write(self) -> None:
        """Identify a Public draft asset that cannot be uploaded."""

        client = Mock()
        client.token_expires_at = ""
        response = MissingResponse()
        client.session.post.return_value = response

        with self.assertRaises(AppError) as raised:
            ReleaseAssetTransport(client).upload(
                "public-owner",
                "app",
                7,
                {"name": "GitDesk.zip", "size": 5},
                BytesIO(b"build"),
            )

        self.assertTrue(response.closed)
        self.assertEqual(raised.exception.code, "SYNC_RELEASE_DESTINATION_ASSET_UNAVAILABLE")
        self.assertEqual(raised.exception.details["operation"], "upload_destination_asset")
        self.assertEqual(raised.exception.details["required_permissions"], ["contents:write"])

    def test_destination_asset_verification_404_names_contents_read(self) -> None:
        """Identify a Public artifact that disappears before fallback byte verification."""

        client = Mock()
        client.token_expires_at = ""
        client.session.get.return_value = MissingResponse()

        with self.assertRaises(AppError) as raised:
            destination_asset_matches(
                ReleaseAssetTransport(client),
                "public-owner",
                "app",
                {"id": 3, "size": 5},
                5,
                "sha256:" + "a" * 64,
            )

        self.assertEqual(raised.exception.code, "SYNC_RELEASE_DESTINATION_ASSET_UNAVAILABLE")
        self.assertEqual(raised.exception.details["operation"], "download_destination_asset")
        self.assertEqual(raised.exception.details["required_permissions"], ["contents:read"])

    def test_release_asset_list_404_retains_repository_context(self) -> None:
        """Identify release metadata that disappears before artifact reconciliation."""

        client = Mock()
        client.request.side_effect = AppError("HTTP 404", "GITHUB_API_FAILED", {"status": 404})

        with self.assertRaises(AppError) as raised:
            release_assets(client, "beta-owner", "app-beta", 7)

        self.assertEqual(raised.exception.code, "SYNC_RELEASE_ASSET_LIST_UNAVAILABLE")
        self.assertEqual(raised.exception.details["operation"], "list_release_assets")
        self.assertEqual(raised.exception.details["resource_owner"], "beta-owner")

    def test_stale_draft_asset_delete_404_names_contents_write(self) -> None:
        """Identify a failed Public draft cleanup without weakening exact-set safety."""

        client = Mock()
        client.request.side_effect = AppError("HTTP 404", "GITHUB_API_FAILED", {"status": 404})

        with self.assertRaises(AppError) as raised:
            delete_destination_release_asset(client, ("public-owner", "app"), 9)

        self.assertEqual(raised.exception.code, "SYNC_RELEASE_DESTINATION_ASSET_UNAVAILABLE")
        self.assertEqual(raised.exception.details["operation"], "delete_destination_asset")
        self.assertEqual(raised.exception.details["required_permissions"], ["contents:write"])

    def test_destination_release_list_404_names_public_repository(self) -> None:
        """Keep normal missing-tag lookup separate from failed Public release-list access."""

        client = Mock()
        client.request.side_effect = [
            AppError("Not Found", "GITHUB_API_FAILED", {"status": 404}),
            AppError("HTTP 404", "GITHUB_API_FAILED", {"status": 404}),
        ]

        with self.assertRaises(AppError) as raised:
            destination_release_for_tag(client, "public-owner", "app", "v1.0.0")

        self.assertEqual(raised.exception.code, "SYNC_RELEASE_DESTINATION_RELEASES_UNAVAILABLE")
        self.assertEqual(raised.exception.details["operation"], "list_destination_releases")
        self.assertEqual(raised.exception.details["resource_owner"], "public-owner")


if __name__ == "__main__":
    unittest.main()
