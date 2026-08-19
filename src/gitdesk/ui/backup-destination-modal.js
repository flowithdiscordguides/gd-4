/*
  Backup destination review, native folder browsing, and parent-folder favorites.
*/

// Keeps destination selection explicit so browsing never replaces backup history before Apply.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;

if (!nativeBridge || !renderHelpers) {
  throw new Error("GitDesk backup destination modal dependencies did not load.");
}

const { callNative } = nativeBridge;
const { appendActivity, byId, setBusy, showMessage } = renderHelpers;
const modalState = {
  backup: {},
  busy: false,
  onSaved: null,
  previousFocus: null,
};

// Inserts the body-level dialog so workspace scrolling cannot clip its controls.
function injectModal() {
  if (document.getElementById("backup-destination-modal")) return;
  document.body.insertAdjacentHTML("beforeend", `
    <section id="backup-destination-modal" class="new-project-modal" hidden>
      <div class="new-project-dialog backup-destination-dialog" role="dialog" aria-modal="true"
        aria-labelledby="backup-destination-modal-title">
        <div class="panel-header new-project-dialog-header">
          <div>
            <h2 id="backup-destination-modal-title">Backup destination</h2>
            <p>Choose the parent folder that will contain dated GitDesk backup versions.</p>
          </div>
          <div class="new-project-dialog-actions">
            <button id="apply-backup-destination" type="submit" form="backup-destination-form">Apply</button>
            <button id="close-backup-destination-modal" type="button">Close</button>
          </div>
        </div>
        <form id="backup-destination-form" class="backup-destination-form">
          <label for="backup-parent-path">Parent folder</label>
          <div class="input-action-row backup-parent-path-row">
            <input id="backup-parent-path" type="text" spellcheck="false"
              placeholder="/absolute/path/to/backups">
            <button id="browse-backup-parent" class="icon-button" type="button"
              aria-label="Choose backup parent folder" title="Choose backup parent folder">
              <svg aria-hidden="true" viewBox="0 0 24 24">
                <path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v1H3z"></path>
                <path d="M3 9h18l-2 9a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z"></path>
              </svg>
            </button>
            <button id="save-backup-parent-favorite" class="icon-button" type="button"
              aria-label="Save backup parent as favorite" title="Save backup parent as favorite"
              aria-pressed="false">
              <svg aria-hidden="true" viewBox="0 0 24 24">
                <path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1L12 16.9l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"></path>
              </svg>
            </button>
          </div>
          <label for="backup-parent-favorites">Favorite parents</label>
          <select id="backup-parent-favorites"></select>
          <div class="backup-destination-note">
            <strong>What GitDesk creates here</strong>
            <code>gitdesk backups {date&amp;time}/</code>
            <span>Selected Local, Repo, Media, and safe settings content is grouped inside each version.</span>
          </div>
        </form>
      </div>
    </section>
  `);
}

// Reports whether the typed path is already present in the saved favorite set.
function isSavedFavorite(path) {
  const favorites = Array.isArray(modalState.backup.parent_favorites)
    ? modalState.backup.parent_favorites
    : [];
  return favorites.some((favorite) => favorite.toLocaleLowerCase() === path.toLocaleLowerCase());
}

// Synchronizes the star state with the current parent-path input.
function renderFavoriteState() {
  const button = byId("save-backup-parent-favorite");
  const saved = isSavedFavorite(byId("backup-parent-path").value.trim());
  button.classList.toggle("saved", saved);
  button.setAttribute("aria-pressed", String(saved));
  button.title = saved ? "Backup parent saved as favorite" : "Save backup parent as favorite";
}

// Rebuilds the safe text-only favorite selector from persisted Backup Mode state.
function renderFavorites() {
  const select = byId("backup-parent-favorites");
  const favorites = Array.isArray(modalState.backup.parent_favorites)
    ? modalState.backup.parent_favorites
    : [];
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = favorites.length ? "Choose a favorite parent" : "No saved backup parents";
  select.append(placeholder);
  favorites.forEach((path) => {
    const option = document.createElement("option");
    option.value = path;
    option.textContent = path;
    select.append(option);
  });
  select.disabled = !favorites.length || modalState.busy;
  renderFavoriteState();
}

// Disables modal mutations while one native operation is unresolved.
function setModalBusy(isBusy) {
  modalState.busy = isBusy;
  [
    "apply-backup-destination",
    "browse-backup-parent",
    "save-backup-parent-favorite",
    "close-backup-destination-modal",
  ].forEach((id) => {
    byId(id).disabled = isBusy;
  });
  setBusy(isBusy);
  renderFavorites();
}

// Applies a backend response to the modal and the parent Backup Mode workspace.
function applyResponse(data) {
  if (!data || !data.backup) return;
  modalState.backup = data.backup;
  renderFavorites();
  if (typeof modalState.onSaved === "function") modalState.onSaved(data);
}

// Runs one modal operation with the same visible diagnostics used throughout GitDesk.
async function runAction(action, payload) {
  if (modalState.busy) return null;
  setModalBusy(true);
  showMessage("");
  try {
    return await callNative(action, payload || {});
  } catch (error) {
    const message = error.message || "Backup destination could not be updated.";
    showMessage(message, true);
    appendActivity(message, true);
    throw error;
  } finally {
    setModalBusy(false);
  }
}

// Opens Finder or the platform picker and fills the field without persisting it.
async function browseParent() {
  const data = await runAction("chooseBackupDestination", {
    initial_path: byId("backup-parent-path").value,
  });
  if (!data || data.cancelled) return;
  byId("backup-parent-path").value = data.path || "";
  byId("backup-parent-favorites").value = "";
  renderFavoriteState();
}

// Saves the current existing folder as a Backup-specific quick-access parent.
async function saveFavorite() {
  const path = byId("backup-parent-path").value.trim();
  if (!path) {
    showMessage("Choose a backup parent folder before saving it as a favorite.", true);
    return;
  }
  const data = await runAction("saveBackupParentFavorite", { path });
  applyResponse(data);
  byId("backup-parent-favorites").value = data.backup.parent_favorites[0] || "";
  appendActivity("Backup parent favorite saved");
}

// Closes the modal and restores focus to the control that opened it.
function close() {
  if (modalState.busy) return;
  byId("backup-destination-modal").hidden = true;
  if (modalState.previousFocus && typeof modalState.previousFocus.focus === "function") {
    modalState.previousFocus.focus();
  }
}

// Persists the reviewed parent only when the user explicitly submits Apply.
async function applyDestination() {
  const path = byId("backup-parent-path").value.trim();
  if (!path) {
    showMessage("Choose a backup parent folder before applying.", true);
    return;
  }
  const data = await runAction("saveBackupDestination", { path });
  applyResponse(data);
  appendActivity("Backup destination selected");
  close();
}

// Opens the modal from current Backup state and preselects the active or newest favorite path.
function open(backup, onSaved) {
  modalState.backup = backup || {};
  modalState.onSaved = onSaved;
  modalState.previousFocus = document.activeElement;
  const favorites = Array.isArray(modalState.backup.parent_favorites)
    ? modalState.backup.parent_favorites
    : [];
  const initialPath = modalState.backup.destination || favorites[0] || "";
  byId("backup-parent-path").value = initialPath;
  renderFavorites();
  byId("backup-parent-favorites").value = favorites.includes(initialPath) ? initialPath : "";
  byId("backup-destination-modal").hidden = false;
  byId("backup-parent-path").focus();
}

// Binds modal browse, favorite, selection, submission, backdrop, and keyboard behavior once.
function bindEvents() {
  byId("browse-backup-parent").addEventListener("click", () => browseParent().catch(() => {}));
  byId("save-backup-parent-favorite").addEventListener("click", () => saveFavorite().catch(() => {}));
  byId("backup-parent-favorites").addEventListener("change", (event) => {
    if (!event.target.value) return;
    byId("backup-parent-path").value = event.target.value;
    renderFavoriteState();
  });
  byId("backup-parent-path").addEventListener("input", renderFavoriteState);
  byId("backup-destination-form").addEventListener("submit", (event) => {
    event.preventDefault();
    applyDestination().catch(() => {});
  });
  byId("close-backup-destination-modal").addEventListener("click", close);
  byId("backup-destination-modal").addEventListener("click", (event) => {
    if (event.target.id === "backup-destination-modal") close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !byId("backup-destination-modal").hidden) close();
  });
}

// Installs the reusable dialog before Backup Mode can open it.
function init() {
  injectModal();
  bindEvents();
}

window.GitDeskBackupDestinationModal = { open };

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
})();
