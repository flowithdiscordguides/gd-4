/* Accessible visual gradient editor shared by every semantic Theme role. */

(() => {
const renderHelpers = window.GitDeskRender;
const settingsModel = window.GitDeskThemeSettingsModel;
const gradientModel = window.GitDeskThemeGradientModel;
const colorWheel = window.GitDeskColorWheel;
if (!renderHelpers || !settingsModel || !gradientModel || !colorWheel) {
  throw new Error("GitDesk gradient editor dependencies did not load.");
}

const { byId } = renderHelpers;
let saved = gradientModel.emptySettings();
let draft = gradientModel.emptySettings();
let activeRole = "";
let working = null;
let selectedStop = 0;
let returnFocus = null;
let options = null;

function roleAttribute(role) {
  return `data-theme-gradient-${role.replaceAll("_", "-")}`;
}

function triggerMarkup(field) {
  return `
    <button class="theme-gradient-trigger" type="button" data-theme-gradient-role="${field.role}"
      aria-label="Create or edit ${field.label} gradient" aria-haspopup="dialog"
      aria-controls="theme-gradient-modal" aria-expanded="false">
      <span class="theme-gradient-icon" aria-hidden="true"></span>
    </button>
  `;
}

function markup() {
  return `
    <div id="theme-gradient-modal" class="theme-gradient-modal" hidden>
      <section class="theme-gradient-dialog" role="dialog" aria-modal="true"
        aria-labelledby="theme-gradient-title" aria-describedby="theme-gradient-description">
        <header class="theme-gradient-header">
          <div><span>Visual gradient studio</span><h2 id="theme-gradient-title">Edit gradient</h2>
            <p id="theme-gradient-description">Build a reusable paint without writing CSS.</p></div>
          <button id="close-theme-gradient" type="button" aria-label="Close gradient editor">Close</button>
        </header>
        <div class="theme-gradient-workspace">
          <section class="theme-gradient-canvas-panel" aria-label="Gradient preview and stops">
            <div id="theme-gradient-preview" class="theme-gradient-preview">
              <div id="theme-gradient-stop-track" class="theme-gradient-stop-track"></div>
            </div>
            <div class="theme-gradient-type" role="group" aria-label="Gradient type">
              <button type="button" data-gradient-type="linear">Linear</button>
              <button type="button" data-gradient-type="radial">Radial</button>
            </div>
            <div id="theme-gradient-linear-controls" class="theme-gradient-geometry">
              <label for="theme-gradient-angle">Angle <output id="theme-gradient-angle-value"></output></label>
              <input id="theme-gradient-angle" type="range" min="0" max="359" step="1">
            </div>
            <div id="theme-gradient-radial-controls" class="theme-gradient-geometry" hidden>
              <label for="theme-gradient-center-x">Horizontal center
                <output id="theme-gradient-center-x-value"></output></label>
              <input id="theme-gradient-center-x" type="range" min="0" max="100" step="1">
              <label for="theme-gradient-center-y">Vertical center
                <output id="theme-gradient-center-y-value"></output></label>
              <input id="theme-gradient-center-y" type="range" min="0" max="100" step="1">
            </div>
          </section>
          <aside class="theme-gradient-inspector" aria-label="Selected color stop">
            <div class="theme-gradient-stop-heading"><div><span>Selected stop</span>
              <strong id="theme-gradient-stop-name"></strong></div>
              <button id="theme-gradient-stop-color" class="theme-gradient-stop-color" type="button"
                aria-label="Choose selected stop color" aria-haspopup="dialog"
                aria-controls="theme-color-wheel-popover"><span aria-hidden="true"></span></button></div>
            <label for="theme-gradient-stop-position">Position
              <output id="theme-gradient-stop-position-value"></output></label>
            <input id="theme-gradient-stop-position" type="range" min="0" max="100" step="1">
            <div class="theme-gradient-stop-actions">
              <button id="add-theme-gradient-stop" type="button">Add stop</button>
              <button id="remove-theme-gradient-stop" type="button">Remove stop</button>
            </div>
            <section class="theme-gradient-favorites" aria-labelledby="theme-gradient-favorites-title">
              <header><div><span>Reusable library</span>
                <strong id="theme-gradient-favorites-title">Favorites</strong></div>
                <button id="favorite-theme-gradient" type="button">Save favorite</button></header>
              <div id="theme-gradient-favorite-list" class="theme-gradient-favorite-list"></div>
            </section>
          </aside>
        </div>
        <footer class="theme-gradient-footer">
          <button id="remove-theme-gradient" type="button">Use solid color</button>
          <div><button id="cancel-theme-gradient" type="button">Cancel</button>
            <button id="use-theme-gradient" class="primary" type="button">Use gradient</button></div>
        </footer>
      </section>
    </div>
  `;
}

function currentMode() {
  return options.currentMode();
}

function notifyChanged(message) {
  options.onChange(message);
  applyCurrentTheme(currentMode());
  renderTriggers(currentMode());
}

function favoriteMarkup(gradient, index) {
  return `<article class="theme-gradient-favorite">
    <button type="button" data-use-gradient-favorite="${index}" aria-label="Use favorite ${index + 1}">
      <span style="--favorite-gradient:${gradientModel.gradientCss(gradient)}"></span>
    </button>
    <button type="button" data-remove-gradient-favorite="${index}"
      aria-label="Remove favorite ${index + 1}">Remove</button>
  </article>`;
}

function renderModal() {
  if (!working || !activeRole) return;
  const field = settingsModel.COLOR_FIELDS.find((candidate) => candidate.role === activeRole);
  const stop = working.stops[selectedStop];
  byId("theme-gradient-title").textContent = `${field.label} gradient`;
  byId("theme-gradient-preview").style.backgroundImage = gradientModel.gradientCss(working);
  byId("theme-gradient-stop-track").innerHTML = working.stops.map((item, index) => `
    <button type="button" data-gradient-stop="${index}" class="${index === selectedStop ? "selected" : ""}"
      style="--stop-position:${item.position}%;--stop-color:${item.color}"
      aria-label="Select stop ${index + 1} at ${item.position}%"></button>`).join("");
  document.querySelectorAll("[data-gradient-type]").forEach((button) => {
    const active = button.dataset.gradientType === working.type;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
  });
  byId("theme-gradient-linear-controls").hidden = working.type !== "linear";
  byId("theme-gradient-radial-controls").hidden = working.type !== "radial";
  [["angle", "°"], ["center-x", "%"], ["center-y", "%"]].forEach(([key, suffix]) => {
    const property = key.replace("-", "_");
    byId(`theme-gradient-${key}`).value = working[property];
    byId(`theme-gradient-${key}-value`).textContent = `${working[property]}${suffix}`;
  });
  byId("theme-gradient-stop-name").textContent = `Stop ${selectedStop + 1} of ${working.stops.length}`;
  byId("theme-gradient-stop-color").style.setProperty("--stop-color", stop.color);
  byId("theme-gradient-stop-position").value = stop.position;
  byId("theme-gradient-stop-position-value").textContent = `${stop.position}%`;
  byId("add-theme-gradient-stop").disabled = working.stops.length >= gradientModel.MAX_STOPS;
  byId("remove-theme-gradient-stop").disabled = working.stops.length <= 2;
  byId("theme-gradient-favorite-list").innerHTML = draft.favorites.length
    ? draft.favorites.map(favoriteMarkup).join("")
    : '<p class="theme-gradient-favorite-empty">Saved gradients will appear here.</p>';
}

function openEditor(trigger) {
  activeRole = trigger.dataset.themeGradientRole;
  const mode = currentMode();
  working = gradientModel.cloneGradient(draft[mode][activeRole])
    || gradientModel.starterGradient(options.color(mode, activeRole));
  selectedStop = 0;
  returnFocus = trigger;
  trigger.setAttribute("aria-expanded", "true");
  byId("theme-gradient-modal").hidden = false;
  document.body.classList.add("theme-gradient-open");
  renderModal();
  byId("close-theme-gradient").focus();
}

function closeEditor(restoreFocus = true) {
  colorWheel.close(false);
  const modal = byId("theme-gradient-modal");
  if (!modal || modal.hidden) return;
  modal.hidden = true;
  document.body.classList.remove("theme-gradient-open");
  if (returnFocus) returnFocus.setAttribute("aria-expanded", "false");
  if (restoreFocus && returnFocus) returnFocus.focus();
  working = null;
  activeRole = "";
}

function addStop() {
  if (working.stops.length >= gradientModel.MAX_STOPS) return;
  const selected = working.stops[selectedStop];
  const neighbor = working.stops[selectedStop + 1] || working.stops[selectedStop - 1];
  const position = neighbor ? Math.round((selected.position + neighbor.position) / 2) : 50;
  working.stops.push({ color: selected.color, position });
  working.stops.sort((first, second) => first.position - second.position);
  selectedStop = working.stops.findIndex((stop) => stop.position === position && stop.color === selected.color);
  renderModal();
}

function saveFavorite() {
  const signature = JSON.stringify(gradientModel.cleanGradient(working));
  if (!draft.favorites.some((favorite) => JSON.stringify(favorite) === signature)) {
    draft.favorites.unshift(gradientModel.cloneGradient(working));
    draft.favorites = draft.favorites.slice(0, gradientModel.MAX_FAVORITES);
    notifyChanged("Gradient saved to favorites. Apply colors to keep it.");
  }
  renderModal();
}

function handleClick(event) {
  const trigger = event.target.closest("[data-theme-gradient-role]");
  if (trigger) return openEditor(trigger);
  if (event.target === byId("theme-gradient-modal") || event.target.closest("#close-theme-gradient")
      || event.target.closest("#cancel-theme-gradient")) return closeEditor();
  const typeButton = event.target.closest("[data-gradient-type]");
  if (typeButton) working.type = typeButton.dataset.gradientType;
  const stopButton = event.target.closest("[data-gradient-stop]");
  if (stopButton) selectedStop = Number(stopButton.dataset.gradientStop);
  if (event.target.closest("#add-theme-gradient-stop")) addStop();
  if (event.target.closest("#remove-theme-gradient-stop") && working.stops.length > 2) {
    working.stops.splice(selectedStop, 1);
    selectedStop = Math.min(selectedStop, working.stops.length - 1);
  }
  if (event.target.closest("#theme-gradient-stop-color")) {
    colorWheel.open(byId("theme-gradient-stop-color"), working.stops[selectedStop].color, "Gradient stop", (color) => {
      working.stops[selectedStop].color = settingsModel.cleanHexColor(color, working.stops[selectedStop].color);
      renderModal();
    });
  }
  if (event.target.closest("#favorite-theme-gradient")) saveFavorite();
  const useFavorite = event.target.closest("[data-use-gradient-favorite]");
  if (useFavorite) {
    working = gradientModel.cloneGradient(draft.favorites[Number(useFavorite.dataset.useGradientFavorite)]);
    selectedStop = 0;
  }
  const removeFavorite = event.target.closest("[data-remove-gradient-favorite]");
  if (removeFavorite) {
    draft.favorites.splice(Number(removeFavorite.dataset.removeGradientFavorite), 1);
    notifyChanged("Favorite removed. Apply colors to keep the change.");
  }
  if (event.target.closest("#use-theme-gradient")) {
    draft[currentMode()][activeRole] = gradientModel.cloneGradient(working);
    notifyChanged("Previewing an unsaved gradient.");
    return closeEditor();
  }
  if (event.target.closest("#remove-theme-gradient")) {
    delete draft[currentMode()][activeRole];
    notifyChanged("Previewing the solid color for this role.");
    return closeEditor();
  }
  if (working) renderModal();
}

function handleInput(event) {
  const map = {
    "theme-gradient-angle": "angle",
    "theme-gradient-center-x": "center_x",
    "theme-gradient-center-y": "center_y",
  };
  if (map[event.target.id]) working[map[event.target.id]] = Number(event.target.value);
  if (event.target.id === "theme-gradient-stop-position") {
    const selected = working.stops[selectedStop];
    selected.position = Number(event.target.value);
    working.stops.sort((first, second) => first.position - second.position);
    selectedStop = working.stops.indexOf(selected);
  }
  renderModal();
}

function handleKeydown(event) {
  const modal = byId("theme-gradient-modal");
  if (!modal || modal.hidden) return;
  if (event.key === "Escape") return closeEditor();
  if (event.key !== "Tab") return;
  const focusable = [...modal.querySelectorAll("button:not(:disabled), input:not(:disabled)")];
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function applyCurrentTheme(mode) {
  settingsModel.COLOR_FIELDS.forEach((field) => {
    const attribute = roleAttribute(field.role);
    const gradient = draft[mode][field.role];
    document.documentElement.toggleAttribute(attribute, Boolean(gradient));
    if (gradient) {
      document.documentElement.style.setProperty(`--theme-gradient-${field.role}`, gradientModel.gradientCss(gradient));
    } else {
      document.documentElement.style.removeProperty(`--theme-gradient-${field.role}`);
    }
  });
}

function renderTriggers(mode) {
  settingsModel.COLOR_FIELDS.forEach((field) => {
    const trigger = document.querySelector(`[data-theme-gradient-role="${field.role}"]`);
    if (!trigger) return;
    const gradient = draft[mode][field.role];
    trigger.classList.toggle("active", Boolean(gradient));
    trigger.style.setProperty("--trigger-gradient", gradientModel.gradientCss(gradient));
    trigger.setAttribute("aria-label", `${gradient ? "Edit" : "Create"} ${field.label} gradient`);
  });
}

function applySettings(settings) {
  closeEditor(false);
  saved = gradientModel.cleanSettings(settings && settings.theme_gradients);
  draft = gradientModel.cloneSettings(saved);
}

function loadProfile(value) {
  closeEditor(false);
  const favorites = draft.favorites.map(gradientModel.cloneGradient);
  draft = gradientModel.cloneSettings(value);
  draft.favorites = favorites;
}

function bind(bindOptions) {
  options = bindOptions;
  const card = byId("theme-settings-card");
  card.addEventListener("click", handleClick);
  byId("theme-gradient-modal").addEventListener("input", handleInput);
  document.addEventListener("keydown", handleKeydown);
}

function resetMode(mode) { draft[mode] = {}; }
function rollback() { draft = gradientModel.cloneSettings(saved); closeEditor(false); }
function isSaved() { return JSON.stringify(draft) === JSON.stringify(saved); }
function value() { return gradientModel.cloneSettings(draft); }
function profileValue() {
  const profile = gradientModel.cloneSettings(draft);
  return { dark: profile.dark, light: profile.light };
}

window.GitDeskThemeGradientEditor = {
  applyCurrentTheme,
  applySettings,
  bind,
  isSaved,
  loadProfile,
  markup,
  profileValue,
  renderTriggers,
  resetMode,
  rollback,
  triggerMarkup,
  value,
};
})();
