/*
  Local parent-folder favorites for the New Project create workflow.
*/

// Manages parent folder quick access without adding weight to the main Local Mode controller.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;

if (!nativeBridge || !renderHelpers) {
  throw new Error("GitDesk parent favorite dependencies did not load.");
}

const { appendActivity, byId, setBusy, setValue, showMessage } = renderHelpers;
const { callNative } = nativeBridge;
let savedFavorites = [];

// Escapes saved paths before rendering them into favorite option labels.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Adds the favorite selector and save button below the parent folder input row.
function injectControls() {
  if (document.getElementById("local-parent-favorite-select")) {
    return;
  }
  const input = document.getElementById("local-parent-path");
  if (!input) {
    return;
  }
  const row = input.closest(".input-action-row");
  if (!row) {
    return;
  }
  row.classList.add("local-parent-path-row");
  row.insertAdjacentHTML("beforeend", `
    <button id="save-local-parent-favorite" class="icon-button" type="button"
      aria-label="Save parent folder as favorite" title="Save parent folder as favorite">
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1L12 16.9l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"></path>
      </svg>
    </button>
  `);
  row.insertAdjacentHTML("afterend", `
    <div class="local-parent-favorites-row">
      <select id="local-parent-favorite-select" aria-label="Favorite parent folders">
        <option value="">Favorite parent folders</option>
      </select>
    </div>
  `);
}

// Keeps the star visually synced with whether the typed parent folder is already saved.
function renderFavoriteState() {
  const button = document.getElementById("save-local-parent-favorite");
  const input = document.getElementById("local-parent-path");
  if (!button || !input) {
    return;
  }
  const saved = savedFavorites.indexOf(input.value.trim()) >= 0;
  button.classList.toggle("saved", saved);
  button.title = saved ? "Parent folder saved as favorite" : "Save parent folder as favorite";
}

// Renders saved favorites, preserving the empty first option as a non-actionable label.
function renderFavorites(settings) {
  const select = document.getElementById("local-parent-favorite-select");
  if (!select) {
    return;
  }
  savedFavorites = settings && Array.isArray(settings.local_parent_favorites)
    ? settings.local_parent_favorites
    : [];
  const options = ['<option value="">Favorite parent folders</option>'];
  savedFavorites.forEach((path) => {
    options.push(`<option value="${escapeHtml(path)}">${escapeHtml(path)}</option>`);
  });
  select.innerHTML = options.join("");
  select.disabled = !savedFavorites.length;
  renderFavoriteState();
}

// Loads current settings so favorites appear when the New Project modal opens for the first time.
async function refreshFavorites() {
  const data = await callNative("localProjectsState", {});
  renderFavorites(data.settings || {});
}

// Saves the current parent path after Python validates that the folder exists.
async function saveFavorite() {
  const path = byId("local-parent-path").value;
  if (!path.trim()) {
    showMessage("Choose a parent folder before saving it as a favorite.", true);
    return;
  }
  setBusy(true);
  try {
    const data = await callNative("saveLocalParentFavorite", { path });
    renderFavorites(data.settings || {});
    appendActivity("Local parent favorite saved");
  } catch (error) {
    const message = error.message || "Parent favorite could not be saved.";
    showMessage(message, true);
    appendActivity(message, true);
  } finally {
    setBusy(false);
  }
}

// Writes a selected favorite into the parent path input without creating a project yet.
function useFavorite(event) {
  if (event.target.value) {
    setValue("local-parent-path", event.target.value);
    renderFavoriteState();
  }
}

// Binds the injected controls after the New Project modal has been created.
function init() {
  injectControls();
  if (!document.getElementById("local-parent-favorite-select")) {
    return;
  }
  byId("local-parent-favorite-select").addEventListener("change", useFavorite);
  byId("save-local-parent-favorite").addEventListener("click", saveFavorite);
  byId("local-parent-path").addEventListener("input", renderFavoriteState);
  refreshFavorites().catch(() => {});
}

// Runs after Project Hub has injected the shared New Project modal.
function onReady(callback) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", callback);
    return;
  }
  callback();
}

window.GitDeskLocalParentFavorites = { refresh: refreshFavorites, sync: renderFavoriteState };
onReady(init);
})();
