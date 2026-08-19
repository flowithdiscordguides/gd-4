/*
  Permanent version-deletion controller for the Local Mode version list.
*/

// Connects each inline trash action to the native deletion transaction without owning list markup.
(() => {
const versionDetail = window.GitDeskLocalVersionDetail;
const renderHelpers = window.GitDeskRender;

if (!versionDetail || !renderHelpers) {
  throw new Error("GitDesk Local Mode version-deletion dependencies did not load.");
}

const { byId } = renderHelpers;
let controller = {};
let bound = false;
const state = {
  busy: false,
  path: "",
  name: "",
  returnFocus: null,
};

// Injects one app-owned confirmation surface because desktop WebViews cannot reliably present browser dialogs.
function injectDeleteDialog() {
  if (document.getElementById("local-version-delete-modal")) {
    return;
  }
  document.body.insertAdjacentHTML("beforeend", `
    <section id="local-version-delete-modal" class="local-version-delete-modal" hidden>
      <div id="local-version-delete-dialog" class="local-version-delete-dialog" role="dialog" aria-modal="true"
        aria-labelledby="local-version-delete-title" aria-describedby="local-version-delete-description" tabindex="-1">
        <header>
          <span>Permanent deletion</span>
          <h2 id="local-version-delete-title">Delete this version?</h2>
        </header>
        <p id="local-version-delete-description" class="local-version-delete-warning">
          The complete <strong id="local-version-delete-name"></strong> folder and everything inside it will be
          permanently deleted. This cannot be undone.
        </p>
        <p id="local-version-delete-status" class="local-version-delete-status"
          role="status" aria-live="polite"></p>
        <div class="local-version-delete-actions">
          <button id="cancel-local-version-delete" type="button">Cancel</button>
          <button id="confirm-local-version-delete" type="button">Delete version</button>
        </div>
      </div>
    </section>
  `);
}

// Synchronizes dialog visibility, exact version identity, and non-interactive native-deletion state.
function renderDeleteDialog() {
  const modal = byId("local-version-delete-modal");
  const dialog = byId("local-version-delete-dialog");
  const cancelButton = byId("cancel-local-version-delete");
  const deleteButton = byId("confirm-local-version-delete");
  modal.hidden = !state.path;
  dialog.setAttribute("aria-busy", String(state.busy));
  byId("local-version-delete-name").textContent = state.name;
  cancelButton.disabled = state.busy;
  deleteButton.disabled = state.busy;
  deleteButton.textContent = state.busy ? "Deleting…" : "Delete version";
}

// Opens confirmation for one exact rendered row and moves focus to the safe cancellation action.
function openDeleteDialog(versionPath, versionName, trigger) {
  if (!versionPath || state.busy) {
    return;
  }
  state.path = versionPath;
  state.name = versionName || "this version";
  state.returnFocus = trigger || document.activeElement;
  byId("local-version-delete-status").textContent = "";
  renderDeleteDialog();
  byId("cancel-local-version-delete").focus();
}

// Closes an idle dialog without deleting and restores focus to the row action that opened it.
function closeDeleteDialog() {
  if (state.busy || !state.path) {
    return;
  }
  const returnFocus = state.returnFocus;
  state.path = "";
  state.name = "";
  state.returnFocus = null;
  renderDeleteDialog();
  if (returnFocus && returnFocus.isConnected && typeof returnFocus.focus === "function") {
    returnFocus.focus();
  }
}

// Deletes the exact listed version, then applies the backend's refreshed selection and filesystem state.
async function deleteVersion(versionPath) {
  const localState = controller.getLocalState();
  const data = await controller.runAction("deleteLocalVersion", {
    project_path: localState.active_project,
    feature_path: localState.active_feature,
    version_path: versionPath,
  }, "Local version deleted");
  controller.applyLocalResponse(data);
}

// Confirms the pending row through the existing native transaction and keeps failures available for retry.
async function confirmDeleteVersion() {
  if (!state.path || state.busy) {
    return;
  }
  const versionPath = state.path;
  state.busy = true;
  byId("local-version-delete-status").textContent = "";
  renderDeleteDialog();
  byId("local-version-delete-dialog").focus();
  try {
    await deleteVersion(versionPath);
    state.busy = false;
    state.path = "";
    state.name = "";
    state.returnFocus = null;
    renderDeleteDialog();
    const nextFocus = document.querySelector("#local-version-list .local-version-row.active")
      || document.querySelector("#local-versions-card .local-accordion-toggle");
    if (nextFocus) {
      nextFocus.focus();
    }
  } catch (error) {
    state.busy = false;
    byId("local-version-delete-status").textContent =
      error.message || "GitDesk could not delete this version.";
    renderDeleteDialog();
    byId("confirm-local-version-delete").focus();
  }
}

// Supports backdrop dismissal, Escape, and a contained two-button keyboard focus cycle.
function handleDialogInteraction(event) {
  if (!state.path || state.busy) {
    return;
  }
  if (event.type === "click" && event.target.id === "local-version-delete-modal") {
    closeDeleteDialog();
    return;
  }
  if (event.type !== "keydown") {
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    closeDeleteDialog();
    return;
  }
  if (event.key !== "Tab") {
    return;
  }
  const cancelButton = byId("cancel-local-version-delete");
  const deleteButton = byId("confirm-local-version-delete");
  if (event.shiftKey && document.activeElement === cancelButton) {
    event.preventDefault();
    deleteButton.focus();
  } else if (!event.shiftKey && document.activeElement === deleteButton) {
    event.preventDefault();
    cancelButton.focus();
  }
}

// Binds the persistent version list after Local Mode has injected its dynamic markup.
function bind(options) {
  controller = options || {};
  injectDeleteDialog();
  versionDetail.bind({ onDeleteVersion: openDeleteDialog });
  if (bound) {
    return;
  }
  bound = true;
  byId("cancel-local-version-delete").addEventListener("click", closeDeleteDialog);
  byId("confirm-local-version-delete").addEventListener("click", confirmDeleteVersion);
  byId("local-version-delete-modal").addEventListener("click", handleDialogInteraction);
  document.addEventListener("keydown", handleDialogInteraction);
}

window.GitDeskLocalVersionDelete = { bind };
})();
