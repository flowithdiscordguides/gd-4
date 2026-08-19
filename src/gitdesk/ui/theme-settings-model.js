/* Shared metadata and sanitation for Theme settings frontend modules. */

(() => {
const APPEARANCE_MODES = ["dark", "light"];
const COLOR_GROUPS = ["Typography", "Surfaces", "Controls"];
const COLOR_FIELDS = [
  { group: "Typography", role: "body_text", label: "Body text", detail: "Main content and control text." },
  { group: "Typography", role: "secondary_text", label: "Secondary text", detail: "Hints and supporting copy." },
  { group: "Typography", role: "headings", label: "Headings", detail: "Page and section titles." },
  { group: "Typography", role: "labels", label: "Labels", detail: "Form labels and field legends." },
  { group: "Surfaces", role: "app_background", label: "App background", detail: "Window canvas and workspace." },
  { group: "Surfaces", role: "navigation_background", label: "Navigation", detail: "Top bars and sidebars." },
  { group: "Surfaces", role: "panel_background", label: "Main panels", detail: "Primary panes and layouts." },
  { group: "Surfaces", role: "section_background", label: "Sections & cards", detail: "Grouped content areas." },
  { group: "Surfaces", role: "secondary_background", label: "Secondary surfaces", detail: "Inset and quiet areas." },
  { group: "Surfaces", role: "control_background", label: "Inputs & controls", detail: "Fields and normal buttons." },
  { group: "Surfaces", role: "modal_background", label: "Modals & menus", detail: "Dialogs and floating menus." },
  { group: "Surfaces", role: "border_color", label: "Borders & dividers", detail: "Shared structural lines." },
  { group: "Controls", role: "notification_glow", label: "Notification glow",
    detail: "Halo around controls with green notification dots.", supportsGradient: false },
  { group: "Controls", role: "accent", label: "Accent & focus", detail: "Focus rings and highlighted details." },
  { group: "Controls", role: "primary_actions", label: "Primary actions", detail: "Commit, save, and create." },
  { group: "Controls", role: "selected_controls", label: "Selected controls", detail: "Active tabs and modes." },
];
const DEFAULT_THEME_COLORS = {
  dark: {
    body_text: "#f4f1ea", secondary_text: "#a0aaa4", headings: "#f4f1ea", labels: "#a0aaa4",
    app_background: "#080a0d", navigation_background: "#101316", panel_background: "#121619",
    section_background: "#0b0d10", secondary_background: "#181a1d", control_background: "#1a1c1f",
    modal_background: "#11161b", border_color: "#272a2b", notification_glow: "#ffffff", accent: "#b9c0c7",
    primary_actions: "#b9c0c7", selected_controls: "#b9c0c7",
  },
  light: {
    body_text: "#17201d", secondary_text: "#64706b", headings: "#17201d", labels: "#64706b",
    app_background: "#eef1ee", navigation_background: "#f7f9f7", panel_background: "#fafbfa",
    section_background: "#fafbfa", secondary_background: "#e3e7e4", control_background: "#f9faf9",
    modal_background: "#ffffff", border_color: "#d3d7d4", notification_glow: "#ffffff", accent: "#5f6972",
    primary_actions: "#6f7881", selected_controls: "#6f7881",
  },
};

function cleanHexColor(value, fallback) {
  const color = String(value || "").trim().toLowerCase();
  return /^#[0-9a-f]{6}$/.test(color) ? color : fallback;
}

function cleanThemeColors(value) {
  const source = value && typeof value === "object" ? value : {};
  const result = {};
  APPEARANCE_MODES.forEach((mode) => {
    const modeSource = source[mode] && typeof source[mode] === "object" ? source[mode] : {};
    result[mode] = {};
    COLOR_FIELDS.forEach((field) => {
      result[mode][field.role] = cleanHexColor(modeSource[field.role], DEFAULT_THEME_COLORS[mode][field.role]);
    });
  });
  return result;
}

function copyThemeColors(value) {
  return APPEARANCE_MODES.reduce((result, mode) => {
    result[mode] = COLOR_FIELDS.reduce((colors, field) => {
      colors[field.role] = value[mode][field.role];
      return colors;
    }, {});
    return result;
  }, {});
}

function readableInk(background) {
  const channels = [1, 3, 5].map((start) => Number.parseInt(background.slice(start, start + 2), 16));
  const linear = channels.map((channel) => {
    const value = channel / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  const luminance = (linear[0] * 0.2126) + (linear[1] * 0.7152) + (linear[2] * 0.0722);
  return luminance > 0.42 ? "#111418" : "#ffffff";
}

window.GitDeskThemeSettingsModel = {
  APPEARANCE_MODES,
  COLOR_FIELDS,
  COLOR_GROUPS,
  DEFAULT_THEME_COLORS,
  cleanHexColor,
  cleanThemeColors,
  copyThemeColors,
  readableInk,
};
})();
