"""Regression coverage for the Local Mode full-screen project library."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gitdesk.localproject_icon_bridge import handle_local_project_icon_previews


# A passive SVG fixture proves every library preview still passes through the established validation boundary.
SAFE_SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="8" height="8"/></svg>'


# ProjectLibraryBackendTests keeps icon-preview reads isolated from settings persistence and project mutation.
class ProjectLibraryBackendTests(unittest.TestCase):
    """Verify the page-only artwork action returns safe previews for every saved project."""

    # Creates two custom-icon projects and proves inactive artwork is available only through the library action.
    def test_library_preview_action_encodes_all_saved_project_icons(self) -> None:
        """Return validated data URLs for active and inactive projects without saving settings."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            projects = []
            # Both saved records receive real in-project artwork so inactive preview behavior is observable.
            for name in ("active", "inactive"):
                project_path = root / name
                project_path.mkdir()
                icon_path = project_path / "icon.svg"
                icon_path.write_bytes(SAFE_SVG)
                projects.append({"path": str(project_path), "name": name, "icon_path": str(icon_path)})
            controller = mock.Mock()
            controller.settings_store.load.return_value = {"local_projects": projects}

            response = handle_local_project_icon_previews(controller)

            expected_paths = [str(root / "active"), str(root / "inactive")]

        self.assertEqual([preview["path"] for preview in response["projects"]], expected_paths)
        self.assertTrue(all(
            preview["icon_data_url"].startswith("data:image/svg+xml;base64,")
            for preview in response["projects"]
        ))
        controller.settings_store.save.assert_not_called()

    # Confirms inactive projects can use latest-version app artwork without adding bytes to routine Local state.
    def test_library_preview_action_encodes_automatic_latest_version_icon(self) -> None:
        """Return a validated app-icon.svg preview when no custom icon_path is saved."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            project_path = Path(temporary_directory) / "project"
            icon_path = project_path / "01 init" / "v1 project" / "media" / "app-icon.svg"
            icon_path.parent.mkdir(parents=True)
            icon_path.write_bytes(SAFE_SVG)
            controller = mock.Mock()
            controller.settings_store.load.return_value = {
                "local_projects": [{"path": str(project_path), "name": "project"}],
            }

            response = handle_local_project_icon_previews(controller)

        self.assertEqual(response["projects"][0]["path"], str(project_path))
        self.assertTrue(response["projects"][0]["icon_data_url"].startswith("data:image/svg+xml;base64,"))
        controller.settings_store.save.assert_not_called()


# ProjectLibrarySourceTests protects page composition, canonical selection reuse, and both asset delivery paths.
class ProjectLibrarySourceTests(unittest.TestCase):
    """Verify the categorized icon grid, size control, and Local Mode integration from current source."""

    # Reads the focused source files once so each assertion can compare complete implementation surfaces.
    def source(self, relative_path: str) -> str:
        """Return UTF-8 source text for one repository-relative path."""

        root = Path(__file__).resolve().parents[1]
        return (root / relative_path).read_text(encoding="utf-8")

    # Confirms the new trigger, page, slider, category grid, and single-click selection path are all present.
    def test_library_page_uses_categorized_resizable_icon_grid(self) -> None:
        """Require the requested folder-first page and its canonical selection callback."""

        source = self.source("src/gitdesk/ui/local-project-library.js")
        style = self.source("src/gitdesk/ui/local-project-library.css")

        self.assertIn('id="open-local-project-library"', source)
        self.assertIn('aria-label="Open all projects"', source)
        self.assertIn('panel.id = "panel-local-project-library";', source)
        self.assertIn('id="local-project-library-size" type="range"', source)
        self.assertIn("projectPicker.categorizedProjects(projects)", source)
        self.assertIn('data-library-project-path="${escapeHtml(project.path)}"', source)
        self.assertIn("await callbacks.onProjectSelect(path);", source)
        self.assertIn('showPanel("local");', source)
        self.assertIn("grid-template-columns: repeat(auto-fill, var(--local-project-library-tile-size));", style)
        self.assertIn(".local-project-library-name", style)

    # Confirms project images remain page-specific and the standard Local response keeps its active-only contract.
    def test_library_loads_validated_artwork_without_expanding_normal_local_state(self) -> None:
        """Require the read-only preview bridge and unchanged active-only state condition."""

        bridge_source = self.source("src/gitdesk/localproject_icon_bridge.py")
        icon_source = self.source("src/gitdesk/localproject_icons.py")
        local_source = self.source("src/gitdesk/localproject_state.py")
        controller_source = self.source("src/gitdesk/ui/local.js")
        library_source = self.source("src/gitdesk/ui/local-project-library.js")
        picker_source = self.source("src/gitdesk/ui/local-project-picker.js")

        self.assertIn('"localProjectIconPreviews"', bridge_source)
        self.assertIn('project_icon_previews(settings.get("local_projects"))', bridge_source)
        self.assertIn("def project_icon_previews(projects_value: Any)", icon_source)
        self.assertIn('if record["path"] == active_project:', local_source)
        self.assertIn('runAction("localProjectIconPreviews", {}, "")', controller_source)
        self.assertIn("projectPicker.currentVersionPath(project)", library_source)
        self.assertIn("currentVersionPath, render", picker_source)

    # Confirms source and packaged frontends load the library between the shared picker and identity controller.
    def test_library_assets_have_matching_dependency_order(self) -> None:
        """Require identical CSS and JavaScript registration in both frontend delivery paths."""

        index_source = self.source("src/gitdesk/ui/index.html")
        frontend_source = self.source("src/gitdesk/frontend.py")
        for source in (index_source, frontend_source):
            self.assertLess(source.index("local-project-picker.css"), source.index("local-project-library.css"))
            self.assertLess(source.index("local-project-library.css"), source.index("local-version-detail.css"))
            self.assertLess(source.index("local-project-picker.js"), source.index("local-project-library.js"))
            self.assertLess(source.index("local-project-library.js"), source.index("local-project-identity.js"))


if __name__ == "__main__":
    unittest.main()
