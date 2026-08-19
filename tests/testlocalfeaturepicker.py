"""Source contracts for the Local Mode ribbon Feature picker."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "src" / "gitdesk" / "ui"


class LocalFeaturePickerSourceTests(unittest.TestCase):
    """Protect form placement, canonical callbacks, and user-owned menu movement."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load focused source without launching the desktop runtime."""

        cls.source = (UI_ROOT / "local-feature-picker.js").read_text(encoding="utf-8")
        cls.style = (UI_ROOT / "local-feature-picker.css").read_text(encoding="utf-8")
        cls.controller = (UI_ROOT / "local.js").read_text(encoding="utf-8")
        cls.render = (UI_ROOT / "local-render.js").read_text(encoding="utf-8")

    def function_source(self, name: str) -> str:
        """Return one JavaScript function body for focused lifecycle assertions."""

        sync_marker = f"function {name}("
        async_marker = f"async function {name}("
        start = self.source.find(sync_marker)
        if start < 0:
            start = self.source.index(async_marker)
        end = self.source.find("\nfunction ", start + 1)
        async_end = self.source.find("\nasync function ", start + 1)
        candidates = [position for position in (end, async_end) if position >= 0]
        return self.source[start:min(candidates) if candidates else len(self.source)]

    def test_form_precedes_ordered_feature_options_in_body_portal(self) -> None:
        """Keep creation fixed above the independently scrollable ordered feature list."""

        form_index = self.source.index('id="local-feature-form"')
        list_index = self.source.index('id="local-feature-picker-list"')
        self.assertLess(form_index, list_index)
        self.assertIn('role="dialog"', self.source)
        self.assertIn('role="menu"', self.source)
        self.assertIn("grid-template-rows: auto minmax(0, 1fr);", self.style)
        self.assertIn("overflow-y: auto;", self.style)
        self.assertIn("scrollbar-gutter: stable;", self.style)
        self.assertNotIn(".sort(", self.function_source("render"))

    def test_open_menu_is_the_only_positioning_path(self) -> None:
        """Never recenter or reposition the Feature menu after the user starts navigating it."""

        render_source = self.function_source("render")
        open_source = self.function_source("openMenu")
        self.assertIn("const listScrollTop = wasOpen ? list.scrollTop : 0;", render_source)
        self.assertIn("list.scrollTop = listScrollTop;", render_source)
        self.assertIn("target.focus({ preventScroll: true });", render_source)
        self.assertNotIn("positionMenu(", render_source)
        self.assertIn("positionMenu();", open_source)
        self.assertEqual(self.source.count("positionMenu("), 2)
        self.assertNotIn('addEventListener("scroll",', self.source)
        self.assertNotIn('addEventListener("resize",', self.source)

    def test_controller_reuses_canonical_create_and_select_actions(self) -> None:
        """Route relocated controls through existing backend actions with one creation-pending owner."""

        self.assertIn('runAction("createLocalFeature"', self.controller)
        self.assertIn('runAction("selectLocalFeature"', self.controller)
        self.assertIn("onFeatureCreate: createFeature", self.controller)
        self.assertIn("onFeatureSelect: selectFeature", self.controller)
        self.assertIn("creating = true;", self.source)
        self.assertIn("creating = false;", self.source)
        self.assertIn("if (failed) {", self.source)
        self.assertIn('input.value = "";', self.source)
        self.assertNotIn('id="local-features-card"', self.render)

    def test_ribbon_trigger_exposes_accessible_feature_context(self) -> None:
        """Keep the Feature field adjacent to Project with explicit popup ownership and state."""

        self.assertIn('id="local-feature-picker-trigger"', self.render)
        self.assertIn('aria-haspopup="dialog"', self.render)
        self.assertIn('aria-controls="local-feature-picker-menu"', self.render)
        self.assertIn('id="local-feature-picker-label"', self.render)
        self.assertIn('aria-checked="${selected}"', self.source)
        self.assertIn("byId(TRIGGER_ID).disabled = !projectAvailable;", self.source)

    def test_assets_and_selected_theme_roles_are_registered(self) -> None:
        """Deliver both picker assets and keep its selected option in the shared selected-control theme."""

        index_source = (UI_ROOT / "index.html").read_text(encoding="utf-8")
        frontend_source = (ROOT / "src" / "gitdesk" / "frontend.py").read_text(encoding="utf-8")
        manifest_source = (ROOT / "src" / "gitdesk.egg-info" / "SOURCES.txt").read_text(encoding="utf-8")
        accent_source = (UI_ROOT / "accent-theme.css").read_text(encoding="utf-8")
        gradient_source = (UI_ROOT / "theme-gradient-application.css").read_text(encoding="utf-8")
        for source in (index_source, frontend_source):
            self.assertLess(source.index("local-feature-picker.css"), source.index("local-version-detail.css"))
            self.assertLess(source.index("local-feature-picker.js"), source.index("local.js"))
        self.assertIn("src/gitdesk/ui/local-feature-picker.css", manifest_source)
        self.assertIn("src/gitdesk/ui/local-feature-picker.js", manifest_source)
        self.assertIn("tests/testlocalfeaturepicker.py", manifest_source)
        self.assertIn(".local-feature-picker-option.selected", accent_source)
        self.assertIn(".local-feature-picker-option.selected", gradient_source)


if __name__ == "__main__":
    unittest.main()
