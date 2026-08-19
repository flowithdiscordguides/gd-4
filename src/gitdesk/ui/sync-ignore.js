/*
  Project-scoped Sync Ignore modal for the selected Local Mode version.
*/

// Owns rule editing while Python owns path validation, persistence, and sync enforcement.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;

if (!nativeBridge || !renderHelpers) {
  throw new Error("GitDesk Sync Ignore dependencies did not load.");
}

const { callNative } = nativeBridge;
const { appendActivity, byId, escapeHtml, setBusy, showMessage } = renderHelpers;
let currentState = null;
let activeTrigger = null;

// Inserts one focused modal beside the existing Local Mode dialogs.
function injectDialog() {
  if (document.getElementById("sync-ignore-dialog")) return;
  document.body.insertAdjacentHTML("beforeend", `
    <div id="sync-ignore-dialog" class="sync-ignore-dialog" hidden>
      <section class="sync-ignore-panel" role="dialog" aria-modal="true"
        aria-labelledby="sync-ignore-title">
        <header class="sync-ignore-header">
          <div>
            <span>Local → Private Beta</span>
            <h2 id="sync-ignore-title">Sync Ignore</h2>
            <p id="sync-ignore-summary">Choose version-relative files and folders to leave out.</p>
          </div>
          <div class="sync-ignore-header-actions">
            <button id="save-sync-ignore" class="primary" type="button">Apply</button>
            <button id="close-sync-ignore" type="button">Close</button>
          </div>
        </header>
        <div class="sync-ignore-notice">
          Ignored paths are removed from the next exact destination snapshot. Git history remains untouched.
        </div>
        <div id="sync-ignore-tree" class="sync-ignore-tree" aria-live="polite"></div>
        <footer class="sync-ignore-footer">
          <p id="sync-ignore-selection">0 paths ignored</p>
        </footer>
      </section>
    </div>
  `);
}

// Returns the selected physical version path already validated by Local Mode state.
function selectedVersionPath() {
  const path = document.getElementById("local-selected-version-path");
  return path ? path.textContent.trim() : "";
}

// Resolves the exact physical version owned by the Local or selected Sync Chain trigger.
function triggerVersionPath(trigger) {
  if (trigger && trigger.dataset.syncIgnoreTrigger === "chain") {
    const source = trigger.closest(".sync-chain-local-source");
    const version = source ? source.querySelector(".sync-chain-local-version") : null;
    return version ? version.value.trim() : "";
  }
  return selectedVersionPath();
}

// Renders one selectable node and recursively includes every child supplied by Python.
function renderTreeNode(node, level) {
  const children = (node.children || []).map((child) => renderTreeNode(child, level + 1)).join("");
  const checked = node.checked ? "checked" : "";
  const kind = node.type === "directory" ? "folder" : "file";
  const link = node.link ? '<span class="status-pill">link</span>' : "";
  const size = node.size_label ? `<small>${escapeHtml(node.size_label)}</small>` : "";
  const checkbox = `
      <input class="sync-ignore-check" type="checkbox" value="${escapeHtml(node.path)}"
        data-sync-ignore-type="${escapeHtml(node.type)}" aria-label="Ignore ${escapeHtml(node.name)}" ${checked}>
  `;
  const content = `
      <span class="sync-ignore-node-icon" aria-hidden="true"></span>
      <span class="sync-ignore-node-name">${escapeHtml(node.name)}</span>
      ${size}${link}
  `;
  if (node.type === "directory" && children) {
    return '<details class="sync-ignore-branch">'
      + `<summary class="sync-ignore-row sync-ignore-folder" style="--sync-ignore-indent:${level * 18}px">`
      + `<span class="sync-ignore-disclosure" aria-hidden="true"></span>${checkbox}${content}</summary>`
      + `<div class="sync-ignore-children">${children}</div></details>`;
  }
  return `
    <label class="sync-ignore-row sync-ignore-${kind}" style="--sync-ignore-indent:${level * 18}px">
      <span class="sync-ignore-disclosure sync-ignore-disclosure-empty" aria-hidden="true"></span>
      ${checkbox}${content}
    </label>
  `;
}

// Updates the visible selection count after any tree change.
function renderSelectionCount() {
  const count = document.querySelectorAll("#sync-ignore-tree .sync-ignore-check:checked").length;
  byId("sync-ignore-selection").textContent = `${count} path${count === 1 ? "" : "s"} ignored`;
}

// Reconciles parent checkboxes from the deepest branch upward so collapsed selections remain visible.
function renderPartialSelections() {
  const branches = Array.from(document.querySelectorAll("#sync-ignore-tree .sync-ignore-branch")).reverse();
  branches.forEach((branch) => {
    const parent = branch.querySelector(":scope > summary > .sync-ignore-check");
    const descendants = Array.from(branch.querySelectorAll(".sync-ignore-children .sync-ignore-check"));
    const allChecked = descendants.length > 0 && descendants.every((input) => input.checked);
    const hasSelection = descendants.some((input) => input.checked || input.indeterminate);
    if (parent.checked && !allChecked) parent.checked = false;
    parent.indeterminate = !parent.checked && hasSelection;
  });
}

// Displays the current project/version tree without trusting any filesystem text as HTML.
function renderState(state) {
  currentState = state || null;
  const tree = state && state.tree ? state.tree : { children: [] };
  const project = state && state.project ? state.project.name : "Local project";
  const version = state && state.version ? state.version.name : "selected version";
  byId("sync-ignore-summary").textContent = `${project} · ${version}`;
  byId("sync-ignore-tree").innerHTML = (tree.children || []).length
    ? tree.children.map((node) => renderTreeNode(node, 0)).join("")
    : '<div class="empty-state">This version has no selectable files or folders.</div>';
  renderPartialSelections();
  renderSelectionCount();
}

// Loads the current rules only after the user opens the selected-version action.
async function openDialog(trigger) {
  const versionPath = triggerVersionPath(trigger);
  if (!versionPath) {
    showMessage("Select a Local version before editing Sync Ignore.", true);
    return;
  }
  setBusy(true);
  showMessage("");
  try {
    const state = await callNative("syncIgnoreState", { version_path: versionPath });
    renderState(state);
    activeTrigger = trigger;
    byId("sync-ignore-dialog").hidden = false;
    activeTrigger.setAttribute("aria-expanded", "true");
    byId("close-sync-ignore").focus();
  } catch (error) {
    const message = error.message || "Sync Ignore could not be loaded.";
    showMessage(message, true);
    appendActivity(message, true);
  } finally {
    setBusy(false);
  }
}

// Closes the modal and restores focus to the selected-version action.
function closeDialog() {
  byId("sync-ignore-dialog").hidden = true;
  const trigger = activeTrigger;
  activeTrigger = null;
  if (trigger && trigger.isConnected) {
    trigger.setAttribute("aria-expanded", "false");
    trigger.focus();
  }
}

// Returns checked paths; backend sanitation collapses descendants covered by checked parents.
function selectedPaths() {
  return Array.from(document.querySelectorAll("#sync-ignore-tree .sync-ignore-check:checked"))
    .map((input) => input.value);
}

// Saves the complete selected rule set and re-renders the canonical backend result.
async function saveRules() {
  if (!currentState || !currentState.version) return;
  setBusy(true);
  showMessage("");
  try {
    const state = await callNative("saveSyncIgnore", {
      version_path: currentState.version.path,
      ignored_paths: selectedPaths(),
    });
    renderState(state);
    appendActivity("Sync Ignore rules saved");
    showMessage("Sync Ignore saved.");
  } catch (error) {
    const message = error.message || "Sync Ignore could not be saved.";
    showMessage(message, true);
    appendActivity(message, true);
  } finally {
    setBusy(false);
  }
}

// Applies a directory checkbox to every rendered descendant and then reconciles collapsed ancestor state.
function handleTreeChange(event) {
  const checkbox = event.target.closest(".sync-ignore-check");
  if (!checkbox) return;
  if (checkbox.dataset.syncIgnoreType === "directory") {
    const branch = checkbox.closest(".sync-ignore-branch");
    if (branch) {
      branch.querySelectorAll(".sync-ignore-check").forEach((child) => {
        child.checked = checkbox.checked;
      });
    }
  }
  renderPartialSelections();
  renderSelectionCount();
}

// Routes modal backdrop clicks, explicit controls, and Escape without affecting other dialogs.
function bindEvents() {
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest('#open-sync-ignore, [data-sync-ignore-trigger="chain"]');
    if (trigger) openDialog(trigger).catch(() => {});
  });
  byId("close-sync-ignore").addEventListener("click", closeDialog);
  byId("save-sync-ignore").addEventListener("click", () => saveRules().catch(() => {}));
  byId("sync-ignore-tree").addEventListener("change", handleTreeChange);
  byId("sync-ignore-dialog").addEventListener("click", (event) => {
    if (event.target.id === "sync-ignore-dialog") closeDialog();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !byId("sync-ignore-dialog").hidden) closeDialog();
  });
}

// Injects and binds after Local Mode has created the selected-version action dock.
function init() {
  injectDialog();
  bindEvents();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
})();
