"""Regression coverage for metadata-fast Stage 3 artifact verification."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from gitdesk import syncrelease
from gitdesk.githubreleaseassets import ASSET_TRANSFER_TIMEOUT


class SyncChainArtifactVerificationTests(unittest.TestCase):
    """Keep matching release checks byte-free without weakening digest fallbacks."""

    def test_binary_transfer_fails_after_bounded_read_inactivity(self) -> None:
        """Prevent a stalled asset stream from retaining Stage 3 busy state for minutes."""

        self.assertEqual(ASSET_TRANSFER_TIMEOUT, (15, 30))

    def asset(self, identifier: int, digest: str = "") -> dict:
        """Return one uploaded release asset with optional authenticated digest metadata."""

        return {
            "id": identifier,
            "name": "GitDesk.zip",
            "size": 4096,
            "state": "uploaded",
            "digest": digest,
        }

    @patch("gitdesk.syncrelease.ReleaseAssetTransport")
    @patch("gitdesk.syncrelease.release_assets")
    def test_matching_published_digests_require_no_asset_download(
        self,
        release_assets: Mock,
        transport_class: Mock,
    ) -> None:
        """Verify an idempotent published release entirely from exact GitHub metadata."""

        digest = "sha256:" + "a" * 64
        release_assets.side_effect = [[self.asset(1, digest)], [self.asset(2, digest)]]
        source_transport = Mock()
        destination_transport = Mock()
        transport_class.side_effect = [source_transport, destination_transport]

        verified, total_bytes = syncrelease.verify_published_assets(
            Mock(),
            Mock(),
            ("private-owner", "app-beta"),
            ("public-owner", "app"),
            {"id": 10},
            {"id": 20},
        )

        self.assertEqual(verified, {"GitDesk.zip": digest})
        self.assertEqual(total_bytes, 4096)
        source_transport.download.assert_not_called()
        destination_transport.download.assert_not_called()

    @patch("gitdesk.syncrelease.ReleaseAssetTransport")
    @patch("gitdesk.syncrelease.release_assets")
    def test_matching_draft_digests_require_no_transfer(
        self,
        release_assets: Mock,
        transport_class: Mock,
    ) -> None:
        """Resume an already-complete draft without downloading, deleting, or uploading assets."""

        digest = "sha256:" + "b" * 64
        source = self.asset(1, digest)
        destination = self.asset(2, digest)
        release_assets.side_effect = [[source], [destination], [destination]]
        source_transport = Mock()
        destination_transport = Mock()
        transport_class.side_effect = [source_transport, destination_transport]
        destination_client = Mock()

        verified, total_bytes = syncrelease.synchronize_draft_assets(
            Mock(),
            destination_client,
            ("private-owner", "app-beta"),
            ("public-owner", "app"),
            {"id": 10},
            {"id": 20},
        )

        self.assertEqual(verified, {"GitDesk.zip": digest})
        self.assertEqual(total_bytes, 4096)
        source_transport.download.assert_not_called()
        destination_transport.download.assert_not_called()
        destination_transport.upload.assert_not_called()
        destination_client.request.assert_not_called()

    @patch("gitdesk.syncrelease.ReleaseAssetTransport")
    @patch("gitdesk.syncrelease.release_assets")
    def test_missing_source_digest_keeps_byte_hash_fallback(
        self,
        release_assets: Mock,
        transport_class: Mock,
    ) -> None:
        """Hash source bytes when GitHub cannot supply trustworthy digest metadata."""

        digest = "sha256:" + "c" * 64
        release_assets.side_effect = [[self.asset(1)], [self.asset(2, digest)]]
        source_transport = Mock()
        source_transport.download.return_value = digest
        destination_transport = Mock()
        transport_class.side_effect = [source_transport, destination_transport]

        verified, _total_bytes = syncrelease.verify_published_assets(
            Mock(),
            Mock(),
            ("private-owner", "app-beta"),
            ("public-owner", "app"),
            {"id": 10},
            {"id": 20},
        )

        self.assertEqual(verified, {"GitDesk.zip": digest})
        source_transport.download.assert_called_once()
        destination_transport.download.assert_not_called()


if __name__ == "__main__":
    unittest.main()
