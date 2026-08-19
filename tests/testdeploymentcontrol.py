"""Source-level regression coverage for the shared successful deployment-site control."""

from __future__ import annotations

from pathlib import Path
import unittest


# DeploymentSiteControlSourceTests protects shared markup, sizing, consumers, and asset dependency order.
class DeploymentSiteControlSourceTests(unittest.TestCase):
    """Verify Pages and every Actions detail placement reuse one canonical success control."""

    # Loads one repository-relative source file without relying on the process working directory.
    def source(self, relative_path: str) -> str:
        """Return UTF-8 source from the current repository checkout."""

        root = Path(__file__).resolve().parents[1]
        return (root / relative_path).read_text(encoding="utf-8")

    # Confirms both deployment controllers delegate success markup and delegated click parsing.
    def test_pages_and_actions_share_success_renderer(self) -> None:
        """Require one label, one data attribute, and one renderer across all success surfaces."""

        shared = self.source("src/gitdesk/ui/deployment-site-control.js")
        pages = self.source("src/gitdesk/ui/pages-deployment.js")
        actions = self.source("src/gitdesk/ui/actions-deployment.js")
        detail = self.source("src/gitdesk/ui/actions-detail.js")

        self.assertIn("<strong>Visit deployed site</strong>", shared)
        self.assertIn('data-deployment-site-url="${safeUrl}"', shared)
        self.assertIn("deploymentSiteControl.render(url)", pages)
        self.assertIn("deploymentSiteControl.render(url)", actions)
        self.assertIn("deploymentSiteControl.urlFromEvent(event)", pages)
        self.assertIn("deploymentSiteControl.urlFromEvent(event)", actions)
        self.assertEqual(detail.count("deploymentRenderer.render("), 3)
        for obsolete in ("data-pages-url", "data-actions-pages-url", "View deployed site"):
            self.assertNotIn(obsolete, pages + actions)

    # Confirms the proven Pages dimensions are centralized and cannot stretch inside Actions detail grids.
    def test_shared_styles_preserve_pages_dimensions_without_duplicates(self) -> None:
        """Require canonical dimensions, start alignment, and one owner for success styling."""

        shared = self.source("src/gitdesk/ui/deployment-site-control.css")
        pages = self.source("src/gitdesk/ui/pages-deployment.css")
        actions = self.source("src/gitdesk/ui/actions-deployment.css")

        for declaration in (
            "min-height: 42px;",
            "padding: 10px 14px;",
            "border-radius: 12px;",
            "box-shadow: 0 10px 28px rgba(22, 163, 74, 0.24);",
        ):
            self.assertIn(declaration, shared)
        self.assertIn(".actions-detail-pane > .deployment-site-link", shared)
        self.assertIn("align-self: start;", shared)
        self.assertIn("justify-self: start;", shared)
        self.assertIn(".deployment-site-link:focus-visible", shared)
        self.assertNotIn(".pages-publication-link", pages)
        self.assertNotIn("button.actions-pages-result.success", actions)
        self.assertNotIn(".actions-pages-copy", actions)

    # Confirms the shared stylesheet and script load before either surface consumes them.
    def test_shared_assets_load_before_deployment_consumers(self) -> None:
        """Keep standalone and inlined frontend dependency ordering synchronized."""

        index_source = self.source("src/gitdesk/ui/index.html")
        frontend_source = self.source("src/gitdesk/frontend.py")

        for source in (index_source, frontend_source):
            self.assertLess(source.index("deployment-site-control.css"), source.index("pages-deployment.css"))
            self.assertLess(source.index("deployment-site-control.css"), source.index("actions-deployment.css"))
            self.assertLess(source.index("deployment-site-control.js"), source.index("pages-deployment.js"))
            self.assertLess(source.index("deployment-site-control.js"), source.index("actions-deployment.js"))


if __name__ == "__main__":
    unittest.main()
