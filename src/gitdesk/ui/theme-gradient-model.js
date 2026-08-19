/* Structured theme-gradient sanitation and CSS serialization. */

(() => {
const settingsModel = window.GitDeskThemeSettingsModel;
if (!settingsModel) throw new Error("GitDesk theme settings model did not load.");

const MAX_STOPS = 8;
const MAX_FAVORITES = 24;

function numberInRange(value, minimum, maximum, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? Math.max(minimum, Math.min(maximum, number)) : fallback;
}

function cleanStop(value) {
  if (!value || typeof value !== "object") return null;
  const color = settingsModel.cleanHexColor(value.color, "");
  if (!color) return null;
  return { color, position: numberInRange(value.position, 0, 100, 0) };
}

function cleanGradient(value) {
  if (!value || !["linear", "radial"].includes(value.type)) return null;
  const stops = (Array.isArray(value.stops) ? value.stops : [])
    .map(cleanStop).filter(Boolean).slice(0, MAX_STOPS)
    .sort((first, second) => first.position - second.position);
  if (stops.length < 2) return null;
  return {
    type: value.type,
    angle: numberInRange(value.angle, 0, 359, 135),
    center_x: numberInRange(value.center_x, 0, 100, 50),
    center_y: numberInRange(value.center_y, 0, 100, 50),
    stops,
  };
}

function cloneGradient(value) {
  const gradient = cleanGradient(value);
  return gradient ? { ...gradient, stops: gradient.stops.map((stop) => ({ ...stop })) } : null;
}

function emptySettings() {
  return { dark: {}, light: {}, favorites: [] };
}

function cleanSettings(value) {
  const source = value && typeof value === "object" ? value : {};
  const result = emptySettings();
  settingsModel.APPEARANCE_MODES.forEach((mode) => {
    const roles = source[mode] && typeof source[mode] === "object" ? source[mode] : {};
    settingsModel.COLOR_FIELDS.filter((field) => field.supportsGradient !== false).forEach((field) => {
      const gradient = cleanGradient(roles[field.role]);
      if (gradient) result[mode][field.role] = gradient;
    });
  });
  const seen = new Set();
  (Array.isArray(source.favorites) ? source.favorites : []).forEach((favorite) => {
    const gradient = cleanGradient(favorite);
    const signature = JSON.stringify(gradient);
    if (gradient && !seen.has(signature) && result.favorites.length < MAX_FAVORITES) {
      result.favorites.push(gradient);
      seen.add(signature);
    }
  });
  return result;
}

function cloneSettings(value) {
  const cleaned = cleanSettings(value);
  const result = emptySettings();
  settingsModel.APPEARANCE_MODES.forEach((mode) => {
    Object.entries(cleaned[mode]).forEach(([role, gradient]) => {
      result[mode][role] = cloneGradient(gradient);
    });
  });
  result.favorites = cleaned.favorites.map(cloneGradient);
  return result;
}

function starterGradient(color) {
  return {
    type: "linear",
    angle: 135,
    center_x: 50,
    center_y: 50,
    stops: [{ color, position: 0 }, { color, position: 100 }],
  };
}

function gradientCss(value) {
  const gradient = cleanGradient(value);
  if (!gradient) return "none";
  const stops = gradient.stops.map((stop) => `${stop.color} ${stop.position}%`).join(", ");
  if (gradient.type === "radial") {
    return `radial-gradient(circle at ${gradient.center_x}% ${gradient.center_y}%, ${stops})`;
  }
  return `linear-gradient(${gradient.angle}deg, ${stops})`;
}

window.GitDeskThemeGradientModel = {
  MAX_FAVORITES,
  MAX_STOPS,
  cleanGradient,
  cleanSettings,
  cloneGradient,
  cloneSettings,
  emptySettings,
  gradientCss,
  starterGradient,
};
})();
