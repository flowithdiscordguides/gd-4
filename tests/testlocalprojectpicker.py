"""Source contracts for stable Local Mode project-dropdown dismissal."""

from __future__ import annotations

from pathlib import Path
import unittest


class LocalProjectPickerSourceTests(unittest.TestCase):
    """Protect mouse-owned dismissal and non-click menu persistence."""

    @classmethod
    def setUpClass(cls) -> None:
        """Load the focused picker source without executing the desktop application."""

        root = Path(__file__).resolve().parents[1]
        cls.source = (root / "src" / "gitdesk" / "ui" / "local-project-picker.js").read_text(
            encoding="utf-8"
        )

    def function_source(self, name: str) -> str:
        """Return one top-level JavaScript function for focused source assertions."""

        start = self.source.index(f"function {name}(")
        end = self.source.find("\nfunction ", start + 1)
        return self.source[start:end if end >= 0 else len(self.source)]

    def test_only_real_mouse_click_handlers_close_the_menu(self) -> None:
        """Keep render and keyboard paths from dismissing an open picker."""

        for function_name in (
            "chooseOption",
            "openCurrentVersion",
            "handleTriggerKeydown",
            "handleMenuKeydown",
            "render",
        ):
            with self.subTest(function_name=function_name):
                self.assertNotIn("closeMenu(", self.function_source(function_name))

        trigger_click = self.function_source("handleTriggerClick")
        menu_click = self.function_source("handleMenuClick")
        document_click = self.function_source("handleDocumentClick")
        self.assertIn("event.detail < 1", trigger_click)
        self.assertIn("event.detail < 1", menu_click)
        self.assertIn("event.detail > 0", document_click)
        self.assertIn("closeMenu(", trigger_click)
        self.assertIn("closeMenu(", menu_click)
        self.assertIn("closeMenu(", document_click)
        self.assertEqual(self.source.count("closeMenu("), 5)
        self.assertIn('document.addEventListener("click", handleDocumentClick);', self.source)
        self.assertNotIn('document.addEventListener("pointerdown",', self.source)

    def test_open_menu_never_repositions_after_the_user_scrolls(self) -> None:
        """Preserve manual scroll through state refresh and remove viewport-driven movement."""

        render_source = self.function_source("render")
        open_source = self.function_source("openMenu")
        self.assertIn("const wasOpen = !menu.hidden;", render_source)
        self.assertIn("const menuScrollTop = wasOpen ? menu.scrollTop : 0;", render_source)
        self.assertIn("const focusedProjectPath =", render_source)
        self.assertIn("if (wasOpen) {", render_source)
        self.assertIn("menu.scrollTop = menuScrollTop;", render_source)
        self.assertIn("(editorAction || target).focus({ preventScroll: true });", render_source)
        self.assertNotIn("positionMenu(", render_source)
        self.assertIn("positionMenu(target);", open_source)
        self.assertEqual(self.source.count("positionMenu("), 2)
        self.assertNotIn("handleViewportChange", self.source)
        self.assertNotIn('addEventListener("scroll",', self.source)
        self.assertNotIn('addEventListener("resize",', self.source)


if __name__ == "__main__":
    unittest.main()
