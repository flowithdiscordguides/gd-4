"""Regression coverage for Local Mode project-icon safety and persistence."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from gitdesk.errors import AppError
from gitdesk import localfeatures
from gitdesk import localproject_icons
from gitdesk.localproject_icon_bridge import handle_choose_local_project_icon
from gitdesk.localproject_icon_bridge import handle_clear_local_project_icon
from gitdesk.localproject_records import clean_local_project_record
from gitdesk import localprojects
from gitdesk.reposettings_schema import REPO_SETTINGS_SCHEMA_VERSION


# A complete passive SVG fixture exercises validation and data-URL encoding without external resources.
SAFE_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">
  <defs><linearGradient id="g"><stop stop-color="#fff"/></linearGradient></defs>
  <rect width="16" height="16" fill="url(#g)"/>
</svg>"""

# A compact one-pixel PNG fixture proves raster artwork follows the same bounded data-URL path.
SAFE_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d4944415408d763f8cfc0f01f00050001ff89993d1d0000000049454e44ae426082"
)


# LocalProjectIconTests isolates every filesystem and metadata assertion inside disposable project folders.
class LocalProjectIconTests(unittest.TestCase):
    """Verify validation, priority resolution, registry updates, and active preview state."""

    # Writes one safe SVG inside a temporary project and returns both paths for focused assertions.
    def project_with_icon(self, root: Path) -> tuple[Path, Path]:
        """Return a project folder and safe SVG icon created below the supplied temporary root."""

        project_path = root / "project"
        project_path.mkdir()
        icon_path = project_path / "art" / "project-icon.svg"
        icon_path.parent.mkdir()
        icon_path.write_bytes(SAFE_SVG)
        return project_path, icon_path

    # Creates one physical version with the canonical automatic app icon location.
    def version_with_app_icon(
        self,
        project_path: Path,
        feature_name: str,
        version_name: str,
        content: bytes = SAFE_SVG,
    ) -> Path:
        """Return a safe app-icon.svg path inside one ordered feature/version pair."""

        icon_path = project_path / feature_name / version_name / "media" / "app-icon.svg"
        icon_path.parent.mkdir(parents=True)
        icon_path.write_bytes(content)
        return icon_path

    # Confirms the private LocalApp project record preserves only an icon contained by its own project.
    def test_record_sanitizer_preserves_only_in_project_icon_paths(self) -> None:
        """Keep a normalized in-project icon path and discard a path outside the project boundary."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project_path, icon_path = self.project_with_icon(root)
            inside = clean_local_project_record({
                "path": str(project_path),
                "name": "project",
                "category": "Game",
                "icon_path": str(icon_path),
            })
            outside = clean_local_project_record({
                "path": str(project_path),
                "name": "project",
                "icon_path": str(root / "outside.svg"),
            })

        self.assertEqual(inside["icon_path"], str(icon_path.resolve()))
        self.assertEqual(outside["icon_path"], "")

    # Confirms selection rejects otherwise valid image content when it lives outside the active project.
    def test_icon_must_live_inside_active_project(self) -> None:
        """Raise LOCAL_PROJECT_ICON_OUTSIDE_PROJECT for an external selected image path."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project_path = root / "project"
            project_path.mkdir()
            icon_path = root / "external.svg"
            icon_path.write_bytes(SAFE_SVG)

            with self.assertRaises(AppError) as raised:
                localproject_icons.validated_project_icon_path(project_path, icon_path)

        self.assertEqual(raised.exception.code, "LOCAL_PROJECT_ICON_OUTSIDE_PROJECT")

    # Confirms an SVG cannot use script handlers or remote URL references even inside an image element.
    def test_svg_preview_rejects_active_or_external_content(self) -> None:
        """Reject scriptable SVG and presentation attributes that load network content."""

        unsafe_sources = (
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            b'<svg xmlns="http://www.w3.org/2000/svg"><rect fill="url(https://example.com/a.svg)"/></svg>',
            b'<svg xmlns="http://www.w3.org/2000/svg">'
            b'<animate attributeName="href" values="https://example.com"/></svg>',
        )
        for source in unsafe_sources:
            with self.subTest(source=source):
                with self.assertRaises(AppError) as raised:
                    localproject_icons.validate_svg_bytes(source)
                self.assertEqual(raised.exception.code, "LOCAL_PROJECT_ICON_SVG_UNSAFE")

    # Confirms a passive SVG is encoded for preview and its absolute path survives unrelated metadata fields.
    def test_safe_svg_is_encoded_and_saved_without_copying(self) -> None:
        """Return an SVG data URL and update only the matched project's icon_path field."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project_path, icon_path = self.project_with_icon(root)
            settings = {
                "local_projects": [{
                    "path": str(project_path),
                    "name": "project",
                    "category": "Game",
                }],
                "active_local_project": str(project_path),
            }

            data_url = localproject_icons.project_icon_data_url(project_path, icon_path)
            updates = localproject_icons.local_project_icon_update(settings, project_path, icon_path)

        self.assertTrue(data_url.startswith("data:image/svg+xml;base64,"))
        self.assertEqual(updates["local_projects"][0]["category"], "Game")
        self.assertEqual(updates["local_projects"][0]["icon_path"], str(icon_path.resolve()))

    # Confirms supported raster content uses its factual MIME type and remains subject to the icon size boundary.
    def test_png_preview_and_size_limit(self) -> None:
        """Encode a valid PNG and reject an otherwise supported file larger than five megabytes."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            project_path = Path(temporary_directory) / "project"
            project_path.mkdir()
            icon_path = project_path / "project.png"
            icon_path.write_bytes(SAFE_PNG)
            data_url = localproject_icons.project_icon_data_url(project_path, icon_path)
            icon_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * localproject_icons.MAX_PROJECT_ICON_BYTES)
            with self.assertRaises(AppError) as raised:
                localproject_icons.project_icon_data_url(project_path, icon_path)

        self.assertTrue(data_url.startswith("data:image/png;base64,"))
        self.assertEqual(raised.exception.code, "LOCAL_PROJECT_ICON_TOO_LARGE")

    # Confirms automatic artwork follows the same latest-feature/latest-version definition as current work.
    def test_latest_version_app_icon_is_the_automatic_project_artwork(self) -> None:
        """Use media/app-icon.svg from the last ordered feature containing a physical version."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            project_path = Path(temporary_directory) / "project"
            project_path.mkdir()
            self.version_with_app_icon(project_path, "01 init", "v1 project")
            latest_svg = b'<svg xmlns="http://www.w3.org/2000/svg"><circle cx="4" cy="4" r="4"/></svg>'
            latest_icon = self.version_with_app_icon(project_path, "02 polish", "v2 project", latest_svg)
            (project_path / "03 empty").mkdir()
            settings = {
                "local_projects": [{"path": str(project_path), "name": "project"}],
                "active_local_project": str(project_path),
            }

            state = localprojects.local_projects_state(settings)
            project = state["projects"][0]
            expected_data_url = localproject_icons.project_icon_data_url(project_path, latest_icon)

        self.assertEqual(project["icon_source"], "app")
        self.assertEqual(project["icon_name"], "app-icon.svg")
        self.assertEqual(project["icon_path"], "")
        self.assertEqual(project["icon_data_url"], expected_data_url)

    # Confirms saved pencil artwork remains definitive even when the current version has an automatic app icon.
    def test_saved_custom_icon_overrides_latest_version_app_icon(self) -> None:
        """Prefer the validated icon_path and do not fall through when that explicit override becomes stale."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            project_path = Path(temporary_directory) / "project"
            project_path.mkdir()
            self.version_with_app_icon(project_path, "01 init", "v1 project")
            custom_icon = project_path / "project-icon.svg"
            custom_icon.write_bytes(
                b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h8v8H0z"/></svg>',
            )
            record = {"path": str(project_path), "name": "project", "icon_path": str(custom_icon)}
            features = localfeatures.list_features(str(project_path))

            expected_data_url = localproject_icons.project_icon_data_url(project_path, custom_icon)
            preview = localproject_icons.project_icon_preview(record, features)
            custom_icon.unlink()
            stale_preview = localproject_icons.project_icon_preview(record, features)

        self.assertEqual(preview["icon_source"], "custom")
        self.assertEqual(preview["icon_data_url"], expected_data_url)
        self.assertEqual(stale_preview["icon_source"], "custom")
        self.assertEqual(stale_preview["icon_data_url"], "")

    # Confirms only the active project's priority-resolved artwork is serialized into derived frontend state.
    def test_local_state_encodes_only_active_project_preview(self) -> None:
        """Keep inactive icon paths as metadata while omitting their potentially expensive preview bytes."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            active_project, active_icon = self.project_with_icon(root)
            inactive_project = root / "inactive"
            inactive_project.mkdir()
            inactive_icon = inactive_project / "inactive.svg"
            inactive_icon.write_bytes(SAFE_SVG)
            settings = {
                "local_projects": [
                    {"path": str(active_project), "name": "active", "icon_path": str(active_icon)},
                    {"path": str(inactive_project), "name": "inactive", "icon_path": str(inactive_icon)},
                ],
                "active_local_project": str(active_project),
            }

            state = localprojects.local_projects_state(settings)

        projects = {project["path"]: project for project in state["projects"]}
        self.assertTrue(projects[str(active_project)]["icon_data_url"])
        self.assertEqual(projects[str(inactive_project)]["icon_data_url"], "")
        self.assertEqual(projects[str(inactive_project)]["icon_path"], str(inactive_icon.resolve()))

    # Confirms choose and clear bridge actions persist canonical state while cancellation remains non-mutating.
    def test_icon_bridge_saves_and_clears_private_registry_metadata(self) -> None:
        """Persist a chosen icon path, then clear it without modifying the project folder or active selection."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            project_path, icon_path = self.project_with_icon(root)
            settings = {
                "local_projects": [{"path": str(project_path), "name": "project"}],
                "active_local_project": str(project_path),
            }
            controller = mock.Mock()
            controller.settings_store.load.return_value = settings
            controller.settings_store.save.side_effect = lambda updates: {**settings, **updates}

            with mock.patch("gitdesk.localproject_icon_bridge.choose_file", return_value=""):
                cancelled = handle_choose_local_project_icon(controller, {})
            controller.settings_store.save.assert_not_called()
            with mock.patch("gitdesk.localproject_icon_bridge.choose_file", return_value=str(icon_path)):
                chosen = handle_choose_local_project_icon(controller, {})
            controller.settings_store.load.return_value = chosen["settings"]
            controller.settings_store.save.side_effect = lambda updates: {**chosen["settings"], **updates}
            cleared = handle_clear_local_project_icon(controller, {})

        self.assertTrue(cancelled["cancelled"])
        self.assertEqual(chosen["settings"]["local_projects"][0]["icon_path"], str(icon_path.resolve()))
        self.assertEqual(cleared["settings"]["local_projects"][0]["icon_path"], "")
        self.assertEqual(cleared["settings"]["active_local_project"], str(project_path))
        self.assertEqual(cleared["local"]["projects"][0]["icon_source"], "")
        self.assertEqual(cleared["local"]["projects"][0]["icon_data_url"], "")

    # Protects the schema marker so recovery knows records include artwork and physical category-layout metadata.
    def test_registry_schema_marks_project_icon_metadata(self) -> None:
        """Require repository registry schema version four for complete Local Mode project records."""

        self.assertEqual(REPO_SETTINGS_SCHEMA_VERSION, 4)


if __name__ == "__main__":
    unittest.main()
