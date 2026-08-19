"""Regression coverage for Local Mode Sync Chain notifications and Stage 3 continuation UI."""

from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from gitdesk import syncrelease
from gitdesk.errors import AppError
from gitdesk.syncnotifications import sync_chain_notifications


# SyncChainNotificationTests protects project scoping and durable Local sync acknowledgement.
class SyncChainNotificationTests(unittest.TestCase):
    """Verify only post-boundary detected changes create Sync Chain notifications."""

    # Builds one chain whose creation or Local receipt time acts as the acknowledgement boundary.
    def settings(self, synced_at: str = "") -> dict:
        """Return one clean chained project with an optional completed Local sync."""

        receipts = {}
        if synced_at:
            receipts["local_to_private_beta"] = {
                "destination_digest": "installed",
                "synced_at": synced_at,
            }
        return {
            "sync_chains": [{
                "id": "chain-one",
                "project_path": "/projects/one",
                "stages": {},
                "receipts": receipts,
                "created_at": "2026-08-05T10:00:00Z",
            }],
        }

    # Confirms pre-chain activity and unrelated project activity cannot light the toolbar badge.
    def test_only_post_creation_changes_for_the_chained_project_notify(self) -> None:
        """Use exact project ownership and the chain creation time for an unsynced chain."""

        events = [
            {
                "project_path": "/projects/one",
                "occurred_at": "2026-08-05T09:59:59Z",
            },
            {
                "project_path": "/projects/two",
                "occurred_at": "2026-08-05T10:05:00Z",
            },
            {
                "project_path": "/projects/one",
                "occurred_at": "2026-08-05T10:06:00Z",
            },
        ]

        notifications = sync_chain_notifications(self.settings(), events)

        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["project_path"], "/projects/one")
        self.assertEqual(notifications[0]["change_count"], 1)

    # Confirms a successful Local Mode sync clears every detected project change through its receipt timestamp.
    def test_local_sync_receipt_acknowledges_earlier_detected_changes(self) -> None:
        """Retain only project changes detected strictly after the completed Local sync."""

        events = [
            {
                "project_path": "/projects/one",
                "occurred_at": "2026-08-05T10:04:00Z",
            },
            {
                "project_path": "/projects/one",
                "occurred_at": "2026-08-05T10:06:00Z",
            },
        ]

        notifications = sync_chain_notifications(
            self.settings("2026-08-05T10:05:00Z"),
            events,
        )

        self.assertEqual(notifications[0]["change_count"], 1)
        self.assertEqual(notifications[0]["latest_changed_at"], "2026-08-05T10:06:00Z")

        cleared = sync_chain_notifications(
            self.settings("2026-08-05T10:07:00Z"),
            events,
        )
        self.assertEqual(cleared, [])

    # Confirms the visible dots, modal checkbox, exact tag, and assembly order remain wired together.
    def test_frontend_wires_notification_dots_and_release_continuation(self) -> None:
        """Protect both notification surfaces and the post-publication Stage 3 prompt contract."""

        root = Path(__file__).resolve().parents[1]
        ui = root / "src" / "gitdesk" / "ui"
        toolbar = (ui / "sync-chain-ui.js").read_text(encoding="utf-8")
        workspace = (ui / "local-version-workspace.js").read_text(encoding="utf-8")
        workspace_styles = (ui / "local-version-workspace.css").read_text(encoding="utf-8")
        local_sync = (ui / "local-sync.js").read_text(encoding="utf-8")
        releases = (ui / "releases.js").read_text(encoding="utf-8")
        release_alerts = (ui / "release-alerts.js").read_text(encoding="utf-8")
        prompt = (ui / "sync-chain-stage-three.js").read_text(encoding="utf-8")
        artifact_jobs = (ui / "sync-chain-artifact-job.js").read_text(encoding="utf-8")
        controller = (ui / "sync-chain.js").read_text(encoding="utf-8")
        renderer = (ui / "sync-chain-render.js").read_text(encoding="utf-8")
        sync_styles = (ui / "sync-chain.css").read_text(encoding="utf-8")
        badge_styles = (ui / "badges.css").read_text(encoding="utf-8")
        bridge = (root / "src" / "gitdesk" / "syncchain_bridge.py").read_text(encoding="utf-8")
        index = (ui / "index.html").read_text(encoding="utf-8")

        self.assertIn("data-sync-chain-alert", toolbar)
        self.assertIn("local-sync-change-dot", workspace)
        self.assertIn("hasProjectNotification(localState.active_project)", workspace)
        self.assertIn("clearProjectNotification(projectPath)", local_sync)
        self.assertIn("refreshNotificationsAfterLocalSync()", local_sync)
        self.assertIn('callNative("syncChainNotifications", {})', controller)
        self.assertIn("renderChainList(state.sync, state.activeChainId, state.notifications)", controller)
        self.assertIn("sync-chain-row-notification", renderer)
        self.assertIn("notifications.some((item) => item.project_path === chain.project_path)", renderer)
        self.assertIn('button.classList.toggle("has-success-notification", hasNotification)', controller)
        self.assertIn('const notificationClass = pending ? " has-notification"', renderer)
        self.assertIn(".sync-chain-row.has-notification", sync_styles)
        self.assertIn(".local-promotion-stage.has-notification", workspace_styles)
        self.assertIn("0 0 14px 2px color-mix", sync_styles)
        self.assertIn("0 0 28px 5px color-mix", sync_styles)
        self.assertIn("0 0 14px 2px color-mix", workspace_styles)
        self.assertIn("0 0 28px 5px color-mix", workspace_styles)
        self.assertIn(".tab-alert-dot.success", badge_styles)
        self.assertNotIn(".tab-button.has-success-notification", badge_styles)
        self.assertIn(".history-button.has-success-notification", badge_styles)
        self.assertIn("var(--theme-notification-glow, #ffffff)", badge_styles)
        self.assertIn("var(--theme-notification-glow, #ffffff)", sync_styles)
        self.assertIn("var(--theme-notification-glow, #ffffff)", workspace_styles)
        self.assertIn("0 0 14px 3px color-mix", badge_styles)
        self.assertIn("0 0 30px 6px color-mix", badge_styles)
        self.assertIn('classList.toggle("has-success-notification", status === "success")', release_alerts)
        self.assertIn('"syncChainNotifications":', bridge)
        self.assertIn("GitDeskSyncStageThree.prompt", releases)
        self.assertIn("GitDeskSyncStageThree.prompt(repository.path, published", releases)
        self.assertIn('id="sync-stage-three-artifacts"', prompt)
        self.assertIn('"public_beta_to_public",\n      requested,', prompt)
        self.assertIn('callNative("startSyncChainEdge"', artifact_jobs)
        self.assertIn('callNative("syncChainJobStatus"', artifact_jobs)
        self.assertIn("expected_release_tag: expectedReleaseTag", artifact_jobs)
        self.assertIn("bytes_transferred", prompt)
        self.assertIn('"startSyncChainEdge":', bridge)
        self.assertIn('"syncChainJobStatus":', bridge)
        self.assertLess(index.index("sync-chain-artifact-job.js"), index.index("sync-chain.js"))
        self.assertLess(index.index("sync-chain.js"), index.index("sync-chain-stage-three.js"))

    # Confirms both visible Local-to-Stage-1 controls send an exact physical version path.
    def test_local_to_stage_one_controls_use_the_explicit_version_action(self) -> None:
        """Keep Version Info and setup-page sync on the validated Local-version bridge action."""

        root = Path(__file__).resolve().parents[1]
        ui = root / "src" / "gitdesk" / "ui"
        local_actions = (ui / "local-actions.js").read_text(encoding="utf-8")
        local_sync = (ui / "local-sync.js").read_text(encoding="utf-8")
        renderer = (ui / "sync-chain-render.js").read_text(encoding="utf-8")
        controller = (ui / "sync-chain.js").read_text(encoding="utf-8")

        self.assertIn("syncButton.hidden = false;", local_actions)
        self.assertIn('runAction("syncLocalVersionToPrivateBeta"', local_sync)
        self.assertIn('class="sync-chain-local-version"', renderer)
        self.assertIn('data-edge="local_to_private_beta"', renderer)
        self.assertIn('const action = localEdge ? "syncLocalVersionToPrivateBeta"', controller)
        self.assertIn("version_path: version ? version.value", controller)

    # Confirms the prompt cannot advance a different latest tag than the release it just published.
    @patch("gitdesk.syncrelease.destination_release_for_tag")
    @patch("gitdesk.syncrelease.latest_source_release")
    @patch("gitdesk.syncrelease.GitHubApiClient")
    def test_prompted_release_tag_must_still_be_latest_before_public_mutation(
        self,
        client_class: Mock,
        latest_release: Mock,
        release_for_tag: Mock,
    ) -> None:
        """Reject a changed latest release before creating or updating any Public release."""

        context = {
            "edge_name": "public_beta_to_public",
            "source_account_login": "private-profile",
            "destination_account_login": "public-profile",
            "source_repository": {"owner": "private-owner", "repo": "app-beta"},
            "destination_repository": {"owner": "public-owner", "repo": "app"},
        }
        source_client = Mock()
        destination_client = Mock()
        destination_client.repository.return_value = {"private": False}
        client_class.side_effect = [source_client, destination_client]
        latest_release.return_value = {"id": 2, "tag_name": "v0.1.4"}
        controller = Mock()
        controller.account_for_owner.side_effect = [
            {"login": "private-profile"},
            {"login": "public-profile"},
        ]
        controller.token_for_account.side_effect = ["private-token", "public-token"]

        with self.assertRaises(AppError) as raised:
            syncrelease.promote_latest_release(controller, context, "v0.1.3")

        self.assertEqual(raised.exception.code, "SYNC_RELEASE_EXPECTED_TAG_MISMATCH")
        release_for_tag.assert_not_called()


if __name__ == "__main__":
    unittest.main()
