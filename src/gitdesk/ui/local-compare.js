/*
  Project-scoped Local Mode version comparison and selected-file copying.
*/

// Owns comparison markup and state so the near-limit Local Mode controller remains focused on folder workflows.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;

if (!nativeBridge || !renderHelpers) {
  throw new Error("GitDesk Local Mode comparison dependencies did not load.");
}

const { callNative } = nativeBridge;
const { appendActivity, byId, setBusy, setTooltipText, showMessage } = renderHelpers;

// Comparison state follows Local Mode's project ownership and returns copy results through one callback.
const state = {
  local: null,
  projectPath: "",
  versionSignature: "",
  compare: null,
  pending: false,
  lastFocused: null,
  onLocalResponse: null,
  bound: false,
};

// Escapes filesystem-derived names and paths before inserting comparison markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Injects a compact Versions-card trigger and a body-level modal that matches the other Local Mode dialogs.
function injectUI() {
  if (!document.getElementById("open-local-compare")) {
    byId("sync-local-private-beta").insertAdjacentHTML("afterend", `
      <button id="open-local-compare" type="button" aria-haspopup="dialog" aria-controls="local-compare-modal"
        aria-expanded="false" aria-label="Compare project versions" title="Compare project versions"
        disabled></button>
    `);
  }
  if (document.getElementById("local-compare-modal")) return;
  document.body.insertAdjacentHTML("beforeend", `
    <section id="local-compare-modal" class="local-compare-modal" hidden>
      <div id="local-compare-dialog" class="local-compare-dialog" role="dialog" aria-modal="true"
        aria-labelledby="local-compare-title"
        aria-describedby="local-compare-project">
        <div class="panel-header local-compare-dialog-header">
          <div>
            <h2 id="local-compare-title">Compare Project Versions</h2>
            <p id="local-compare-project">Select a project with two versions</p>
          </div>
          <div class="local-compare-dialog-actions">
            <button id="local-compare-run" type="button">Compare</button>
            <button id="close-local-compare" type="button">Close</button>
          </div>
        </div>
        <div class="local-compare-controls">
          <label for="local-compare-source">
            <span>Source version</span>
            <select id="local-compare-source"></select>
          </label>
          <label for="local-compare-target">
            <span>Target version</span>
            <select id="local-compare-target"></select>
          </label>
        </div>
        <div class="local-compare-actions">
          <button id="local-compare-select-all" type="button">Select copyable</button>
          <button id="local-compare-copy" class="primary" type="button">Copy selected to target</button>
          <span id="local-compare-summary" class="local-compare-muted" role="status" aria-live="polite">
            No comparison loaded
          </span>
        </div>
        <div id="local-compare-files" class="local-compare-files" aria-live="polite"></div>
      </div>
    </section>
  `);
}

// Returns the active Local Mode project record from the latest backend state.
function activeProject(localState) {
  return (localState.projects || []).find((project) => project.path === localState.active_project) || null;
}

// Flattens only the selected project's versions while retaining feature context in each label.
function selectedProjectVersions(localState) {
  const project = activeProject(localState);
  const records = [];
  (project ? project.features || [] : []).forEach((feature) => {
    (feature.versions || []).forEach((version) => {
      records.push({
        path: version.path,
        label: `${feature.name} / ${version.name}`,
        featurePath: feature.path,
      });
    });
  });
  return records;
}

// Chooses the active version as target and its nearest project sibling as source.
function defaultSelection(localState, records) {
  const targetIndex = records.findIndex((record) => record.path === localState.active_version);
  const lastRecord = records.length ? records[records.length - 1] : null;
  const target = targetIndex >= 0 ? records[targetIndex].path : lastRecord ? lastRecord.path : "";
  const sourceIndex = targetIndex > 0 ? targetIndex - 1 : records.findIndex((record) => record.path !== target);
  const source = sourceIndex >= 0 ? records[sourceIndex].path : records[0] ? records[0].path : "";
  return { source, target };
}

// Preserves valid current selections while rebuilding options for the newly selected project.
function renderSelectors(localState) {
  const project = activeProject(localState);
  const records = selectedProjectVersions(localState);
  const defaults = defaultSelection(localState, records);
  const currentSource = byId("local-compare-source").value;
  const currentTarget = byId("local-compare-target").value;
  const options = records.length ? records.map((record) => (
    `<option value="${escapeHtml(record.path)}">${escapeHtml(record.label)}</option>`
  )).join("") : '<option value="">No versions</option>';
  byId("local-compare-source").innerHTML = options;
  byId("local-compare-target").innerHTML = options;
  byId("local-compare-source").value = records.some((record) => record.path === currentSource)
    ? currentSource : defaults.source;
  byId("local-compare-target").value = records.some((record) => record.path === currentTarget)
    ? currentTarget : defaults.target;
  byId("local-compare-project").textContent = project
    ? `${project.name} - ${records.length} versions available`
    : "Select a project with two versions";
  renderActionState(records.length);
}

// Disables comparison and copying when the selected project cannot provide two distinct versions.
function renderActionState(recordCount) {
  const source = byId("local-compare-source").value;
  const target = byId("local-compare-target").value;
  const canCompare = recordCount >= 2 && Boolean(source && target && source !== target);
  const comparisonMatches = Boolean(state.compare && state.compare.left === source && state.compare.right === target);
  const openButton = byId("open-local-compare");
  const unavailable = recordCount < 2;
  const tooltipText = unavailable
    ? "Select a project with at least two versions."
    : "Compare project versions";
  openButton.disabled = unavailable;
  openButton.setAttribute(
    "aria-label",
    unavailable ? `Compare project versions. ${tooltipText}` : tooltipText,
  );
  setTooltipText(openButton, tooltipText);
  byId("local-compare-source").disabled = state.pending;
  byId("local-compare-target").disabled = state.pending;
  byId("local-compare-run").disabled = !canCompare || state.pending;
  const copyableChecks = byId("local-compare-files").querySelectorAll(
    '.local-compare-copy-check[data-copyable="true"]',
  );
  copyableChecks.forEach((checkbox) => {
    checkbox.disabled = state.pending;
  });
  const hasCheckedPath = Array.from(copyableChecks).some((checkbox) => checkbox.checked);
  byId("local-compare-copy").disabled = !comparisonMatches || !hasCheckedPath || state.pending;
  byId("local-compare-select-all").disabled = !comparisonMatches || !copyableChecks.length || state.pending;
  byId("local-compare-dialog").setAttribute("aria-busy", String(state.pending));
}

// Renders changed paths and prevents target-only rows from being selected as source copies.
function renderCompareFiles() {
  const list = byId("local-compare-files");
  const compare = state.compare;
  if (!compare || !compare.files) {
    byId("local-compare-summary").textContent = "No comparison loaded";
    list.innerHTML = '<div class="empty-state">Choose two versions from the selected project.</div>';
    renderActionState(selectedProjectVersions(state.local || { projects: [] }).length);
    return;
  }
  const summary = compare.summary || {};
  const truncated = summary.truncated ? " - result limit reached" : "";
  byId("local-compare-summary").textContent = `${summary.modified || 0} modified - `
    + `${summary.deleted || 0} source-only - ${summary.added || 0} target-only${truncated}`;
  if (!compare.files.length) {
    list.innerHTML = '<div class="empty-state">Selected versions match.</div>';
    renderActionState(selectedProjectVersions(state.local || { projects: [] }).length);
    return;
  }
  list.innerHTML = compare.files.map((file) => {
    const copyable = file.status !== "added";
    const pillClass = file.status === "modified" ? "warning" : file.status === "deleted" ? "success" : "";
    return `
      <label class="local-compare-file-row">
        <input type="checkbox" class="local-compare-copy-check" data-copyable="${String(copyable)}"
          value="${escapeHtml(file.path)}"
          ${copyable ? "checked" : ""} ${copyable ? "" : "disabled"}>
        <span>
          <strong>${escapeHtml(file.path)}</strong>
          <small>${escapeHtml(file.left_size || "-")} -> ${escapeHtml(file.right_size || "-")}</small>
        </span>
        <span class="status-pill ${pillClass}">${escapeHtml(file.status)}</span>
      </label>
    `;
  }).join("");
  renderActionState(selectedProjectVersions(state.local || { projects: [] }).length);
}

// Runs a comparison bridge action with the same DevTools feedback contract as other Local Mode actions.
async function runAction(action, payload, successMessage) {
  state.pending = true;
  renderActionState(selectedProjectVersions(state.local || { projects: [] }).length);
  setBusy(true);
  showMessage("");
  try {
    const data = await callNative(action, payload);
    appendActivity(successMessage);
    return data;
  } catch (error) {
    const message = error.message || "Version comparison failed.";
    console.error(`Local comparison action failed: ${action}`, error);
    showMessage(message, true);
    appendActivity(message, true);
    throw error;
  } finally {
    state.pending = false;
    renderActionState(selectedProjectVersions(state.local || { projects: [] }).length);
    setBusy(false);
  }
}

// Requests an exact folder comparison for the two current project-scoped selections.
async function compareVersions() {
  state.compare = null;
  renderCompareFiles();
  state.compare = await runAction("compareLocalVersions", {
    left_path: byId("local-compare-source").value,
    right_path: byId("local-compare-target").value,
  }, "Project versions compared");
  renderCompareFiles();
}

// Selects every source-side row that the backend can safely copy into the target.
function selectCopyable() {
  byId("local-compare-files").querySelectorAll(".local-compare-copy-check:not(:disabled)").forEach((checkbox) => {
    checkbox.checked = true;
  });
  renderActionState(selectedProjectVersions(state.local || { projects: [] }).length);
}

// Copies checked source paths into the target and hands fresh Local Mode state back to its owner.
async function copySelected() {
  const paths = Array.from(
    byId("local-compare-files").querySelectorAll(".local-compare-copy-check:checked:not(:disabled)"),
  )
    .map((checkbox) => checkbox.value);
  const data = await runAction("copyComparedVersionFiles", {
    source_path: byId("local-compare-source").value,
    target_path: byId("local-compare-target").value,
    paths,
  }, "Selected version files copied");
  state.compare = null;
  if (state.onLocalResponse) state.onLocalResponse(data);
  renderCompareFiles();
}

// Clears stale results when the user changes either side of the comparison.
function resetComparison() {
  state.compare = null;
  renderCompareFiles();
}

// Opens the comparison dialog without changing either selected version.
function openModal() {
  const modal = byId("local-compare-modal");
  if (byId("open-local-compare").disabled) return;
  state.lastFocused = document.activeElement;
  document.querySelector(".app-shell").inert = true;
  modal.hidden = false;
  byId("open-local-compare").setAttribute("aria-expanded", "true");
  byId("local-compare-source").focus();
}

// Closes the dialog and optionally returns keyboard focus to its Versions-card trigger.
function closeModal(restoreFocus = true) {
  const modal = byId("local-compare-modal");
  if (modal.hidden) return;
  modal.hidden = true;
  document.querySelector(".app-shell").inert = false;
  byId("open-local-compare").setAttribute("aria-expanded", "false");
  if (restoreFocus) {
    const fallback = byId("open-local-compare");
    const focusTarget = state.lastFocused && state.lastFocused.isConnected ? state.lastFocused : fallback;
    if (!focusTarget.disabled) focusTarget.focus();
  }
  state.lastFocused = null;
}

// Closes only for the explicit Close control or the modal backdrop, never for clicks inside the dialog.
function handleModalClick(event) {
  if (event.target.id === "close-local-compare" || event.target === byId("local-compare-modal")) {
    closeModal();
  }
}

// Lets keyboard users dismiss the modal consistently with the New Project workflow.
function handleModalKeydown(event) {
  if (event.key === "Escape" && !byId("local-compare-modal").hidden) {
    event.preventDefault();
    event.stopPropagation();
    closeModal();
    return;
  }
  if (event.key !== "Tab" || byId("local-compare-modal").hidden) return;
  const controls = Array.from(byId("local-compare-dialog").querySelectorAll(
    'button:not(:disabled), select:not(:disabled), input:not(:disabled), [tabindex]:not([tabindex="-1"])',
  ));
  if (!controls.length) return;
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

// Applies Local Mode state and discards results when project ownership or available versions change.
function applyState(localState) {
  const nextState = localState || { projects: [] };
  const signature = selectedProjectVersions(nextState).map((record) => record.path).join("\n");
  const projectChanged = state.projectPath !== nextState.active_project;
  if (projectChanged || state.versionSignature !== signature) {
    state.compare = null;
    state.projectPath = nextState.active_project || "";
    state.versionSignature = signature;
  }
  if (projectChanged) closeModal(false);
  state.local = nextState;
  renderSelectors(nextState);
  renderCompareFiles();
}

// Binds injected controls once and stores the Local Mode state callback used after copy operations.
function bind(options = {}) {
  if (state.bound) return;
  state.bound = true;
  state.onLocalResponse = options.onLocalResponse || null;
  byId("open-local-compare").addEventListener("click", openModal);
  byId("local-compare-modal").addEventListener("click", handleModalClick);
  document.addEventListener("keydown", handleModalKeydown);
  byId("local-compare-run").addEventListener("click", () => compareVersions().catch(() => {}));
  byId("local-compare-select-all").addEventListener("click", selectCopyable);
  byId("local-compare-copy").addEventListener("click", () => copySelected().catch(() => {}));
  byId("local-compare-files").addEventListener("change", () => {
    renderActionState(selectedProjectVersions(state.local || { projects: [] }).length);
  });
  byId("local-compare-source").addEventListener("change", resetComparison);
  byId("local-compare-target").addEventListener("change", resetComparison);
}

window.GitDeskLocalCompare = { applyState, bind, injectUI };
})();
