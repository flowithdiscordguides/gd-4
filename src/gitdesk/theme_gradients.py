"""Validation helpers for structured visual theme gradients."""

from __future__ import annotations

from typing import Any

from gitdesk.settings_preferences import THEME_APPEARANCE_MODES, THEME_COLOR_ROLES, THEME_HEX_COLOR


MAX_GRADIENT_STOPS = 8
MAX_GRADIENT_FAVORITES = 24
GRADIENT_TYPES = {"linear", "radial"}
THEME_GRADIENT_ROLES = tuple(role for role in THEME_COLOR_ROLES if role != "notification_glow")


def bounded_number(value: Any, minimum: float, maximum: float, fallback: float) -> float:
    """Return a finite number constrained to the requested inclusive range."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number or number in {float("inf"), float("-inf")}:
        return fallback
    return max(minimum, min(maximum, number))


def clean_gradient_stop(value: Any) -> dict[str, Any] | None:
    """Return one safe color stop or None for malformed input."""

    if not isinstance(value, dict):
        return None
    color = str(value.get("color") or "").strip().lower()
    if not THEME_HEX_COLOR.fullmatch(color):
        return None
    return {
        "color": color,
        "position": bounded_number(value.get("position"), 0, 100, 0),
    }


def clean_theme_gradient(value: Any) -> dict[str, Any] | None:
    """Return one bounded linear or radial gradient, or None when unusable."""

    if not isinstance(value, dict) or value.get("type") not in GRADIENT_TYPES:
        return None
    stops = []
    raw_stops = value.get("stops") if isinstance(value.get("stops"), list) else []
    for raw_stop in raw_stops:
        stop = clean_gradient_stop(raw_stop)
        if stop:
            stops.append(stop)
        if len(stops) == MAX_GRADIENT_STOPS:
            break
    if len(stops) < 2:
        return None
    stops.sort(key=lambda item: item["position"])
    return {
        "type": value["type"],
        "angle": bounded_number(value.get("angle"), 0, 359, 135),
        "center_x": bounded_number(value.get("center_x"), 0, 100, 50),
        "center_y": bounded_number(value.get("center_y"), 0, 100, 50),
        "stops": stops,
    }


def default_theme_gradients() -> dict[str, Any]:
    """Return empty role maps and a fresh favorites list."""

    return {**{mode: {} for mode in THEME_APPEARANCE_MODES}, "favorites": []}


def clean_theme_gradients(value: Any) -> dict[str, Any]:
    """Return safe per-mode gradients plus a de-duplicated favorites list."""

    source = value if isinstance(value, dict) else {}
    result = default_theme_gradients()
    for mode in THEME_APPEARANCE_MODES:
        role_source = source.get(mode) if isinstance(source.get(mode), dict) else {}
        for role in THEME_GRADIENT_ROLES:
            gradient = clean_theme_gradient(role_source.get(role))
            if gradient:
                result[mode][role] = gradient
    seen = set()
    favorites = source.get("favorites") if isinstance(source.get("favorites"), list) else []
    for raw_gradient in favorites:
        gradient = clean_theme_gradient(raw_gradient)
        signature = repr(gradient)
        if gradient and signature not in seen:
            result["favorites"].append(gradient)
            seen.add(signature)
        if len(result["favorites"]) == MAX_GRADIENT_FAVORITES:
            break
    return result
