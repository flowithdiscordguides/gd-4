"""Regression coverage for progress-aware Stage 3 background transfer."""

from __future__ import annotations

from hashlib import sha256
from threading import Event
import unittest
from unittest.mock import Mock, patch

from gitdesk import syncchain_bridge, syncrelease
from gitdesk.errors import AppError
from gitdesk.githubreleaseassets import ReleaseAssetTransport
from gitdesk.syncchain_jobs import SyncJobRegistry


class FakeStreamResponse:
    """Provide the streamed response surface used by a release-asset copy."""

    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.headers = {}
        self.status_code = 200

    def __enter__(self) -> "FakeStreamResponse":
        return self

    def __exit__(self, exception_type, exception, traceback) -> bool:
        return False

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return self.chunks


class StageThreeStreamingTests(unittest.TestCase):
    """Verify a digest-backed first publication overlaps its download and upload."""

    def test_copy_to_hashes_the_same_stream_consumed_by_upload(self) -> None:
        """Avoid a complete download pass before a trustworthy source asset begins uploading."""

        content = b"build-artifact"
        source_client = Mock()
        source_client.token_expires_at = ""
        source_client.session.get.return_value = FakeStreamResponse([b"build-", b"artifact"])
        destination_transport = Mock()
        uploaded_bytes = bytearray()
        upload_progress: list[tuple[int, int]] = []
        download_progress: list[tuple[int, int]] = []

        def upload(_owner, _repo, _release_id, asset, reader, on_progress, rewind=True):
            self.assertFalse(rewind)
            while True:
                chunk = reader.read(4)
                if not chunk:
                    break
                uploaded_bytes.extend(chunk)
                on_progress(len(uploaded_bytes), asset["size"])
            return {"id": 9, "name": asset["name"], "size": asset["size"], "state": "uploaded"}

        destination_transport.upload.side_effect = upload
        uploaded, digest = ReleaseAssetTransport(source_client).copy_to(
            destination_transport,
            ("private-owner", "app-beta"),
            ("public-owner", "app"),
            8,
            {"id": 7, "name": "GitDesk.zip", "size": len(content)},
            lambda current, total: download_progress.append((current, total)),
            lambda current, total: upload_progress.append((current, total)),
        )

        self.assertEqual(bytes(uploaded_bytes), content)
        self.assertEqual(digest, f"sha256:{sha256(content).hexdigest()}")
        self.assertEqual(uploaded["name"], "GitDesk.zip")
        self.assertEqual(download_progress[-1], (len(content), len(content)))
        self.assertEqual(upload_progress[-1], (len(content), len(content)))

    @patch("gitdesk.syncrelease.ReleaseAssetTransport")
    @patch("gitdesk.syncrelease.release_assets")
    def test_digest_backed_draft_uses_stream_copy_without_two_pass_download(
        self,
        release_assets: Mock,
        transport_class: Mock,
    ) -> None:
        """Use one digest-checked stream for a missing Public draft asset."""

        digest = "sha256:" + "d" * 64
        source = {"id": 1, "name": "GitDesk.zip", "size": 4096, "state": "uploaded", "digest": digest}
        uploaded = {"id": 2, "name": "GitDesk.zip", "size": 4096, "state": "uploaded", "digest": digest}
        release_assets.side_effect = [[source], [], [uploaded]]
        source_transport = Mock()
        destination_transport = Mock()
        source_transport.copy_to.return_value = (uploaded, digest)
        transport_class.side_effect = [source_transport, destination_transport]

        verified, total_bytes = syncrelease.synchronize_draft_assets(
            Mock(),
            Mock(),
            ("private-owner", "app-beta"),
            ("public-owner", "app"),
            {"id": 10},
            {"id": 20},
        )

        self.assertEqual(verified, {"GitDesk.zip": digest})
        self.assertEqual(total_bytes, 4096)
        source_transport.copy_to.assert_called_once()
        source_transport.download.assert_not_called()
        destination_transport.upload.assert_not_called()


class StageThreeJobTests(unittest.TestCase):
    """Verify terminal results, errors, and active-edge deduplication."""

    def wait_for_job(self, registry: SyncJobRegistry, job_id: str) -> None:
        """Join the registry-owned daemon thread without polling or sleeping."""

        thread = registry.jobs[job_id]["thread"]
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())

    def test_job_returns_progress_and_terminal_result(self) -> None:
        """Keep the WebUI callback short while preserving the complete sync response."""

        registry = SyncJobRegistry()

        def runner(report):
            report({"phase": "uploading", "message": "Uploading GitDesk.zip", "bytes_transferred": 5})
            return {"sync_result": {"edge": "public_beta_to_public"}}

        started = registry.start("chain\0public_beta_to_public", runner)
        self.wait_for_job(registry, started["job_id"])
        status = registry.status(started["job_id"])

        self.assertEqual(status["status"], "succeeded")
        self.assertEqual(status["progress"]["phase"], "uploading")
        self.assertEqual(status["result"]["sync_result"]["edge"], "public_beta_to_public")

    def test_job_returns_structured_application_error(self) -> None:
        """Let the modal settle with the backend's safe error instead of an unresolved promise."""

        registry = SyncJobRegistry()

        def runner(_report):
            raise AppError("GitHub rejected the release.", "SYNC_RELEASE_REJECTED")

        started = registry.start("chain\0public_beta_to_public", runner)
        self.wait_for_job(registry, started["job_id"])
        status = registry.status(started["job_id"])

        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["error"]["code"], "SYNC_RELEASE_REJECTED")

    def test_active_edge_reuses_one_job(self) -> None:
        """Prevent repeated Stage 3 clicks from queuing duplicate release transfers."""

        registry = SyncJobRegistry()
        entered = Event()
        release = Event()

        def runner(_report):
            entered.set()
            release.wait(timeout=1)
            return {}

        first = registry.start("chain\0public_beta_to_public", runner)
        self.assertTrue(entered.wait(timeout=1))
        second = registry.start("chain\0public_beta_to_public", runner)
        release.set()
        self.wait_for_job(registry, first["job_id"])

        self.assertEqual(second, {"job_id": first["job_id"], "reused": True})

    @patch("gitdesk.syncchain_bridge.run_sync_edge_locked")
    @patch("gitdesk.syncchain_bridge.SYNC_TRANSACTION_LOCK")
    def test_background_stage_three_rejects_a_hidden_sync_queue(
        self,
        sync_lock: Mock,
        run_locked: Mock,
    ) -> None:
        """Settle promptly when another sync owns the global transaction instead of waiting behind it."""

        sync_lock.acquire.return_value = False

        with self.assertRaises(AppError) as raised:
            syncchain_bridge.run_sync_edge(
                Mock(),
                {},
                "chain",
                "public_beta_to_public",
                "",
                progress=Mock(),
            )

        self.assertEqual(raised.exception.code, "SYNC_CHAIN_BUSY")
        run_locked.assert_not_called()
        sync_lock.release.assert_not_called()


if __name__ == "__main__":
    unittest.main()
