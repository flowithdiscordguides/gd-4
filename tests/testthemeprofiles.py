"""Regression coverage for reusable and exportable Theme profiles."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from gitdesk.config import SettingsStore
from gitdesk.settings_preferences import THEME_COLOR_DEFAULTS
from gitdesk.theme_profiles import exported_profile_payload, save_theme_profile, write_exported_profile


class ThemeProfileTests(unittest.TestCase):
    """Verify complete profile persistence, exports, and frontend integration contracts."""

    def settings_store(self, root: Path) -> SettingsStore:
        """Return a settings store isolated below a temporary root."""

        store = SettingsStore()
        store.config_path = root / "settings.json"
        store.repo_settings_store.config_path = root / "reposettings.json"
        return store

    def test_named_profile_persists_complete_colors_and_role_gradients(self) -> None:
        """Save all appearance colors and gradients while excluding the global favorite list."""

        gradient = {
            "type": "linear",
            "angle": 45,
            "center_x": 50,
            "center_y": 50,
            "stops": [{"color": "#112233", "position": 0}, {"color": "#abcdef", "position": 100}],
        }
        profiles = save_theme_profile(
            [],
            "  Night   studio  ",
            THEME_COLOR_DEFAULTS,
            {"dark": {"panel_background": gradient}, "favorites": [gradient]},
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.settings_store(Path(temporary_directory))
            saved = store.save({"theme_profiles": profiles})
            persisted = json.loads(store.config_path.read_text(encoding="utf-8"))

        profile = saved["theme_profiles"][0]
        self.assertEqual(profile["name"], "Night studio")
        self.assertEqual(profile["theme_colors"], THEME_COLOR_DEFAULTS)
        self.assertEqual(profile["theme_gradients"]["dark"]["panel_background"], gradient)
        self.assertNotIn("favorites", profile["theme_gradients"])
        self.assertEqual(persisted["theme_profiles"], saved["theme_profiles"])

    def test_duplicate_profile_name_replaces_the_existing_profile(self) -> None:
        """Keep profile names unique while retaining the stable identifier on replacement."""

        first = save_theme_profile([], "Workspace", THEME_COLOR_DEFAULTS, {})
        second = save_theme_profile(first, "workspace", {"dark": {"body_text": "#123456"}}, {})
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]["id"], first[0]["id"])
        self.assertEqual(second[0]["theme_colors"]["dark"]["body_text"], "#123456")

    def test_export_is_versioned_and_does_not_change_destination_directory_mode(self) -> None:
        """Write portable JSON atomically without applying app-settings permissions to its folder."""

        profile = save_theme_profile([], "Export me", THEME_COLOR_DEFAULTS, {})[0]
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            root.chmod(0o755)
            destination = root / "export.gitdesk-theme.json"
            write_exported_profile(destination, profile)
            exported = json.loads(destination.read_text(encoding="utf-8"))
            directory_mode = root.stat().st_mode & 0o777

        self.assertEqual(exported_profile_payload(profile)["format"], "gitdesk-theme-profile")
        self.assertEqual(exported["version"], 1)
        self.assertEqual(exported["profile"]["name"], "Export me")
        if os.name != "nt":
            self.assertEqual(directory_mode, 0o755)

    def test_frontend_registers_profile_preview_and_native_export(self) -> None:
        """Protect package order, preview semantics, and the native export action."""

        root = Path(__file__).resolve().parents[1]
        ui = root / "src/gitdesk/ui"
        manager = (ui / "theme-profile-manager.js").read_text(encoding="utf-8")
        controller = (ui / "accent-settings.js").read_text(encoding="utf-8")
        settings_css = (ui / "settings.css").read_text(encoding="utf-8")
        bridge = (root / "src/gitdesk/bridge.py").read_text(encoding="utf-8")
        frontend = (root / "src/gitdesk/frontend.py").read_text(encoding="utf-8")
        self.assertIn('callNative("saveThemeProfile"', manager)
        self.assertIn('callNative("exportThemeProfile"', manager)
        self.assertIn("Apply colors to make it active", manager)
        self.assertIn("gradientEditor.profileValue()", controller)
        self.assertIn("gradientEditor.loadProfile", controller)
        self.assertIn("grid-template-columns: repeat(3, minmax(240px, 1fr));", settings_css)
        self.assertIn("theme_profile_handlers(self)", bridge)
        self.assertLess(frontend.index('"theme-profile-manager.js"'), frontend.index('"accent-settings.js"'))


if __name__ == "__main__":
    unittest.main()
