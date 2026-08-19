"""Regression coverage for artifact-only final Sync Chain release promotion."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from gitdesk.errors import AppError
from gitdesk.githubreleaseassets import ReleaseAssetTransport
from gitdesk import syncrelease
from gitdesk.syncchains import clean_sync_chain, configure_public_artifact_sync_update, edge_context
from gitdesk.syncchain_lifecycle import detach_repository


# FakeResponse provides only the requests response surface used by binary release asset transport.
class FakeResponse:
    """Represent one deterministic streamed download or JSON upload response."""

    # Stores raw chunks or JSON while exposing a successful GitHub-like response.
    def __init__(self, chunks: list[bytes] | None = None, payload: dict | None = None) -> None:
        """Create a response with optional binary chunks and JSON payload."""

        self.chunks = chunks or []
        self.payload = payload or {}
        self.headers = {}
        self.status_code = 200

    # Supports requests.Response context management used by streaming downloads.
    def __enter__(self) -> "FakeResponse":
        """Return this response when a download enters its managed response block."""

        return self

    # Leaves exceptions untouched so the production error path remains observable.
    def __exit__(self, exception_type, exception, traceback) -> bool:
        """Return False so an exception from the transfer is never suppressed."""

        return False

    # Returns the preloaded byte chunks without changing their boundaries.
    def iter_content(self, chunk_size: int) -> list[bytes]:
        """Return binary chunks for the transport download loop."""

        return self.chunks

    # Returns the preloaded GitHub JSON response for uploads.
    def json(self) -> dict:
        """Return the configured response payload."""

        return self.payload

    # Matches the requests close contract without owning an external resource.
    def close(self) -> None:
        """Close this in-memory response without side effects."""


# SyncChainArtifactMetadataTests protects persistence and final receipt invalidation.
class SyncChainArtifactMetadataTests(unittest.TestCase):
    """Verify the checkbox is durable and changes only final-edge completion state."""

    # Builds a complete chain with all repository stages and receipts.
    def settings(self) -> dict:
        """Return metadata for one fully configured three-stage chain."""

        stages = {
            "private_beta": {"account_login": "owner", "repository_path": "/repos/private"},
            "public_beta": {"account_login": "owner", "repository_path": "/repos/public-beta"},
            "public": {"account_login": "public", "repository_path": "/repos/public"},
        }
        receipts = {
            "local_to_private_beta": {"destination_digest": "private"},
            "private_beta_to_public_beta": {"destination_digest": "public-beta"},
            "public_beta_to_public": {"destination_digest": "public"},
        }
        return {
            "sync_chains": [{
                "id": "chain",
                "project_path": "/projects/app",
                "stages": stages,
                "receipts": receipts,
            }],
        }

    # Confirms old metadata defaults to working-tree mode while a checked value survives sanitization.
    def test_clean_chain_preserves_artifact_mode_with_safe_default(self) -> None:
        """Default absent settings to False and retain an explicit enabled boolean."""

        raw_chain = self.settings()["sync_chains"][0]

        self.assertFalse(clean_sync_chain(raw_chain)["public_artifacts_only"])
        self.assertFalse(clean_sync_chain({**raw_chain, "public_artifacts_only": "true"})["public_artifacts_only"])
        self.assertTrue(clean_sync_chain({**raw_chain, "public_artifacts_only": True})["public_artifacts_only"])

    # Confirms changing final mode clears only the receipt whose meaning changed.
    def test_mode_change_clears_only_final_receipt(self) -> None:
        """Preserve earlier completion while invalidating Public completion from the prior mode."""

        update = configure_public_artifact_sync_update(self.settings(), "chain", True)
        chain = update["sync_chains"][0]

        self.assertTrue(chain["public_artifacts_only"])
        self.assertEqual(
            set(chain["receipts"]),
            {"local_to_private_beta", "private_beta_to_public_beta"},
        )

    # Confirms losing any configured repository dependency also disables the now-hidden final mode.
    def test_repository_detach_clears_artifact_mode(self) -> None:
        """Avoid silently restoring artifact mode after a final stage is removed and later replaced."""

        settings = self.settings()
        settings["sync_chains"][0]["public_artifacts_only"] = True

        detached = detach_repository(settings, "public", "/repos/public")

        self.assertFalse(detached[0]["public_artifacts_only"])

    # Confirms artifact promotion receives exact source and destination remote identities from saved metadata.
    def test_final_edge_context_exposes_both_repository_records(self) -> None:
        """Resolve owner/repo pairs without deriving them from frontend values."""

        settings = self.settings()
        settings["managed_repositories"] = {
            "owner": [{
                "path": "/repos/public-beta",
                "owner": "private-owner",
                "repo": "app-beta",
            }],
            "public": [{
                "path": "/repos/public",
                "owner": "public-owner",
                "repo": "app",
            }],
        }

        context = edge_context(settings, "chain", "public_beta_to_public")

        self.assertEqual(context["source_repository"]["full_name"], "private-owner/app-beta")
        self.assertEqual(context["destination_repository"]["full_name"], "public-owner/app")
        self.assertEqual(context["source_account_login"], "owner")
        self.assertEqual(context["destination_account_login"], "public")


# ReleaseAssetTransportTests verifies raw transfer boundaries without making network requests.
class ReleaseAssetTransportTests(unittest.TestCase):
    """Verify authenticated download hashing and release-specific upload construction."""

    # Confirms private release bytes are hashed and size-checked while downloading.
    def test_download_streams_and_hashes_exact_asset_bytes(self) -> None:
        """Return a sha256 digest for the complete streamed response body."""

        client = Mock()
        client.token_expires_at = ""
        client.session.get.return_value = FakeResponse([b"build-", b"artifact"])
        target = BytesIO()

        digest = ReleaseAssetTransport(client).download(
            "private-owner",
            "app-beta",
            {"id": 7, "size": 14},
            target,
        )

        self.assertEqual(target.getvalue(), b"build-artifact")
        self.assertEqual(digest, f"sha256:{sha256(b'build-artifact').hexdigest()}")
        request = client.session.get.call_args
        self.assertEqual(request.kwargs["headers"]["Accept"], "application/octet-stream")
        self.assertIn("/private-owner/app-beta/releases/assets/7", request.args[0])

    # Confirms uploads send raw bytes to uploads.github.com with the source name and media type.
    def test_upload_uses_release_asset_endpoint_and_raw_content(self) -> None:
        """Preserve artifact metadata while avoiding JSON or source-tree payloads."""

        client = Mock()
        client.token_expires_at = ""
        client.session.post.return_value = FakeResponse(payload={
            "id": 9,
            "name": "GitDesk.dmg",
            "size": 5,
        })
        source = BytesIO(b"build")

        uploaded = ReleaseAssetTransport(client).upload(
            "public-owner",
            "app",
            4,
            {
                "name": "GitDesk.dmg",
                "label": "macOS",
                "content_type": "application/x-apple-diskimage",
                "size": 5,
            },
            source,
        )

        self.assertEqual(uploaded["name"], "GitDesk.dmg")
        request = client.session.post.call_args
        self.assertTrue(request.args[0].startswith("https://uploads.github.com/"))
        self.assertEqual(request.kwargs["params"], {"name": "GitDesk.dmg", "label": "macOS"})
        self.assertEqual(request.kwargs["headers"]["Content-Length"], "5")
        self.assertIs(request.kwargs["data"], source)


# SyncReleaseOrchestrationTests protects tag identity, PAT routing, and receipt completion.
class SyncReleaseOrchestrationTests(unittest.TestCase):
    """Verify the final edge publishes the source tag and reports only release assets."""

    # Builds the final edge context normally supplied by syncchains.edge_context.
    def context(self) -> dict:
        """Return exact local, remote, owner-profile, and mode metadata for the final edge."""

        return {
            "edge_name": "public_beta_to_public",
            "source_path": "/repos/public-beta",
            "destination_path": "/repos/public",
            "source_account_login": "private-profile",
            "destination_account_login": "public-profile",
            "source_repository": {"owner": "private-owner", "repo": "app-beta"},
            "destination_repository": {"owner": "public-owner", "repo": "app"},
        }

    # Confirms the destination release omits the private commit target while retaining its exact tag and notes.
    def test_destination_release_data_keeps_tag_without_source_commit(self) -> None:
        """Use the Public repository's own default branch for tag creation."""

        data = syncrelease.destination_release_data({
            "tag_name": "v0.1.3",
            "name": "Version 0.1.3",
            "body": "Release notes",
            "target_commitish": "private-sha",
        }, False)

        self.assertEqual(data["tag_name"], "v0.1.3")
        self.assertEqual(data["make_latest"], "true")
        self.assertNotIn("target_commitish", data)

    # Confirms an existing public release with a different asset set is preserved and rejected.
    @patch("gitdesk.syncrelease.release_assets")
    def test_published_asset_conflict_is_rejected_without_deletion(self, assets: Mock) -> None:
        """Never destructively replace a mismatched already-published Public release."""

        source_client = Mock()
        destination_client = Mock()
        assets.side_effect = [
            [{"id": 7, "name": "GitDesk.dmg", "size": 5, "state": "uploaded"}],
            [],
        ]

        with self.assertRaises(AppError) as raised:
            syncrelease.verify_published_assets(
                source_client,
                destination_client,
                ("private-owner", "app-beta"),
                ("public-owner", "app"),
                {"id": 1, "tag_name": "v0.1.3"},
                {"id": 2, "tag_name": "v0.1.3", "draft": False},
            )

        self.assertEqual(raised.exception.code, "SYNC_RELEASE_PUBLISHED_CONFLICT")
        destination_client.request.assert_not_called()

    # Confirms source and destination PATs remain independent and the receipt records publication identity.
    @patch("gitdesk.syncrelease.publish_destination_release")
    @patch("gitdesk.syncrelease.synchronize_draft_assets")
    @patch("gitdesk.syncrelease.prepare_destination_draft")
    @patch("gitdesk.syncrelease.destination_release_for_tag")
    @patch("gitdesk.syncrelease.latest_source_release")
    @patch("gitdesk.syncrelease.GitHubApiClient")
    def test_promotion_uses_owner_routed_clients_and_matching_tag(
        self,
        client_class: Mock,
        latest_release: Mock,
        release_for_tag: Mock,
        prepare_draft: Mock,
        synchronize_assets: Mock,
        publish_release: Mock,
    ) -> None:
        """Publish v0.1.3 as latest and record the exact artifact-only completion receipt."""

        source_client = Mock()
        destination_client = Mock()
        destination_client.repository.return_value = {"private": False}
        client_class.side_effect = [source_client, destination_client]
        latest_release.return_value = {"id": 1, "tag_name": "v0.1.3", "name": "v0.1.3", "body": ""}
        release_for_tag.return_value = None
        prepare_draft.return_value = {"id": 2, "draft": True}
        synchronize_assets.return_value = ({"GitDesk.dmg": "sha256:" + "a" * 64}, 4096)
        publish_release.return_value = {"id": 2, "tag_name": "v0.1.3", "assets": [], "draft": False}
        controller = Mock()
        controller.account_for_owner.side_effect = [
            {"login": "private-profile"},
            {"login": "public-profile"},
        ]
        controller.token_for_account.side_effect = ["private-token", "public-token"]

        result = syncrelease.promote_latest_release(controller, self.context())

        self.assertEqual(client_class.call_args_list[0].args[0], "private-token")
        self.assertEqual(client_class.call_args_list[1].args[0], "public-token")
        self.assertEqual(result["release"]["tag_name"], "v0.1.3")
        self.assertEqual(result["receipt"]["release_tag"], "v0.1.3")
        self.assertEqual(result["receipt"]["sync_mode"], "release_artifacts")
        self.assertEqual(result["receipt"]["file_count"], 1)
        publish_release.assert_called_once_with(
            destination_client,
            ("public-owner", "app"),
            latest_release.return_value,
            2,
        )

    # Confirms the Stage 3 header owns the checkbox while the final edge uses persisted state.
    def test_bridge_and_ui_route_only_enabled_final_edge_to_release_service(self) -> None:
        """Protect Stage 3 placement, final-action locking, and the no-source release branch."""

        root = Path(__file__).resolve().parents[1] / "src" / "gitdesk"
        bridge = (root / "syncchain_bridge.py").read_text(encoding="utf-8")
        renderer = (root / "ui" / "sync-chain-render.js").read_text(encoding="utf-8")
        controller = (root / "ui" / "sync-chain.js").read_text(encoding="utf-8")
        stylesheet = (root / "ui" / "sync-chain.css").read_text(encoding="utf-8")

        self.assertIn('artifact_release = syncchains.artifact_only_for_edge', bridge)
        self.assertIn(
            'release_result = promote_latest_release(controller, context, expected_release_tag, progress)',
            bridge,
        )
        self.assertIn('transaction = begin_mirror_transaction(', bridge)
        self.assertIn('data-sync-artifacts-only', renderer)
        self.assertIn("const eligible = configured && previous", renderer)
        self.assertIn('data-edge="${escapeHtml(stage.edge)}"', renderer)
        self.assertIn(
            '          </div>\n'
            '          ${publicArtifactOptionMarkup(stage, chain, configured)}\n'
            '        </div>\n'
            '        ${removeButton}',
            renderer,
        )
        stage_markup_start = renderer.index("function stageMarkup")
        header_start = renderer.index('<div class="sync-chain-stage-header">', stage_markup_start)
        checkbox_position = renderer.index('${publicArtifactOptionMarkup(stage, chain, configured)}')
        stage_body_start = renderer.index('${destinationChoiceMarkup(stage, configured', header_start)
        self.assertLess(header_start, checkbox_position)
        self.assertLess(checkbox_position, stage_body_start)
        self.assertNotIn(
            '${publicArtifactOptionMarkup(stage, chain, configured)}',
            renderer[stage_body_start:],
        )
        self.assertIn('configureArtifactSync', controller)
        self.assertIn('const edge = input.dataset.edge || "";', controller)
        self.assertIn(
            '#panel-sync-chain .sync-chain-artifact-option input[type="checkbox"] {',
            stylesheet,
        )
        self.assertIn('width: 18px;', stylesheet)
        self.assertIn('min-height: 18px;', stylesheet)
        self.assertIn('-webkit-text-fill-color: currentColor;', stylesheet)
        self.assertIn('background-image: none;', stylesheet)

    # Confirms private repositories are valid artifact destinations for non-Public terminal stages.
    def test_artifact_destination_privacy_does_not_block_release_delivery(self) -> None:
        """Do not hard-code Public visibility into generalized terminal release promotion."""

        source = Path(syncrelease.__file__).read_text(encoding="utf-8")

        self.assertNotIn("SYNC_RELEASE_DESTINATION_PRIVATE", source)


if __name__ == "__main__":
    unittest.main()
