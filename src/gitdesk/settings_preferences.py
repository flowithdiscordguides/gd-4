"""Validation helpers for bounded non-secret GitDesk user preferences."""

from __future__ import annotations

import re
from datetime import date
from typing import Any


# Date-only preferences reject timestamps so activity queries retain one unambiguous boundary format.
DATE_SETTINGS = {"activity_tracker_started_on"}

# Theme roles are stable API keys shared with the frontend Color Studio and semantic CSS layer.
THEME_COLOR_ROLES = (
    "body_text",
    "secondary_text",
    "headings",
    "labels",
    "app_background",
    "navigation_background",
    "panel_background",
    "section_background",
    "secondary_background",
    "control_background",
    "modal_background",
    "border_color",
    "notification_glow",
    "accent",
    "primary_actions",
    "selected_controls",
)

# Appearance modes match the browser-local light and dark choices owned by theme.js.
THEME_APPEARANCE_MODES = ("dark", "light")

# Six-digit hex colors keep persisted values compact, predictable, and safe for CSS custom properties.
THEME_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

# Defaults preserve the established GitDesk palettes while separating typography and control roles.
THEME_COLOR_DEFAULTS = {
    "dark": {
        "body_text": "#f4f1ea",
        "secondary_text": "#a0aaa4",
        "headings": "#f4f1ea",
        "labels": "#a0aaa4",
        "app_background": "#080a0d",
        "navigation_background": "#101316",
        "panel_background": "#121619",
        "section_background": "#0b0d10",
        "secondary_background": "#181a1d",
        "control_background": "#1a1c1f",
        "modal_background": "#11161b",
        "border_color": "#272a2b",
        "notification_glow": "#ffffff",
        "accent": "#b9c0c7",
        "primary_actions": "#b9c0c7",
        "selected_controls": "#b9c0c7",
    },
    "light": {
        "body_text": "#17201d",
        "secondary_text": "#64706b",
        "headings": "#17201d",
        "labels": "#64706b",
        "app_background": "#eef1ee",
        "navigation_background": "#f7f9f7",
        "panel_background": "#fafbfa",
        "section_background": "#fafbfa",
        "secondary_background": "#e3e7e4",
        "control_background": "#f9faf9",
        "modal_background": "#ffffff",
        "border_color": "#d3d7d4",
        "notification_glow": "#ffffff",
        "accent": "#5f6972",
        "primary_actions": "#6f7881",
        "selected_controls": "#6f7881",
    },
}


# Returns a deep-enough copy so callers cannot mutate module-owned appearance maps.
def default_theme_colors() -> dict[str, dict[str, str]]:
    """Return fresh dark and light semantic color defaults."""

    return {
        mode: dict(THEME_COLOR_DEFAULTS[mode])
        for mode in THEME_APPEARANCE_MODES
    }


# Accepts one CSS-safe six-digit hex color and otherwise preserves the supplied role default.
def clean_theme_color(value: Any, fallback: str) -> str:
    """Return a normalized hex color or the caller-provided fallback."""

    color = str(value or "").strip()
    return color.lower() if THEME_HEX_COLOR.fullmatch(color) else fallback


# Sanitizes both appearance maps before any color customization can enter settings.json.
def clean_theme_colors(value: Any) -> dict[str, dict[str, str]]:
    """Return complete safe semantic colors from an arbitrary nested value."""

    defaults = default_theme_colors()
    source = value if isinstance(value, dict) else {}
    return {
        mode: {
            role: clean_theme_color(
                (source.get(mode) if isinstance(source.get(mode), dict) else {}).get(role),
                defaults[mode][role],
            )
            for role in THEME_COLOR_ROLES
        }
        for mode in THEME_APPEARANCE_MODES
    }


# Accepts only unambiguous ISO dates for persisted range boundaries.
def clean_date_setting(value: Any) -> str:
    """Return a normalized YYYY-MM-DD setting or an empty string for malformed values."""

    try:
        return date.fromisoformat(str(value or "").strip()).isoformat()
    except ValueError:
        return ""
