/*
  Theme tab controller for dark and light semantic color customization.
*/

// Keeps draft preview state separate from canonical backend settings until the user applies it.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const themeManager = window.GitDeskTheme;
const colorWheel = window.GitDeskColorWheel;
const settingsModel = window.GitDeskThemeSettingsModel;
const gradientEditor = window.GitDeskThemeGradientEditor;
const profileManager = window.GitDeskThemeProfileManager;

if (!nativeBridge || !renderHelpers || !themeManager || !colorWheel || !settingsModel || !gradientEditor
    || !profileManager) {
  throw new Error("GitDesk theme settings dependencies did not load.");
}

const { callNative } = nativeBridge;
const { appendActivity, byId, setBusy, showMessage } = renderHelpers;
const { COLOR_FIELDS, COLOR_GROUPS, DEFAULT_THEME_COLORS } = settingsModel;
const { cleanHexColor, cleanThemeColors, copyThemeColors, readableInk } = settingsModel;

let busy = false;
let feedback = "";
let feedbackIsError = false;
let saved = copyThemeColors(DEFAULT_THEME_COLORS);
let draft = copyThemeColors(DEFAULT_THEME_COLORS);

// Applies the active appearance's draft roles through semantic CSS variables.
function applyCurrentThemeColors() {
  const mode = themeManager.currentTheme();
  const colors = draft[mode];
  const rootStyle = document.documentElement.style;
  rootStyle.setProperty("--text", colors.body_text);
  rootStyle.setProperty("--muted", colors.secondary_text);
  rootStyle.setProperty("--theme-heading-color", colors.headings);
  rootStyle.setProperty("--gitdesk-label", colors.labels);
  rootStyle.setProperty("--theme-app-background", colors.app_background);
  rootStyle.setProperty("--theme-navigation-background", colors.navigation_background);
  rootStyle.setProperty("--theme-panel-background", colors.panel_background);
  rootStyle.setProperty("--theme-section-background", colors.section_background);
  rootStyle.setProperty("--theme-secondary-background", colors.secondary_background);
  rootStyle.setProperty("--theme-control-background", colors.control_background);
  rootStyle.setProperty("--theme-modal-background", colors.modal_background);
  rootStyle.setProperty("--theme-border-color", colors.border_color);
  rootStyle.setProperty("--theme-notification-glow", colors.notification_glow);
  rootStyle.setProperty("--accent-solid", colors.accent);
  rootStyle.setProperty("--theme-primary-action", colors.primary_actions);
  rootStyle.setProperty("--theme-primary-action-ink", readableInk(colors.primary_actions));
  rootStyle.setProperty("--theme-selected-control", colors.selected_controls);
  rootStyle.setProperty("--theme-selected-control-ink", readableInk(colors.selected_controls));
  gradientEditor.applyCurrentTheme(mode);
}

// Builds one semantic row whose swatch opens GitDesk's continuous color wheel.
function colorFieldMarkup(field) {
  const swatchId = `theme-color-${field.role}`;
  return `
    <div class="theme-color-row">
      <div class="theme-color-copy">
        <label for="${swatchId}">${field.label}</label>
        <p>${field.detail}</p>
      </div>
      <div class="theme-color-control">
        ${field.supportsGradient === false ? "" : gradientEditor.triggerMarkup(field)}
        <button id="${swatchId}" class="theme-color-swatch" type="button"
          data-theme-color-role="${field.role}" aria-label="Choose ${field.label} color"
          aria-haspopup="dialog" aria-controls="theme-color-wheel-popover" aria-expanded="false">
          <span aria-hidden="true"></span>
        </button>
        <output id="${swatchId}-value" for="${swatchId}"></output>
      </div>
    </div>
  `;
}

// Builds semantic groups from one field registry so surface roles stay generalized.
function colorGroupsMarkup() {
  return COLOR_GROUPS.map((group) => `
    <section class="theme-color-group theme-color-group-${group.toLowerCase()}"
      aria-labelledby="theme-${group.toLowerCase()}-title">
      <h3 id="theme-${group.toLowerCase()}-title">${group}</h3>
      <div class="theme-color-group-fields">
        ${COLOR_FIELDS.filter((field) => field.group === group).map(colorFieldMarkup).join("")}
      </div>
    </section>
  `).join("");
}

// Creates the Color Studio only inside the dedicated Theme mount.
function injectThemeEditor() {
  if (document.getElementById("theme-settings-card")) return;
  const mount = document.getElementById("settings-theme-content");
  if (!mount) return;
  mount.innerHTML = `
    <section id="theme-settings-card" class="settings-block theme-settings-card"
      aria-labelledby="theme-settings-title">
      <header class="theme-settings-header">
        <div>
          <strong id="theme-settings-title">Color Studio</strong>
          <p>Choose any colors for GitDesk typography, shared surfaces, and controls.</p>
        </div>
        <span id="theme-current-badge" class="theme-current-badge"></span>
      </header>
      <div class="theme-live-preview" aria-labelledby="theme-preview-title">
        <span>Live palette</span>
        <strong id="theme-preview-title">A focused workspace</strong>
        <p>Every wheel adjustment previews immediately across the visible app.</p>
        <div><span class="theme-preview-primary">Primary action</span>
          <span class="theme-preview-selected">Selected control</span></div>
      </div>
      ${profileManager.markup()}
      <fieldset class="theme-appearance-field">
        <legend>Edit appearance</legend>
        <div class="theme-appearance-switch" role="group" aria-label="Appearance colors to edit">
          <button type="button" data-theme-appearance="dark">Dark</button>
          <button type="button" data-theme-appearance="light">Light</button>
        </div>
      </fieldset>
      <div class="theme-color-groups">${colorGroupsMarkup()}</div>
      <footer class="theme-settings-footer">
        <p id="theme-settings-status" role="status" aria-live="polite"></p>
        <div class="theme-settings-actions">
          <button id="reset-theme-settings" type="button">Reset current theme</button>
          <button id="apply-theme-settings" class="primary" type="button">Apply colors</button>
        </div>
      </footer>
      ${colorWheel.markup()}
      ${gradientEditor.markup()}
    </section>
  `;
}

// Returns true when every draft role exactly matches the sanitized saved settings.
function draftIsSaved() {
  return JSON.stringify(draft) === JSON.stringify(saved) && gradientEditor.isSaved();
}

// Renders swatches, appearance state, save feedback, and action availability from the current draft.
function renderThemeEditor() {
  if (!document.getElementById("theme-settings-card")) return;
  const mode = themeManager.currentTheme();
  document.querySelectorAll("[data-theme-appearance]").forEach((button) => {
    const active = button.dataset.themeAppearance === mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  COLOR_FIELDS.forEach((field) => {
    const color = draft[mode][field.role];
    byId(`theme-color-${field.role}`).style.setProperty("--theme-swatch-color", color);
    byId(`theme-color-${field.role}-value`).textContent = color.toUpperCase();
  });
  gradientEditor.renderTriggers(mode);
  byId("theme-current-badge").textContent = `${mode} theme`;
  byId("apply-theme-settings").disabled = busy || draftIsSaved();
  byId("reset-theme-settings").disabled = busy;
  const status = byId("theme-settings-status");
  status.classList.toggle("danger", feedbackIsError);
  status.textContent = feedback;
}

// Replaces saved and draft state from one canonical backend settings response.
function applySettings(settings) {
  colorWheel.close(false);
  saved = cleanThemeColors(settings && settings.theme_colors);
  draft = copyThemeColors(saved);
  gradientEditor.applySettings(settings || {});
  profileManager.applySettings(settings || {});
  applyCurrentThemeColors();
  renderThemeEditor();
}

// Applies one continuous wheel adjustment directly to the selected semantic role's draft.
function previewWheelColor(role, mode, color) {
  draft[mode][role] = cleanHexColor(color, draft[mode][role]);
  feedback = "Previewing unsaved colors.";
  feedbackIsError = false;
  applyCurrentThemeColors();
  renderThemeEditor();
}

// Routes swatches, appearance choices, and reset without involving the native save bridge.
function handleThemeEditorClick(event) {
  const swatch = event.target.closest("[data-theme-color-role]");
  if (swatch) {
    const mode = themeManager.currentTheme();
    const role = swatch.dataset.themeColorRole;
    const field = COLOR_FIELDS.find((candidate) => candidate.role === role);
    colorWheel.open(swatch, draft[mode][role], field.label, (color) => {
      previewWheelColor(role, mode, color);
    });
    return;
  }
  const appearanceButton = event.target.closest("[data-theme-appearance]");
  if (appearanceButton) {
    colorWheel.close(false);
    themeManager.selectTheme(appearanceButton.dataset.themeAppearance);
    return;
  }
  if (event.target.closest("#reset-theme-settings")) {
    colorWheel.close(false);
    const mode = themeManager.currentTheme();
    draft[mode] = Object.assign({}, DEFAULT_THEME_COLORS[mode]);
    gradientEditor.resetMode(mode);
    feedback = `${mode[0].toUpperCase()}${mode.slice(1)} defaults are ready to apply.`;
    feedbackIsError = false;
    applyCurrentThemeColors();
    renderThemeEditor();
  }
}

// Persists every valid draft color and rolls the preview back only if the native save itself fails.
async function saveThemeSettings() {
  if (busy || draftIsSaved()) return;
  colorWheel.close(false);
  busy = true;
  feedback = "Applying colors…";
  feedbackIsError = false;
  renderThemeEditor();
  setBusy(true);
  try {
    const data = await callNative("saveSettings", {
      theme_colors: draft,
      theme_gradients: gradientEditor.value(),
    });
    applySettings(data.settings || {});
    feedback = "Theme colors applied.";
    appendActivity("Theme color settings applied");
  } catch (error) {
    const message = error.message || "Theme colors could not be saved.";
    draft = copyThemeColors(saved);
    gradientEditor.rollback();
    applyCurrentThemeColors();
    feedback = message;
    feedbackIsError = true;
    showMessage(message, true);
    appendActivity(message, true);
  } finally {
    busy = false;
    setBusy(false);
    renderThemeEditor();
  }
}

// Reapplies the draft for the appearance selected in Theme settings or the topbar.
function handleThemeChanged() {
  colorWheel.close(false);
  applyCurrentThemeColors();
  renderThemeEditor();
}

function loadThemeProfile(profile) {
  colorWheel.close(false);
  draft = cleanThemeColors(profile && profile.theme_colors);
  gradientEditor.loadProfile(profile && profile.theme_gradients);
  feedback = "Previewing an unsaved theme profile.";
  feedbackIsError = false;
  applyCurrentThemeColors();
  renderThemeEditor();
}

// Injects and binds the editor once the dynamic Theme panel exists.
function bindThemeSettings() {
  injectThemeEditor();
  const card = document.getElementById("theme-settings-card");
  if (!card) return;
  colorWheel.bind();
  gradientEditor.bind({
    currentMode: () => themeManager.currentTheme(),
    color: (mode, role) => draft[mode][role],
    onChange: (message) => {
      feedback = message;
      feedbackIsError = false;
      renderThemeEditor();
    },
  });
  profileManager.bind({
    load: loadThemeProfile,
    snapshot: () => ({
      theme_colors: copyThemeColors(draft),
      theme_gradients: gradientEditor.profileValue(),
    }),
  });
  card.addEventListener("click", handleThemeEditorClick);
  byId("apply-theme-settings").addEventListener("click", saveThemeSettings);
  window.addEventListener("gitdesk:theme-changed", handleThemeChanged);
  applyCurrentThemeColors();
  renderThemeEditor();
}

window.GitDeskThemeSettings = { applySettings };

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bindThemeSettings);
} else {
  bindThemeSettings();
}
})();
