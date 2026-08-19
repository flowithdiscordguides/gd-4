"""Regression coverage for local Sync Chain stages and terminal artifact delivery."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from gitdesk.errors import AppError
from gitdesk.syncchain_jobs import start_sync_chain_job
from gitdesk.syncmirror import validate_mirror_paths
from gitdesk.syncchains import (
    configure_artifact_sync_update,
    configure_local_stage_update,
    edge_context,
)


class SyncChainFlexibilityTests(unittest.TestCase):
    """Protect chooser-backed folders and a two-repository artifact terminal."""

    def test_local_stages_resolve_without_managed_repository_records(self) -> None:
        """Mirror between ordinary selected folders without requiring Git metadata."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            first = root / "stage-one"
            second = root / "stage-two"
            project.mkdir()
            first.mkdir()
            second.mkdir()
            settings = {
                "local_projects": [{"path": str(project), "name": "project", "category": ""}],
                "managed_repositories": {},
                "sync_chains": [{
                    "id": "chain",
                    "project_path": str(project),
                    "stages": {},
                    "receipts": {},
                }],
            }
            settings.update(configure_local_stage_update(settings, "chain", "private_beta", str(first)))
            settings.update(configure_local_stage_update(settings, "chain", "public_beta", str(second)))
            context = edge_context(settings, "chain", "private_beta_to_public_beta")

        self.assertEqual(context["source_path"], str(first.resolve()))
        self.assertEqual(context["destination_path"], str(second.resolve()))
        self.assertIsNone(context["source_repository"])
        self.assertIsNone(context["destination_repository"])
        self.assertFalse(context["handoff_destination"])

    def test_mirror_path_validation_imports_its_canonical_helper(self) -> None:
        """Keep application startup and nested-path rejection intact after helper modularization."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with self.assertRaises(AppError) as raised:
                validate_mirror_paths(root, root / "nested")

        self.assertEqual(raised.exception.code, "SYNC_PATH_OVERLAP")

    def test_stage_two_can_be_the_artifact_only_terminal(self) -> None:
        """Bind binary release delivery to Stage 2 when Stage 3 is not configured."""

        stages = {
            "private_beta": {"account_login": "owner", "repository_path": "/repos/private"},
            "public_beta": {"account_login": "owner", "repository_path": "/repos/public-beta"},
        }
        settings = {
            "sync_chains": [{
                "id": "chain",
                "project_path": "/projects/app",
                "stages": stages,
                "receipts": {"private_beta_to_public_beta": {"destination_digest": "old"}},
            }],
        }

        update = configure_artifact_sync_update(
            settings,
            "chain",
            "private_beta_to_public_beta",
            True,
        )
        chain = update["sync_chains"][0]

        self.assertEqual(chain["artifact_only_edge"], "private_beta_to_public_beta")
        self.assertFalse(chain["public_artifacts_only"])
        self.assertNotIn("private_beta_to_public_beta", chain["receipts"])

    def test_stage_two_artifacts_use_the_background_job_boundary(self) -> None:
        """Accept the saved Stage 2 artifact edge without blocking a WebView request."""

        settings = {
            "sync_chains": [{
                "id": "chain",
                "project_path": "/projects/app",
                "stages": {
                    "private_beta": {"account_login": "owner", "repository_path": "/repos/private"},
                    "public_beta": {"account_login": "owner", "repository_path": "/repos/public-beta"},
                },
                "artifact_only_edge": "private_beta_to_public_beta",
                "receipts": {},
            }],
        }
        controller = Mock()
        controller.settings_store.load.return_value = settings
        with patch("gitdesk.syncchain_jobs.SYNC_JOB_REGISTRY.start", return_value={"job_id": "job"}) as start:
            result = start_sync_chain_job(
                controller,
                {"chain_id": "chain", "edge": "private_beta_to_public_beta"},
                Mock(),
            )

        self.assertEqual(result, {"job_id": "job"})
        self.assertEqual(start.call_args.args[0], "chain\0private_beta_to_public_beta")

    def test_setup_uses_native_folder_authority_and_in_app_deletion(self) -> None:
        """Keep local paths out of WebView payloads and browser confirmation out of destructive actions."""

        root = Path(__file__).resolve().parents[1] / "src" / "gitdesk"
        controller = (root / "ui" / "sync-chain.js").read_text(encoding="utf-8")
        renderer = (root / "ui" / "sync-chain-render.js").read_text(encoding="utf-8")
        deletion = (root / "ui" / "sync-chain-delete.js").read_text(encoding="utf-8")
        jobs = (root / "ui" / "sync-chain-artifact-job.js").read_text(encoding="utf-8")
        bridge = (root / "syncchain_configuration_bridge.py").read_text(encoding="utf-8")

        self.assertIn("chooseSyncStageFolder", controller)
        self.assertIn("GitDeskSyncChainArtifactJob", controller)
        self.assertIn('callNative("startSyncChainEdge"', jobs)
        self.assertIn('callNative("syncChainJobStatus"', jobs)
        self.assertIn("data-sync-local-toggle", renderer)
        self.assertIn("choose_directory", bridge)
        self.assertNotIn('payload.get("folder_path")', bridge)
        self.assertNotIn("window.confirm", controller)
        self.assertIn('open("deleteSyncChain", deleteButton)', deletion)
        self.assertIn('open("removeSyncStage", removeButton)', deletion)


if __name__ == "__main__":
    unittest.main()
