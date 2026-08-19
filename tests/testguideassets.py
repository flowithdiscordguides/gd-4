"""Regression coverage for the modular standalone and in-app GitDesk Guide assets."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from gitdesk.app import frontend_asset_path, render_guide_document, serve_frontend_file


# GuideAssetTests protects asset routing after the oversized inline guide was split into packaged modules.
class GuideAssetTests(unittest.TestCase):
    """Verify guide modules and existing screenshots resolve without embedded base64 data."""

    # Confirms in-app rendering rewrites standalone nested paths to WebUI's one-segment asset routes.
    def test_rendered_guide_uses_in_app_asset_bases(self) -> None:
        """Return guide markup with local CSS, JavaScript, and screenshot bases."""

        document = render_guide_document()

        self.assertIsNotNone(document)
        self.assertIn('href="./gitdesk-guide-layout.css"', document)
        self.assertIn('href="./gitdesk-guide-learning.css"', document)
        self.assertIn('href="./gitdesk-guide-learning-responsive.css"', document)
        self.assertIn('src="./gitdesk-guide-topics-local.js"', document)
        self.assertIn('src="./gitdesk-guide-topic-contracts.js"', document)
        self.assertIn('src="./gitdesk-guide-interactions.js"', document)
        self.assertIn('data-guide-asset-base="./"', document)
        self.assertIn('data-guide-media-base="./"', document)
        self.assertNotIn("data:image/png;base64", document)

    # Prevents a new topic from shipping without the instructional contract rendered by the Field Manual.
    def test_every_guide_topic_has_a_learning_contract(self) -> None:
        """Require unique teaching headings, guideposts, practice, proof, and recovery for every topic."""

        ui_root = Path(__file__).resolve().parents[1] / "src" / "gitdesk" / "ui"
        topic_paths = (
            ui_root / "gitdesk-guide-topics-primary.js",
            ui_root / "gitdesk-guide-topics-local.js",
            ui_root / "gitdesk-guide-topics-secondary.js",
        )
        topic_ids = {
            match
            for path in topic_paths
            for match in re.findall(r'^\s+id: "([^"]+)",$', path.read_text(encoding="utf-8"), re.MULTILINE)
        }
        contracts = (ui_root / "gitdesk-guide-topic-contracts.js").read_text(encoding="utf-8")
        contract_matches = re.findall(
            r'^  (?:"([^"]+)"|([a-z]+)): \{$',
            contracts,
            re.MULTILINE,
        )
        contract_ids = {quoted or unquoted for quoted, unquoted in contract_matches}

        self.assertEqual(topic_ids, contract_ids)
        for field_name in ("sectionTitle", "goals", "guideposts", "prerequisite", "practice", "proof", "recovery"):
            self.assertEqual(contracts.count(f"    {field_name}:"), len(topic_ids))

        section_titles = re.findall(r'^    sectionTitle: "([^"]+)",$', contracts, re.MULTILINE)
        self.assertEqual(len(section_titles), len(set(section_titles)))
        self.assertNotIn("talking" + "Points", contracts)

        control_sources = "\n".join(path.read_text(encoding="utf-8") for path in topic_paths)
        self.assertNotIn('["none",', control_sources)
        icon_names = set(re.findall(r'^\s+\["([A-Za-z]+)",', control_sources, re.MULTILINE))
        icon_names.discard("group")
        known_icons = {
            "actions", "app", "branches", "category", "clone", "compare", "copy", "debug", "favorite",
            "folder", "guide", "ignore", "image", "local", "newProject", "newTag", "newVersion", "note",
            "overview", "pages", "releases", "rename", "resources", "settings", "sync", "syncChain", "theme",
            "trash", "vscode",
        }
        self.assertEqual(icon_names, known_icons)

    # Confirms source execution maps the fixed screenshot alias to the existing documentation-media file.
    def test_source_guide_screenshot_resolves_to_existing_png(self) -> None:
        """Resolve the encoded header screenshot request to a real non-empty PNG path."""

        image_path = frontend_asset_path("/1%29header.png")

        self.assertIsNotNone(image_path)
        self.assertTrue(image_path.is_file())
        self.assertGreater(image_path.stat().st_size, 0)

    # Confirms the WebUI response boundary sends screenshot bytes with the correct content type.
    def test_guide_screenshot_response_is_png(self) -> None:
        """Return a successful image/png response for an existing guide screenshot."""

        response = serve_frontend_file("/1%29header.png")

        self.assertIsNotNone(response)
        self.assertTrue(response.startswith("HTTP/1.1 200 OK\r\n"))
        self.assertIn("Content-Type: image/png\r\n", response)

    # Keeps checkout-relative Guide tests on source imports after the workflow installs build dependencies.
    def test_build_workflow_runs_guide_regressions_from_source_tree(self) -> None:
        """Set the source import boundary on the exact cross-platform unittest step."""

        workflow_path = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "build-app.yml"
        workflow = workflow_path.read_text(encoding="utf-8")
        test_step = workflow.split("- name: Run persistence and permission regression tests", 1)[1]
        test_step = test_step.split("- name:", 1)[0]

        self.assertIn('python -m unittest discover -s tests -p "test*.py"', test_step)
        self.assertIn("PYTHONPATH: src", test_step)


if __name__ == "__main__":
    unittest.main()
