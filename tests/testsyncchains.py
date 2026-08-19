"""Regression coverage for Project Sync Chain metadata and ordered-stage validation."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from gitdesk.errors import AppError
from gitdesk.syncchain_bridge import destination_repository_handoff
from gitdesk.syncchains import clean_sync_chains, configure_stage_update, create_chain_update, receipt_update
from gitdesk.syncchain_lifecycle import (
    detach_repository,
    remap_project_chains,
    remove_project_chains,
    sync_chain_state,
)
from gitdesk.syncchains import edge_context


# SyncChainMetadataTests uses disposable path records without touching application settings.
class SyncChainMetadataTests(unittest.TestCase):
    """Verify one-per-project chains, stage order, path separation, and lifecycle cleanup."""

    # Builds the minimum registry state needed for chain configuration tests.
    def settings(self, root: Path) -> dict:
        """Return one saved project and three account-owned repository records."""

        project = root / "project"
        repositories = [root / "private", root / "public-beta", root / "public"]
        project.mkdir()
        for repository in repositories:
            repository.mkdir()
        return {
            "local_projects": [{"path": str(project), "name": "project", "category": ""}],
            "managed_repositories": {
                "octocat": [
                    {
                        "path": str(path),
                        "name": path.name,
                        "owner": "octocat",
                        "repo": path.name,
                        "full_name": f"octocat/{path.name}",
                    }
                    for path in repositories
                ],
            },
            "sync_chains": [],
        }

    # Confirms Local Mode metadata, not an arbitrary Finder folder, is required to create a chain.
    def test_chain_requires_saved_local_project(self) -> None:
        """Reject a project path that is absent from GitDesk's local project registry."""

        with self.assertRaises(AppError) as raised:
            create_chain_update({"local_projects": []}, "/unmanaged/project")

        self.assertEqual(raised.exception.code, "SYNC_PROJECT_NOT_MANAGED")

    # Confirms a project can own only one chain even when creation is requested repeatedly.
    def test_project_can_own_only_one_chain(self) -> None:
        """Create one chain and reject a duplicate for the same Local Mode project."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            settings = self.settings(Path(temporary_directory))
            settings.update(create_chain_update(settings, settings["local_projects"][0]["path"]))
            with self.assertRaises(AppError) as raised:
                create_chain_update(settings, settings["local_projects"][0]["path"])

        self.assertEqual(raised.exception.code, "SYNC_CHAIN_PROJECT_EXISTS")

    # Confirms stages cannot skip Private Beta and repository paths cannot overlap the Local project.
    def test_stage_order_and_path_overlap_are_enforced(self) -> None:
        """Reject Public Beta before Private Beta and reject a destination nested in the source project."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = self.settings(root)
            settings.update(create_chain_update(settings, settings["local_projects"][0]["path"]))
            chain_id = settings["sync_chains"][0]["id"]
            with self.assertRaises(AppError) as order_error:
                configure_stage_update(settings, chain_id, "public_beta", "octocat", str(root / "public-beta"))
            nested = root / "project" / "nested-repository"
            nested.mkdir()
            settings["managed_repositories"]["octocat"].append({
                "path": str(nested),
                "name": nested.name,
                "owner": "octocat",
                "repo": nested.name,
                "full_name": f"octocat/{nested.name}",
            })
            with self.assertRaises(AppError) as overlap_error:
                configure_stage_update(settings, chain_id, "private_beta", "octocat", str(nested))

        self.assertEqual(order_error.exception.code, "SYNC_STAGE_PREVIOUS_REQUIRED")
        self.assertEqual(overlap_error.exception.code, "SYNC_CHAIN_PATH_OVERLAP")

    # Confirms selected Local Mode versions must physically belong to the chain's saved project.
    def test_first_edge_rejects_version_from_another_project(self) -> None:
        """Reject a version path outside the chain's Local Mode project hierarchy."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = self.settings(root)
            settings.update(create_chain_update(settings, settings["local_projects"][0]["path"]))
            chain_id = settings["sync_chains"][0]["id"]
            settings.update(configure_stage_update(
                settings,
                chain_id,
                "private_beta",
                "octocat",
                str(root / "private"),
            ))
            unrelated = root / "unrelated" / "feature" / "v1"
            unrelated.mkdir(parents=True)
            with self.assertRaises(AppError) as raised:
                edge_context(settings, chain_id, "local_to_private_beta", str(unrelated))

        self.assertEqual(raised.exception.code, "LOCAL_VERSION_INVALID")

    # Confirms setup state supplies only real Local version folders for the first-edge selector.
    def test_setup_state_lists_exact_local_source_versions(self) -> None:
        """Project physical versions into Sync Chain state with their owning feature labels."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = self.settings(root)
            version = root / "project" / "01 init" / "v1 project"
            version.mkdir(parents=True)

            state = sync_chain_state(settings)

        self.assertEqual(state["projects"][0]["versions"], [{
            "name": "v1 project",
            "path": str(version.resolve()),
            "feature_name": "01 init",
        }])

    # Confirms the first edge hands off only when Private Beta is the configured terminal stage.
    def test_first_edge_handoff_depends_on_public_beta_configuration(self) -> None:
        """Open terminal Private Beta, but stay Local when Public Beta is available as Step 2."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            settings = self.settings(root)
            project = Path(settings["local_projects"][0]["path"])
            version = project / "01 init" / "v1 project"
            version.mkdir(parents=True)
            settings.update(create_chain_update(settings, str(project)))
            chain_id = settings["sync_chains"][0]["id"]
            settings.update(configure_stage_update(
                settings,
                chain_id,
                "private_beta",
                "octocat",
                str(root / "private"),
            ))
            terminal_context = edge_context(settings, chain_id, "local_to_private_beta", str(version))
            settings.update(configure_stage_update(
                settings,
                chain_id,
                "public_beta",
                "octocat",
                str(root / "public-beta"),
            ))
            two_step_context = edge_context(settings, chain_id, "local_to_private_beta", str(version))
            repository_context = edge_context(settings, chain_id, "private_beta_to_public_beta")

        self.assertTrue(terminal_context["handoff_destination"])
        self.assertFalse(two_step_context["handoff_destination"])
        self.assertTrue(repository_context["handoff_destination"])

    # Confirms a newly completed edge invalidates only receipts that are later in the ordered chain.
    def test_receipt_update_clears_downstream_completion(self) -> None:
        """Keep earlier proof while removing stale downstream completion after a new snapshot install."""

        receipts = {
            edge: {"destination_digest": f"old-{edge}"}
            for edge in (
                "local_to_private_beta",
                "private_beta_to_public_beta",
                "public_beta_to_public",
            )
        }
        settings = {
            "sync_chains": [{
                "id": "chain",
                "project_path": "/project",
                "stages": {},
                "receipts": receipts,
            }],
        }

        middle_update = receipt_update(
            settings,
            "chain",
            "private_beta_to_public_beta",
            {"destination_digest": "new-public-beta"},
        )
        first_update = receipt_update(
            settings,
            "chain",
            "local_to_private_beta",
            {"destination_digest": "new-private-beta"},
        )

        self.assertEqual(
            set(middle_update["sync_chains"][0]["receipts"]),
            {"local_to_private_beta", "private_beta_to_public_beta"},
        )
        self.assertEqual(
            set(first_update["sync_chains"][0]["receipts"]),
            {"local_to_private_beta"},
        )

    # Confirms removing a managed stage clears that stage and all forward dependencies.
    def test_repository_detach_clears_downstream_stages(self) -> None:
        """Preserve the chain while removing stages that depend on a removed repository."""

        chain = {
            "id": "chain",
            "project_path": "/project",
            "stages": {
                "private_beta": {"account_login": "octocat", "repository_path": "/private"},
                "public_beta": {"account_login": "octocat", "repository_path": "/public-beta"},
                "public": {"account_login": "octocat", "repository_path": "/public"},
            },
            "receipts": {},
            "created_at": "now",
            "updated_at": "now",
        }

        detached = detach_repository({"sync_chains": [chain]}, "octocat", "/public-beta")

        self.assertEqual(set(detached[0]["stages"]), {"private_beta"})

    # Confirms project repair removes only chains whose source metadata disappeared.
    def test_project_cleanup_preserves_remaining_chains(self) -> None:
        """Remove orphaned chain records while retaining a still-managed project chain."""

        chains = [
            {"id": "one", "project_path": "/one", "stages": {}, "receipts": {}},
            {"id": "two", "project_path": "/two", "stages": {}, "receipts": {}},
        ]

        remaining = remove_project_chains({"sync_chains": chains}, {"/two"})

        self.assertEqual([chain["id"] for chain in clean_sync_chains(remaining)], ["two"])

    # Confirms folder moves update the receipt paths that record which Local version was synchronized.
    def test_project_remap_updates_nested_chain_paths(self) -> None:
        """Remap project-owned paths while preserving unrelated repository destinations."""

        fixture_root = Path.cwd().resolve() / "path-remap-fixture"
        old_root = fixture_root / "Alpha"
        new_root = fixture_root / "categories" / "Game" / "Alpha"
        destination = "/repositories/private"
        settings = {
            "sync_chains": [{
                "id": "alpha",
                "project_path": str(new_root),
                "stages": {
                    "private_beta": {
                        "account_login": "octocat",
                        "repository_path": destination,
                    },
                },
                "receipts": {
                    "local_to_private_beta": {
                        "source_path": str(old_root / "01 init" / "v1"),
                        "destination_path": destination,
                        "destination_digest": "digest",
                    },
                },
            }],
        }

        remapped = remap_project_chains(settings, old_root, new_root)
        receipt = remapped[0]["receipts"]["local_to_private_beta"]

        self.assertEqual(remapped[0]["project_path"], str(new_root))
        self.assertEqual(receipt["source_path"], str(new_root / "01 init" / "v1"))
        self.assertEqual(receipt["destination_path"], destination)


# SyncChainDestinationHandoffTests protects cross-owner Stage 2 activation after a successful mirror.
class SyncChainDestinationHandoffTests(unittest.TestCase):
    """Verify a mirrored destination becomes the active Repo Mode repository under its exact owner."""

    # Confirms destination settings and fresh Git state use the destination owner rather than the source owner.
    def test_cross_owner_destination_becomes_active_repo_mode_context(self) -> None:
        """Select Public Beta under its owner and return its status and branches for Overview."""

        destination_path = "/repositories/public-beta"
        summary = {
            "path": destination_path,
            "branch": "main",
            "github_owner": "public-owner",
            "github_repo": "public-beta",
            "has_origin": True,
            "remotes": [],
        }
        status = {"repository": summary, "files": [{"path": "src/app.py"}], "summary": {"changed": 1}}
        branches = {"current": "main", "branches": [{"name": "main", "active": True}], "has_commits": True}
        settings = {
            "active_account": "private-owner",
            "workspace_mode": "repo",
            "managed_repositories": {
                "private-owner": [],
                "public-owner": [{
                    "path": destination_path,
                    "name": "public-beta",
                    "owner": "public-owner",
                    "repo": "public-beta",
                    "full_name": "public-owner/public-beta",
                }],
            },
            "active_repository_by_account": {},
        }
        controller = Mock()
        controller.git_service.repository_summary.return_value = summary
        controller.git_service.status.return_value = status
        controller.git_service.branches.return_value = branches

        updates, handoff = destination_repository_handoff(controller, settings, {
            "destination_account_login": "public-owner",
            "destination_path": destination_path,
            "destination_label": "Public Beta",
        })

        self.assertEqual(updates["active_account"], "public-owner")
        self.assertEqual(updates["active_repository_by_account"]["public-owner"], destination_path)
        self.assertEqual(updates["repository_path"], destination_path)
        self.assertEqual(updates["workspace_mode"], "repo")
        self.assertEqual(handoff["account_login"], "public-owner")
        self.assertIs(handoff["status"], status)
        self.assertIs(handoff["branches"], branches)

    # Confirms the frontend applies owner/settings context before rendering Stage 2 changed files.
    def test_frontend_handoff_orders_account_settings_and_status(self) -> None:
        """Require one event to open the synced destination with fresh Overview state."""

        root = Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "ui"
        sync_source = (root / "sync-chain.js").read_text(encoding="utf-8")
        app_source = (root / "app.js").read_text(encoding="utf-8")

        self.assertIn('new CustomEvent("gitdesk:sync-destination-ready"', sync_source)
        handler_index = app_source.index("handleSyncedDestination")
        account_index = app_source.index("accountManager.apply(data.auth);", handler_index)
        settings_index = app_source.index("applySettings(data.settings);", account_index)
        status_index = app_source.index("applyStatus(data.status);", settings_index)
        overview_index = app_source.index('showPanel("overview");', status_index)
        self.assertLess(account_index, settings_index)
        self.assertLess(settings_index, status_index)
        self.assertLess(status_index, overview_index)


# SyncChainUnconditionalPolicyTests prevents removed destination/source policy gates from returning.
class SyncChainUnconditionalPolicyTests(unittest.TestCase):
    """Verify every Sync Chain edge remains an unconditional current-working-file replacement."""

    # Confirms neither backend nor frontend can reintroduce a confirmation or cleanliness blocker.
    def test_sync_execution_contains_no_divergence_or_clean_source_gate(self) -> None:
        """Reject old blocker codes, override prompts, and source-cleanliness checks in active sync files."""

        root = Path(__file__).resolve().parents[1] / "src" / "gitdesk"
        paths = [
            root / "synctransaction.py",
            root / "syncchain_bridge.py",
            root / "ui" / "sync-chain.js",
            root / "ui" / "local-sync.js",
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in paths)

        self.assertNotIn("SYNC_DESTINATION_DIVERGED", source)
        self.assertNotIn("Replace anyway", source)
        self.assertNotIn("require_clean_repository_source", source)
        self.assertNotIn("SYNC_SOURCE_REPOSITORY_DIRTY", source)
        self.assertNotIn('payload.get("force"', source)
        self.assertNotIn('"force":', source)

    # Confirms terminal Local sync and repository edges use handoff without reintroducing source gates.
    def test_repository_edges_handoff_without_a_clean_source_requirement(self) -> None:
        """Use terminal-stage-aware handoff metadata with no source-policy field."""

        source = (Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "syncchains.py").read_text(
            encoding="utf-8",
        )

        self.assertIn('edge_index > 0 or "public_beta" not in chain["stages"]', source)
        self.assertNotIn('"requires_clean_source"', source)


if __name__ == "__main__":
    unittest.main()
