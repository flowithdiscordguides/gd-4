"""Hard regression boundary for source-free final Sync Chain publication."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from gitdesk import syncchain_bridge


# ArtifactOnlyBoundaryTests forbids the enabled final edge from entering filesystem mirroring.
class ArtifactOnlyBoundaryTests(unittest.TestCase):
    """Protect the release-assets-only branch from source-tree synchronization."""

    # Builds the stable final-edge context normally resolved from saved Sync Chain metadata.
    def context(self) -> dict:
        """Return one enabled Public Beta-to-Public release context."""

        return {
            "chain": {"public_artifacts_only": True, "project_path": "/projects/app"},
            "edge_name": "public_beta_to_public",
            "source_path": "/repos/public-beta",
            "source_account_login": "private-profile",
            "source_repository": {"owner": "private-owner", "repo": "app-beta"},
            "destination_path": "/repos/public",
            "destination_account_login": "public-profile",
            "destination_repository": {"owner": "public-owner", "repo": "app"},
            "destination_label": "Public",
            "handoff_destination": True,
        }

    # Proves the checked final edge cannot start the source-working-tree transaction.
    @patch("gitdesk.syncchain_bridge.sync_state", return_value={"settings": {}, "sync": {}})
    @patch("gitdesk.syncchain_bridge.destination_repository_handoff", return_value=({}, {"stage": "Public"}))
    @patch("gitdesk.syncchain_bridge.syncchains.receipt_update", return_value={"sync_chains": []})
    @patch("gitdesk.syncchain_bridge.syncchains.edge_context")
    @patch("gitdesk.syncchain_bridge.promote_latest_release")
    @patch("gitdesk.syncchain_bridge.begin_mirror_transaction")
    def test_enabled_final_edge_avoids_mirror_and_local_git_handoff(
        self,
        begin_mirror: Mock,
        promote_release: Mock,
        edge_context: Mock,
        _receipt_update: Mock,
        destination_handoff: Mock,
        _sync_state: Mock,
    ) -> None:
        """Allow only release publication when Built artifacts only is enabled."""

        context = self.context()
        edge_context.return_value = context
        promote_release.return_value = {
            "release": {"id": 7, "tag_name": "v0.1.3", "draft": False},
            "receipt": {
                "destination_digest": "artifact-digest",
                "sync_mode": "release_artifacts",
                "release_tag": "v0.1.3",
            },
        }
        controller = Mock()
        controller.settings_store.load.return_value = {}
        controller.settings_store.save.return_value = {}

        result = syncchain_bridge.run_sync_edge_locked(
            controller,
            {},
            "chain",
            "public_beta_to_public",
            "",
        )

        begin_mirror.assert_not_called()
        promote_release.assert_called_once_with(controller, context, "", None)
        destination_handoff.assert_not_called()
        self.assertIsNone(result["repository_handoff"])
        self.assertEqual(result["sync_result"]["release"]["tag_name"], "v0.1.3")
        self.assertEqual(result["sync_result"]["receipt"]["sync_mode"], "release_artifacts")


if __name__ == "__main__":
    unittest.main()
