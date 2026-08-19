/*
  Lazy Backup source selection, include/exclude rules, and required creation confirmation.
*/
// Owns the mandatory review step before any dated Backup version can be created.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const selectionModel = window.GitDeskBackupSelectionModel;
const transferModal = window.GitDeskBackupTransferModal;
if (!nativeBridge || !renderHelpers || !selectionModel || !transferModal) {
  throw new Error("GitDesk Backup selection dependencies did not load.");
}
const { callNative } = nativeBridge;
const { appendActivity, byId, setBusy, showMessage } = renderHelpers;
const selectionState = {
  backup: {},
  busy: false,
  loadingFolders: new Set(),
  onBusy: null,
  onSaved: null,
  previousFocus: null,
  rules: {},
  tree: [],
};
// Inserts the body-level selection dialog and its explicit confirmation boundary.
function injectModal() {
  if (document.getElementById("backup-selection-modal")) return;
  document.body.insertAdjacentHTML("beforeend", `
    <section id="backup-selection-modal" class="backup-selection-modal" hidden>
      <div class="backup-selection-dialog" role="dialog" aria-modal="true"
        aria-labelledby="backup-selection-title" aria-describedby="backup-selection-explanation">
        <header class="panel-header backup-selection-header">
          <div>
            <span>Required backup scope</span>
            <h2 id="backup-selection-title">Choose files and folders</h2>
            <p id="backup-selection-explanation">
              Check exactly what this dated backup version should contain.
            </p>
          </div>
          <div class="button-row">
            <button id="confirm-create-backup" type="button" disabled>Create backup</button>
            <button id="close-backup-selection" type="button">Close</button>
          </div>
        </header>
        <div class="backup-selection-toolbar">
          <p id="backup-selection-summary">Loading registered sources…</p>
          <div class="button-row">
            <button id="select-all-backup-sources" type="button">Select all</button>
            <button id="clear-backup-sources" type="button">Clear</button>
          </div>
        </div>
        <div id="backup-selection-tree" class="backup-selection-tree" aria-live="polite"></div>
        <label class="backup-selection-confirmation">
          <input id="backup-selection-confirmed" type="checkbox">
          <span>I reviewed this selection. Only checked files and folders will be included in the new backup
            version. Unchecked content will not be copied; earlier backup versions stay unchanged.</span>
        </label>
      </div>
    </section>
  `);
}

// Keeps every loaded checkbox synchronized with its effective and mixed selection state.
function renderChecks() {
  document.querySelectorAll(".backup-selection-check").forEach((checkbox) => {
    const included = selectionModel.pathIncluded(
      selectionState.rules,
      checkbox.dataset.sourceId,
      checkbox.dataset.path || "",
    );
    checkbox.checked = included;
    checkbox.indeterminate = selectionModel.pathMixed(
      selectionState.rules,
      checkbox.dataset.sourceId,
      checkbox.dataset.path || "",
    );
    checkbox.disabled = selectionState.busy || checkbox.dataset.available === "false";
  });
}

// Updates selection count, confirmation availability, and the transactional action label.
function renderSummary() {
  const selection = selectionModel.serializedSelection(selectionState.rules);
  const includedRules = selection.reduce((count, item) => {
    return count + Object.values(item.rules).filter(Boolean).length;
  }, 0);
  const confirmed = byId("backup-selection-confirmed").checked;
  byId("backup-selection-summary").textContent = includedRules
    ? `${includedRules} selected file or folder scope${includedRules === 1 ? "" : "s"}`
    : "Select at least one file or folder.";
  byId("confirm-create-backup").disabled = selectionState.busy || !confirmed || !includedRules;
  byId("confirm-create-backup").textContent = selectionState.busy
    ? "Creating backup…"
    : selectionState.backup.latest_snapshot ? "Sync backup" : "Create first backup";
  renderChecks();
}

// Creates one New Version-style file or collapsible folder row with a safe text label.
function createTreeNode(node, level) {
  const isDirectory = node.kind === "directory";
  const branch = isDirectory && node.expandable;
  const wrapper = document.createElement(branch ? "details" : "div");
  wrapper.className = branch ? "backup-selection-branch" : "backup-selection-leaf";
  if (branch) {
    wrapper.dataset.sourceId = node.source_id;
    wrapper.dataset.path = node.path || "";
    wrapper.dataset.loaded = "false";
  }
  const row = document.createElement(branch ? "summary" : "div");
  row.className = `backup-selection-row backup-selection-${isDirectory ? "folder" : "file"}`;
  row.style.setProperty("--backup-selection-indent", `${level * 18}px`);
  const caret = document.createElement("span");
  caret.className = branch ? "backup-selection-caret" : "backup-selection-caret-spacer";
  caret.setAttribute("aria-hidden", "true");
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "backup-selection-check";
  checkbox.dataset.sourceId = node.source_id;
  checkbox.dataset.path = node.path || "";
  checkbox.dataset.available = String(node.available !== false);
  checkbox.setAttribute("aria-label", `Include ${node.name} in this backup`);
  const icon = document.createElement("span");
  icon.className = "backup-selection-icon";
  icon.setAttribute("aria-hidden", "true");
  const name = document.createElement("span");
  name.className = "backup-selection-name";
  name.textContent = node.name;
  row.append(caret, checkbox, icon, name);
  if (node.size_label) {
    const size = document.createElement("small");
    size.textContent = node.size_label;
    row.append(size);
  }
  if (node.available === false) {
    const unavailable = document.createElement("span");
    unavailable.className = "status-pill danger";
    unavailable.textContent = "unavailable";
    row.append(unavailable);
  }
  wrapper.append(row);
  if (branch) {
    const children = document.createElement("div");
    children.className = "backup-selection-children";
    wrapper.append(children);
  }
  return wrapper;
}

// Replaces one tree region with a safe text-only empty or error state.
function setEmptyState(container, message) {
  const empty = document.createElement("div");
  empty.className = "empty-state";
  empty.textContent = message;
  container.replaceChildren(empty);
}

// Adds one continuation control without hiding children already loaded from the same folder.
function appendLoadMore(container, branch, nextOffset, level) {
  if (nextOffset == null) return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "backup-selection-load-more";
  button.textContent = "Load more";
  button.style.setProperty("--backup-selection-indent", `${level * 18}px`);
  button.addEventListener("click", () => {
    button.remove();
    loadChildren(branch, nextOffset, level).catch(() => {});
  });
  container.append(button);
}

// Loads one safe direct-child page when a folder is expanded.
async function loadChildren(branch, offset = 0, level = 1) {
  const key = `${branch.dataset.sourceId}\0${branch.dataset.path}\0${offset}`;
  if (selectionState.loadingFolders.has(key)) return;
  selectionState.loadingFolders.add(key);
  const container = branch.querySelector(":scope > .backup-selection-children");
  if (!offset) container.innerHTML = '<div class="empty-state">Loading folder…</div>';
  try {
    const data = await callNative("backupSelectionChildren", {
      source_id: branch.dataset.sourceId,
      path: branch.dataset.path,
      offset,
    });
    if (!offset) container.replaceChildren();
    data.children.forEach((node) => container.append(createTreeNode(node, level)));
    if (!data.children.length && !offset) {
      container.innerHTML = '<div class="empty-state">Empty folder</div>';
    }
    appendLoadMore(container, branch, data.next_offset, level);
    branch.dataset.loaded = "true";
    renderSummary();
  } catch (error) {
    setEmptyState(container, error.message || "Folder could not be loaded.");
    showMessage(error.message || "Backup selection folder could not be loaded.", true);
  } finally {
    selectionState.loadingFolders.delete(key);
  }
}

// Renders stable mode groups and their current registered source roots.
function renderTree() {
  const tree = byId("backup-selection-tree");
  tree.replaceChildren();
  selectionState.tree.forEach((group) => {
    const section = document.createElement("section");
    section.className = "backup-selection-group";
    if (group.kind === "detected-changes") section.classList.add("detected-changes");
    const heading = document.createElement("h3");
    heading.textContent = group.label;
    section.append(heading);
    if (!group.children.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = group.kind === "detected-changes" ? "No detected changes"
        : group.kind === "optional-sources" ? "No additional sources" : "No registered sources";
      section.append(empty);
    }
    group.children.forEach((node) => section.append(createTreeNode(node, 0)));
    tree.append(section);
  });
  renderSummary();
}

// Applies one backend selection payload without trusting paths as markup.
function applyTreeData(data) {
  const review = selectionModel.reviewData(data);
  selectionState.tree = review.tree;
  selectionState.rules = review.rules;
  renderTree();
}

// Disables modal mutation while the confirmed snapshot transaction runs.
function setModalBusy(isBusy) {
  selectionState.busy = isBusy;
  if (typeof selectionState.onBusy === "function") {
    selectionState.onBusy(isBusy || !byId("backup-selection-modal").hidden);
  }
  setBusy(isBusy);
  byId("close-backup-selection").disabled = isBusy;
  byId("select-all-backup-sources").disabled = isBusy;
  byId("clear-backup-sources").disabled = isBusy;
  byId("backup-selection-confirmed").disabled = isBusy;
  renderSummary();
}

// Closes an idle selection review and restores its opening control.
function close() {
  if (selectionState.busy) return;
  byId("backup-selection-modal").hidden = true;
  if (typeof selectionState.onBusy === "function") selectionState.onBusy(false);
  const target = selectionState.previousFocus;
  if (target && target.isConnected && typeof target.focus === "function") target.focus();
}

// Creates a snapshot only after both frontend and backend receive explicit confirmation.
async function createBackup() {
  const selection = selectionModel.serializedSelection(selectionState.rules);
  if (!byId("backup-selection-confirmed").checked || !selection.length || selectionState.busy) return;
  setModalBusy(true);
  showMessage("");
  try {
    const data = await transferModal.start(selection);
    if (typeof selectionState.onSaved === "function") selectionState.onSaved(data);
    if (data.no_changes) {
      showMessage("No backup changes detected.");
      appendActivity("Backup already current");
    } else {
      const skipped = Array.isArray(data.skipped_items) ? data.skipped_items.length : 0;
      showMessage(skipped ? `Backup created with ${skipped} skipped item(s): ${data.created_version.name}`
        : `Backup created: ${data.created_version.name}`);
      appendActivity(skipped ? `Backup version created with ${skipped} skipped item(s)` : "Backup version created");
    }
    setModalBusy(false);
    close();
  } catch (error) {
    setModalBusy(false);
    const cancelled = error.code === "BACKUP_CANCELLED";
    const message = cancelled ? "Backup cancelled. No version was created."
      : error.message || "Backup could not be created.";
    showMessage(message, !cancelled);
    appendActivity(message, !cancelled);
  }
}
// Opens the required review immediately, then loads current roots and saved rules.
async function open(backup, onSaved, onBusy) {
  selectionState.backup = backup || {};
  selectionState.onBusy = onBusy;
  selectionState.onSaved = onSaved;
  selectionState.previousFocus = document.activeElement;
  selectionState.rules = {};
  selectionState.tree = [];
  byId("backup-selection-confirmed").checked = false;
  byId("backup-selection-tree").innerHTML = '<div class="empty-state">Loading registered sources…</div>';
  byId("backup-selection-modal").hidden = false;
  if (typeof selectionState.onBusy === "function") selectionState.onBusy(true);
  byId("close-backup-selection").focus();
  try {
    applyTreeData(await callNative("backupSelectionTree", {}));
  } catch (error) {
    setEmptyState(byId("backup-selection-tree"), error.message || "Backup sources could not be loaded.");
    showMessage(error.message || "Backup sources could not be loaded.", true);
  }
}
// Binds tree selection, lazy expansion, bulk choices, confirmation, dismissal, and creation.
function bindEvents() {
  byId("backup-selection-tree").addEventListener("click", (event) => {
    if (event.target.matches(".backup-selection-check")) event.stopPropagation();
  });
  byId("backup-selection-tree").addEventListener("change", (event) => {
    if (!event.target.matches(".backup-selection-check")) return;
    selectionModel.setPathRule(
      selectionState.rules,
      event.target.dataset.sourceId,
      event.target.dataset.path || "",
      event.target.checked,
    );
    byId("backup-selection-confirmed").checked = false;
    renderSummary();
  });
  byId("backup-selection-tree").addEventListener("toggle", (event) => {
    const branch = event.target.closest(".backup-selection-branch");
    if (branch && branch.open && branch.dataset.loaded === "false") {
      const level = branch.dataset.path ? branch.dataset.path.split("/").length + 1 : 1;
      loadChildren(branch, 0, level).catch(() => {});
    }
  }, true);
  byId("select-all-backup-sources").addEventListener("click", () => {
    selectionState.rules = selectionModel.selectAll(selectionState.tree);
    byId("backup-selection-confirmed").checked = false;
    renderSummary();
  });
  byId("clear-backup-sources").addEventListener("click", () => {
    selectionState.rules = {};
    byId("backup-selection-confirmed").checked = false;
    renderSummary();
  });
  byId("backup-selection-confirmed").addEventListener("change", renderSummary);
  byId("confirm-create-backup").addEventListener("click", () => createBackup().catch(() => {}));
  byId("close-backup-selection").addEventListener("click", close);
  byId("backup-selection-modal").addEventListener("click", (event) => {
    if (event.target.id === "backup-selection-modal") close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !byId("backup-selection-modal").hidden) close();
  });
}
// Installs the reusable mandatory selection surface before Backup Mode binds its action.
function init() {
  injectModal();
  bindEvents();
}

window.GitDeskBackupSelectionModal = { open };
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
})();
