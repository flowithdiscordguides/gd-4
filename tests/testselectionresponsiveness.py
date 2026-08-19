"""Regression coverage for Local project and managed repository selection latency."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gitdesk.gitops import GitService
from gitdesk.localproject_state import local_project_selection_state, local_project_selection_update


class LocalProjectSelectionStateTests(unittest.TestCase):
    """Verify targeted Local responses never scan unrelated saved projects."""

    @mock.patch("gitdesk.localproject_state.SharedResourceStore.load", return_value={
        "catalog": {},
        "installations": {},
    })
    @mock.patch("gitdesk.localproject_state.localfeatures.list_features", return_value=[])
    def test_selected_state_scans_only_the_requested_project(self, list_features, load_resources) -> None:
        """Keep cached inactive project trees outside the dropdown selection critical path."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            selected = root / "selected"
            inactive = root / "inactive"
            selected.mkdir()
            inactive.mkdir()
            settings = {
                "workspace_mode": "local",
                "local_projects": [
                    {"path": str(inactive), "name": "inactive"},
                    {"path": str(selected), "name": "selected"},
                ],
                "active_local_project": str(selected),
            }

            state = local_project_selection_state(settings, str(selected))

        self.assertEqual(state["project"]["path"], str(selected))
        self.assertNotIn("projects", state)
        list_features.assert_called_once_with(str(selected))
        load_resources.assert_called_once_with()

    @mock.patch("gitdesk.localproject_state.localfeatures.list_features")
    def test_cached_selection_validation_does_not_scan_the_project(self, list_features) -> None:
        """Keep a valid cached feature and version on the bounded acknowledgement path."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            project = Path(temporary_directory) / "project"
            feature = project / "01 init"
            version = feature / "v1 project"
            version.mkdir(parents=True)
            canonical_feature = str(feature.resolve())
            canonical_version = str(version.resolve())
            settings = {"local_projects": [{"path": str(project), "name": "project"}]}

            update = local_project_selection_update(
                settings,
                str(project),
                str(feature),
                str(version),
            )

        self.assertEqual(update["active_local_project"], str(project))
        self.assertEqual(update["active_local_feature"], canonical_feature)
        self.assertEqual(update["active_local_version"], canonical_version)
        list_features.assert_not_called()

    def test_stale_cached_children_are_cleared_inside_the_saved_project(self) -> None:
        """Acknowledge the project without accepting stale or unrelated cached child paths."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project = root / "project"
            unrelated = root / "unrelated" / "v1"
            project.mkdir()
            unrelated.mkdir(parents=True)
            settings = {"local_projects": [{"path": str(project), "name": "project"}]}

            update = local_project_selection_update(
                settings,
                str(project),
                str(unrelated.parent),
                str(unrelated),
            )

        self.assertEqual(update["active_local_project"], str(project))
        self.assertEqual(update["active_local_feature"], "")
        self.assertEqual(update["active_local_version"], "")


class RepositorySelectionStateTests(unittest.TestCase):
    """Verify one repository handle supplies every dropdown selection payload."""

    @mock.patch("gitdesk.gitops.open_repository")
    def test_repository_selection_opens_the_working_tree_once(self, open_repository) -> None:
        """Avoid reopening one selected repository for summary, status, and branches."""

        repository = mock.Mock()
        repository.working_tree_dir = "/repository"
        repository.remotes = []
        repository.active_branch.name = "main"
        repository.heads = []
        repository.git.status.return_value = ""
        repository.git.rev_parse.return_value = "commit"
        open_repository.return_value = repository

        state = GitService().repository_selection_state("/repository")

        open_repository.assert_called_once_with("/repository")
        repository.git.status.assert_called_once_with("--porcelain=v1", "-z", "--untracked-files=all")
        self.assertIs(state["status"]["repository"], state["repository"])
        self.assertEqual(state["branches"]["current"], "main")


class SelectionResponsivenessSourceTests(unittest.TestCase):
    """Protect targeted response integration and immediate repository loading feedback."""

    def source(self, relative_path: str) -> str:
        """Return one current UTF-8 source file without launching GitDesk."""

        root = Path(__file__).resolve().parents[1]
        return (root / relative_path).read_text(encoding="utf-8")

    def function_source(self, source: str, name: str) -> str:
        """Return one Python or JavaScript function for focused source assertions."""

        for prefix in (f"def {name}(", f"async function {name}(", f"function {name}("):
            start = source.find(prefix)
            if start >= 0:
                break
        self.assertGreaterEqual(start, 0)
        candidates = [
            source.find("\ndef ", start + 1),
            source.find("\nasync function ", start + 1),
            source.find("\nfunction ", start + 1),
        ]
        ends = [candidate for candidate in candidates if candidate >= 0]
        return source[start:min(ends) if ends else len(source)]

    def test_create_and_project_selection_keep_scans_out_of_acknowledgement(self) -> None:
        """Keep hierarchy scans out of create reuse and the dropdown acknowledgement path."""

        bridge = self.source("src/gitdesk/localproject_selection_bridge.py")
        project_bridge = self.source("src/gitdesk/localproject_bridge.py")
        controller = self.source("src/gitdesk/ui/local-project-selection.js")
        create_source = self.function_source(project_bridge, "handle_create_local_project")
        select_source = self.function_source(bridge, "handle_select_local_project")
        refresh_source = self.function_source(bridge, "handle_local_project_selection_state")
        controller_select = self.function_source(controller, "select")

        self.assertIn("local_project_selection_state(", create_source)
        self.assertIn("local_project_selection_update(", select_source)
        self.assertNotIn("local_projects_state(", create_source)
        self.assertNotIn("local_projects_state(", select_source)
        self.assertNotIn("local_project_selection_state(", select_source)
        self.assertNotIn("list_features(", select_source)
        self.assertIn("local_project_selection_state(", refresh_source)
        self.assertLess(controller_select.index("applyResponse(data);"), controller_select.index("refresh(path"))
        self.assertIn("localProjectIdentity.setPending(true);", controller_select)
        self.assertIn("icon_data_url: \"\"", controller)

    def test_project_selection_module_loads_between_identity_and_local_controller(self) -> None:
        """Keep both frontend assembly paths and the installed source list synchronized."""

        index = self.source("src/gitdesk/ui/index.html")
        frontend = self.source("src/gitdesk/frontend.py")
        sources = self.source("src/gitdesk.egg-info/SOURCES.txt")
        for source in (index, frontend):
            self.assertLess(source.index("local-project-identity.js"), source.index("local-project-selection.js"))
            self.assertLess(source.index("local-project-selection.js"), source.index("local.js"))
        self.assertIn("src/gitdesk/localproject_selection_bridge.py", sources)
        self.assertIn("src/gitdesk/ui/local-project-selection.js", sources)

    def test_repository_selection_reports_loading_and_restores_failure(self) -> None:
        """Show immediate feedback while preserving the prior saved choice on a failed switch."""

        controller = self.source("src/gitdesk/ui/repositories.js")
        selection = self.function_source(controller, "selectManagedRepository")

        self.assertIn("Loading repository status and branches", selection)
        self.assertIn("const previousPath = activePathFromSettings();", selection)
        self.assertIn('byId("managed-repo-select").value = previousPath;', selection)
        self.assertIn("renderPicker();", selection)


if __name__ == "__main__":
    unittest.main()
