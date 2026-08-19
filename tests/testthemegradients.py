"""Regression coverage for structured visual theme gradients."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from gitdesk.config import SettingsStore
from gitdesk.settings_preferences import THEME_COLOR_ROLES
from gitdesk.theme_gradients import THEME_GRADIENT_ROLES, clean_theme_gradient, clean_theme_gradients


class ThemeGradientTests(unittest.TestCase):
    """Verify bounded persistence and the visual semantic frontend contract."""

    def settings_store(self, root: Path) -> SettingsStore:
        """Return a settings store isolated below a temporary root."""

        store = SettingsStore()
        store.config_path = root / "settings.json"
        store.repo_settings_store.config_path = root / "reposettings.json"
        return store

    def test_gradient_geometry_and_stops_are_sanitized(self) -> None:
        """Keep safe structured paint data while rejecting CSS strings and unusable stops."""

        gradient = clean_theme_gradient({
            "type": "linear",
            "angle": 999,
            "center_x": -4,
            "center_y": 140,
            "stops": [
                {"color": "#AABBCC", "position": 90},
                {"color": "url(javascript:alert(1))", "position": 50},
                {"color": "#112233", "position": -10},
            ],
        })

        self.assertEqual(gradient["angle"], 359)
        self.assertEqual(gradient["center_x"], 0)
        self.assertEqual(gradient["center_y"], 100)
        self.assertEqual(gradient["stops"], [
            {"color": "#112233", "position": 0},
            {"color": "#aabbcc", "position": 90},
        ])
        self.assertIsNone(clean_theme_gradient({"type": "conic", "stops": []}))
        self.assertIsNone(clean_theme_gradient("linear-gradient(red, blue)"))

    def test_gradient_roles_and_favorites_persist(self) -> None:
        """Round-trip one role and favorite through the allowlisted settings store."""

        gradient = {
            "type": "radial", "angle": 135, "center_x": 25, "center_y": 70,
            "stops": [{"color": "#112233", "position": 0}, {"color": "#abcdef", "position": 100}],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.settings_store(Path(temporary_directory))
            saved = store.save({
                "theme_gradients": {"dark": {"panel_background": gradient}, "favorites": [gradient, gradient]},
            })
            persisted = json.loads(store.config_path.read_text(encoding="utf-8"))

        self.assertEqual(saved["theme_gradients"]["dark"]["panel_background"], gradient)
        self.assertEqual(saved["theme_gradients"]["light"], {})
        self.assertEqual(len(saved["theme_gradients"]["favorites"]), 1)
        self.assertEqual(persisted["theme_gradients"], saved["theme_gradients"])
        self.assertEqual(set(clean_theme_gradients({"dark": {"unknown": gradient}})["dark"]), set())
        self.assertNotIn("notification_glow", THEME_GRADIENT_ROLES)
        self.assertEqual(clean_theme_gradients({"dark": {"notification_glow": gradient}})["dark"], {})

    def test_frontend_keeps_visual_editor_and_semantic_paint_separate(self) -> None:
        """Require visual editing for paintable roles while preserving color-only shadow roles."""

        root = Path(__file__).resolve().parents[1]
        ui = root / "src/gitdesk/ui"
        settings_model = (ui / "theme-settings-model.js").read_text(encoding="utf-8")
        gradient_model = (ui / "theme-gradient-model.js").read_text(encoding="utf-8")
        editor = (ui / "theme-gradient-editor.js").read_text(encoding="utf-8")
        application = (ui / "theme-gradient-application.css").read_text(encoding="utf-8")
        controller = (ui / "accent-settings.js").read_text(encoding="utf-8")
        for role in THEME_COLOR_ROLES:
            self.assertIn(f'role: "{role}"', settings_model)
        self.assertIn('class="theme-gradient-trigger"', editor)
        self.assertIn("Gradient saved to favorites", editor)
        self.assertIn("theme_gradients: gradientEditor.value()", controller)
        self.assertIn("field.supportsGradient !== false", gradient_model)
        self.assertIn('field.supportsGradient === false ? ""', controller)
        self.assertNotIn("linear-gradient(", controller)
        self.assertNotIn("raw CSS", editor)
        self.assertIn("--theme-gradient-panel_background", application)
        self.assertIn("--theme-gradient-body_text", application)
        self.assertIn("border-image: var(--theme-gradient-border_color) 1", application)


if __name__ == "__main__":
    unittest.main()
