"""Regression coverage for semantic theme-color persistence and frontend integration."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from gitdesk.config import SettingsStore
from gitdesk.frontend import INLINE_SCRIPTS, INLINE_STYLES
from gitdesk.settings_preferences import THEME_APPEARANCE_MODES, THEME_COLOR_DEFAULTS, THEME_COLOR_ROLES
from gitdesk.settings_preferences import clean_theme_colors


# ThemeSettingsTests isolates preferences and validates the source-level delivery contract.
class ThemeSettingsTests(unittest.TestCase):
    """Verify sanitation, persistence, tab placement, accessibility, and package registration."""

    # Builds a real settings store redirected entirely into one disposable test directory.
    def settings_store(self, root: Path) -> SettingsStore:
        """Return an isolated SettingsStore whose files remain below root."""

        store = SettingsStore()
        store.config_path = root / "settings.json"
        store.repo_settings_store.config_path = root / "reposettings.json"
        return store

    # Confirms every appearance and semantic role accepts only normalized six-digit hex colors.
    def test_theme_colors_are_complete_and_hex_sanitized(self) -> None:
        """Keep complete dark/light role maps while rejecting unsafe or malformed CSS values."""

        source = {
            mode: {role: "#A1B2C3" for role in THEME_COLOR_ROLES}
            for mode in THEME_APPEARANCE_MODES
        }
        cleaned = clean_theme_colors(source)
        self.assertEqual(len(THEME_COLOR_ROLES), 16)
        self.assertEqual(THEME_COLOR_DEFAULTS["dark"]["notification_glow"], "#ffffff")
        self.assertEqual(THEME_COLOR_DEFAULTS["light"]["notification_glow"], "#ffffff")
        for mode in THEME_APPEARANCE_MODES:
            self.assertEqual(set(cleaned[mode]), set(THEME_COLOR_ROLES))
            self.assertEqual(set(cleaned[mode].values()), {"#a1b2c3"})

        invalid = clean_theme_colors({
            "dark": {"body_text": "red", "accent": "var(--secret)"},
            "light": {"labels": "#12345", "primary_actions": "#12345678"},
            "unknown": {"body_text": "#000000"},
        })
        self.assertEqual(invalid, THEME_COLOR_DEFAULTS)

        legacy = clean_theme_colors({"dark": {"body_text": "#123456"}})
        self.assertEqual(legacy["dark"]["body_text"], "#123456")
        self.assertEqual(legacy["dark"]["panel_background"], THEME_COLOR_DEFAULTS["dark"]["panel_background"])

    # Confirms settings.json receives only the complete sanitized theme object and drops the retired accent key.
    def test_theme_colors_persist_through_the_allowlisted_store(self) -> None:
        """Persist valid semantic colors while rejecting malformed, retired, and unknown setting values."""

        with tempfile.TemporaryDirectory() as temporary_directory:
            store = self.settings_store(Path(temporary_directory))
            custom = {
                mode: {
                    role: "#123456" if role == "accent" else THEME_COLOR_DEFAULTS[mode][role]
                    for role in THEME_COLOR_ROLES
                }
                for mode in THEME_APPEARANCE_MODES
            }
            custom["light"]["labels"] = "javascript:alert(1)"
            saved = store.save({
                "theme_colors": custom,
                "accent_colors": {"scope": "global", "global": "ruby"},
                "untrusted_setting": "must not persist",
            })
            persisted = json.loads(store.config_path.read_text(encoding="utf-8"))

        self.assertEqual(saved["theme_colors"]["dark"]["accent"], "#123456")
        self.assertEqual(saved["theme_colors"]["light"]["labels"], THEME_COLOR_DEFAULTS["light"]["labels"])
        self.assertEqual(persisted["theme_colors"], saved["theme_colors"])
        self.assertNotIn("accent_colors", persisted)
        self.assertNotIn("untrusted_setting", persisted)

    # Protects tab order, package delivery, semantic roles, continuous color selection, and save freedom.
    def test_frontend_registers_dedicated_theme_color_studio(self) -> None:
        """Require the Theme tab, custom wheel, unrestricted valid colors, and appearance synchronization."""

        root = Path(__file__).resolve().parents[1]
        ui_root = root / "src" / "gitdesk" / "ui"
        tabs = (ui_root / "settings-tabs.js").read_text(encoding="utf-8")
        controller = (ui_root / "accent-settings.js").read_text(encoding="utf-8")
        settings_model = (ui_root / "theme-settings-model.js").read_text(encoding="utf-8")
        color_wheel = (ui_root / "theme-color-wheel.js").read_text(encoding="utf-8")
        theme_manager = (ui_root / "theme.js").read_text(encoding="utf-8")
        workspace = (ui_root / "workspace-mode.js").read_text(encoding="utf-8")
        app = (ui_root / "app.js").read_text(encoding="utf-8")
        theme = (ui_root / "accent-theme.css").read_text(encoding="utf-8")
        settings_css = (ui_root / "accent-settings.css").read_text(encoding="utf-8")
        wheel_css = (ui_root / "theme-color-wheel.css").read_text(encoding="utf-8")
        index = (ui_root / "index.html").read_text(encoding="utf-8")
        frontend = (root / "src" / "gitdesk" / "frontend.py").read_text(encoding="utf-8")

        self.assertLess(tabs.index('data-settings-tab="system"'), tabs.index('data-settings-tab="theme"'))
        self.assertIn('id="settings-theme-content"', tabs)
        self.assertIn('data-settings-panel="theme"', tabs)
        self.assertNotIn('type="color"', controller)
        self.assertIn('class="theme-color-swatch"', controller)
        self.assertIn("colorWheel.open(swatch", controller)
        self.assertIn('id="apply-theme-settings"', controller)
        self.assertIn('id="reset-theme-settings"', controller)
        self.assertIn('role="group" aria-label="Appearance colors to edit"', controller)
        self.assertIn('button.setAttribute("aria-pressed"', controller)
        self.assertIn('aria-haspopup="dialog"', controller)
        self.assertNotIn("allContrastIssues", controller)
        self.assertNotIn("Increase contrast", controller)
        self.assertIn('disabled = busy || draftIsSaved()', controller)
        self.assertNotIn('document.getElementById("settings-user-content")', controller)
        for role in THEME_COLOR_ROLES:
            self.assertIn(f'role: "{role}"', settings_model)
        self.assertIn("window.GitDeskThemeSettings = { applySettings };", controller)
        self.assertIn("themeSettings.applySettings(state.settings);", app)
        self.assertIn('new CustomEvent("gitdesk:theme-changed"', theme_manager)
        self.assertNotIn("GitDeskAccentSettings", workspace)
        self.assertIn("--theme-heading-color", theme)
        self.assertIn("--theme-primary-action", theme)
        self.assertIn("--theme-selected-control", theme)
        self.assertIn("--theme-app-background", theme)
        self.assertIn("--theme-navigation-background", theme)
        self.assertIn("--theme-panel-background", theme)
        self.assertIn("--theme-section-background", theme)
        self.assertIn("--theme-secondary-background", theme)
        self.assertIn("--theme-control-background", theme)
        self.assertIn("--theme-modal-background", theme)
        self.assertIn("--theme-border-color", theme)
        self.assertIn("--theme-notification-glow", theme)
        self.assertIn('role: "notification_glow"', settings_model)
        self.assertIn('label: "Notification glow"', settings_model)
        self.assertIn('supportsGradient: false', settings_model)
        self.assertIn('setProperty("--theme-notification-glow", colors.notification_glow)', controller)
        self.assertIn('field.supportsGradient === false ? ""', controller)
        self.assertGreaterEqual(theme.count(':root[data-theme="dark"]'), 2)
        self.assertGreaterEqual(theme.count(':root[data-theme="light"]'), 2)
        self.assertIn("--panel: var(--theme-panel-background);", theme)
        self.assertIn("--surface: var(--theme-section-background);", theme)
        self.assertIn("--gitdesk-modal-panel: var(--theme-modal-background);", theme)
        self.assertIn('const COLOR_GROUPS = ["Typography", "Surfaces", "Controls"]', settings_model)
        self.assertIn("theme-color-group-${group.toLowerCase()}", controller)
        self.assertIn(".theme-color-group-surfaces", settings_css)
        self.assertIn("window.GitDeskColorWheel = { bind, close, markup, open };", color_wheel)
        self.assertIn('role="slider"', color_wheel)
        self.assertIn('aria-valuemin="0" aria-valuemax="359"', color_wheel)
        self.assertIn('wheel.addEventListener("pointerdown"', color_wheel)
        self.assertIn("hsvToHex", color_wheel)
        self.assertIn(".theme-color-swatch", settings_css)
        self.assertIn(".theme-live-preview", settings_css)
        self.assertIn("@media (max-width: 520px)", settings_css)
        self.assertIn("conic-gradient", wheel_css)
        self.assertIn(".theme-brightness-slider", wheel_css)
        for source in (index, frontend):
            self.assertLess(source.index("accent-theme.css"), source.index("accent-settings.css"))
            self.assertLess(source.index("accent-settings.css"), source.index("theme-color-wheel.css"))
            self.assertLess(source.index("settings-tabs.js"), source.index("theme-color-wheel.js"))
            self.assertLess(source.index("theme-color-wheel.js"), source.index("accent-settings.js"))
            self.assertLess(source.index("accent-settings.js"), source.index("app.js"))
        self.assertIn("accent-theme.css", INLINE_STYLES)
        self.assertIn("accent-settings.css", INLINE_STYLES)
        self.assertIn("theme-color-wheel.css", INLINE_STYLES)
        self.assertIn("theme-color-wheel.js", INLINE_SCRIPTS)
        self.assertIn("theme-settings-model.js", INLINE_SCRIPTS)
        self.assertIn("theme-gradient-editor.js", INLINE_SCRIPTS)
        self.assertIn("accent-settings.js", INLINE_SCRIPTS)


if __name__ == "__main__":
    unittest.main()
