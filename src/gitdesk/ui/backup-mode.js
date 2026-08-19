/*
  Backup Mode workspace, scheduled scans, change notification, and version history.
*/

// Owns Backup Mode state while Python owns registered-source hashing and snapshot transactions.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const destinationModal = window.GitDeskBackupDestinationModal;
const selectionModal = window.GitDeskBackupSelectionModal;

if (!nativeBridge || !renderHelpers || !destinationModal || !selectionModal) {
  throw new Error("GitDesk Backup Mode dependencies did not load.");
}

const { callNative } = nativeBridge;
const { appendActivity, byId, escapeHtml, setBusy, showMessage } = renderHelpers;
const SCAN_INTERVAL_MS = 15 * 60 * 1000;
const state = {
  data: null,
  busy: false,
  timer: 0,
  lastScanStarted: 0,
  mergeBusy: false,
  parentVersionPath: "",
};

// Inserts the Backup page icon beside Local and Media workspace destinations.
function injectToolbarButton() {
  if (document.querySelector('.tab-button[data-tab="backup"]')) return;
  const button = document.createElement("button");
  button.className = "tab-button";
  button.type = "button";
  button.dataset.tab = "backup";
  button.title = "Backup Mode";
  button.setAttribute("aria-label", "Backup Mode");
  button.innerHTML = `
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M4 5h16v14H4zM8 5v5h8V5M8 15h8"></path>
      <path d="M12 12v6m-3-3 3 3 3-3"></path>
    </svg>
  `;
  const mediaButton = document.querySelector('.tab-button[data-tab="media"]');
  mediaButton.insertAdjacentElement("afterend", button);
}

// Inserts the focused destination, scan status, inventory, changes, and version-history workspace.
function injectPanel() {
  if (document.getElementById("panel-backup")) return;
  const panel = document.createElement("section");
  panel.id = "panel-backup";
  panel.className = "panel";
  panel.setAttribute("aria-labelledby", "backup-title");
  panel.innerHTML = `
    <header class="panel-header backup-header">
      <div><span class="backup-kicker">Versioned local safety</span>
        <h2 id="backup-title">Backup Mode</h2>
        <p id="backup-summary">Choose a destination to create the first backup version.</p></div>
      <div class="button-row">
        <button id="scan-backup-changes" type="button">Scan for changes</button>
        <button id="sync-backup" class="primary" type="button">Create backup</button>
      </div>
    </header>
    <div class="backup-layout">
      <section class="backup-destination-card">
        <div><strong>Backup destination</strong>
          <p>Use a local folder, USB drive, or external hard drive.</p></div>
        <div class="backup-destination-row">
          <code id="backup-destination">No destination selected</code>
          <button id="choose-backup-destination" type="button">Choose folder</button>
          <button id="open-backup-destination" type="button" disabled>Open</button>
        </div>
      </section>
      <section class="backup-inventory" aria-labelledby="backup-inventory-title">
        <div><h3 id="backup-inventory-title">Complete source inventory</h3>
          <p>Choose content from these registered roots before creating each backup.</p></div>
        <div id="backup-inventory-counts" class="backup-inventory-counts"></div>
      </section>
      <section class="backup-change-card" aria-labelledby="backup-change-title">
        <div class="backup-section-heading"><div><h3 id="backup-change-title">Detected changes</h3>
          <p id="backup-scan-time">No scan completed</p></div>
          <div id="backup-change-totals" class="backup-change-totals"></div></div>
        <div id="backup-source-errors" class="backup-source-errors" hidden></div>
        <div id="backup-change-list" class="backup-change-list" aria-live="polite"></div>
      </section>
      <section class="backup-history-card" aria-labelledby="backup-history-title">
        <div class="backup-section-heading"><div><h3 id="backup-history-title">Backup versions</h3>
          <p>Choose a parent; every newer version merges into it without changing the child folders.</p></div>
          <button id="merge-down-backup" type="button" disabled>Merge down</button></div>
        <div id="backup-version-list" class="backup-version-list" aria-live="polite"></div>
      </section>
    </div>
  `;
  document.querySelector(".workspace").append(panel);
}

// Ensures the Backup page icon owns one reusable notification dot.
function backupDot() {
  const button = document.querySelector('.tab-button[data-tab="backup"]');
  let dot = button.querySelector(".tab-alert-dot");
  if (!dot) {
    dot = document.createElement("span");
    dot.className = "tab-alert-dot";
    dot.setAttribute("aria-hidden", "true");
    button.append(dot);
  }
  return dot;
}

// Applies changed, unavailable, or clear state to the Backup page icon and tooltip.
function renderNotification(backup) {
  const button = document.querySelector('.tab-button[data-tab="backup"]');
  const dot = backupDot();
  const scan = backup.scan || {};
  if ((scan.errors || []).length) {
    dot.hidden = false;
    dot.className = "tab-alert-dot danger";
    button.title = "Backup source unavailable";
  } else if (scan.has_changes) {
    dot.hidden = false;
    dot.className = "tab-alert-dot release-ready";
    button.title = `${scan.total || 0} backup changes detected`;
  } else {
    dot.hidden = true;
    dot.className = "tab-alert-dot";
    button.title = "Backup Mode";
  }
}

// Formats byte totals without requiring a frontend dependency.
function sizeLabel(byteCount) {
  let value = Number(byteCount || 0);
  const units = ["B", "KB", "MB", "GB", "TB"];
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${index ? value.toFixed(1) : Math.round(value)} ${units[index]}`;
}

// Renders the four explicit backup groups from non-scanning registry counts.
function renderInventory(inventory) {
  const groups = [
    ["Local Mode", inventory.local || 0],
    ["Repo Mode", inventory.repo || 0],
    ["Media Mode", inventory.media || 0],
    ["Settings", inventory.settings || 0],
  ];
  byId("backup-inventory-counts").innerHTML = groups.map(([label, count]) => `
    <div><strong>${count}</strong><span>${label} source${count === 1 ? "" : "s"}</span></div>
  `).join("");
}

// Renders unavailable sources prominently because an incomplete snapshot is never accepted as success.
function renderErrors(errors) {
  const container = byId("backup-source-errors");
  container.hidden = !errors.length;
  container.innerHTML = errors.length ? `
    <strong>Backup blocked: ${errors.length} registered source
      ${errors.length === 1 ? "is" : "are"} unavailable</strong>
    ${errors.map((error) => `<div><span>${escapeHtml(error.label)}</span>
      <code>${escapeHtml(error.path)}</code><small>${escapeHtml(error.message)}</small></div>`).join("")}
  ` : "";
}

// Renders pending path-level changes and bounded scan truncation state.
function renderChanges(scan) {
  const totals = byId("backup-change-totals");
  totals.innerHTML = `
    <span class="status-pill added">+${scan.added || 0}</span>
    <span class="status-pill warning">~${scan.modified || 0}</span>
    <span class="status-pill danger">−${scan.deleted || 0}</span>
  `;
  byId("backup-scan-time").textContent = scan.scanned_at
    ? `Last scan ${new Date(scan.scanned_at).toLocaleString()}`
    : "No scan completed";
  renderErrors(scan.errors || []);
  const changes = scan.changes || [];
  byId("backup-change-list").innerHTML = changes.length ? changes.map((change) => `
    <div class="backup-change-row"><span class="status-pill ${change.kind === "added" ? "added"
      : change.kind === "deleted" ? "danger" : "warning"}">${escapeHtml(change.kind)}</span>
      <code>${escapeHtml(change.path)}</code></div>
  `).join("") + (scan.truncated ? '<p class="row-meta">Additional changes are recorded in the full scan.</p>' : "")
    : '<div class="empty-state">No changed files detected.</div>';
}

// Keeps merge availability factual for the selected parent and its newer child count.
function renderMergeAction(versions) {
  const parentIndex = versions.findIndex((version) => version.path === state.parentVersionPath);
  const childCount = Math.max(0, parentIndex);
  const button = byId("merge-down-backup");
  button.disabled = state.busy || state.mergeBusy || !childCount;
  button.textContent = state.mergeBusy ? "Merging…" : "Merge down";
  button.title = childCount
    ? `Copy and merge ${childCount} newer version${childCount === 1 ? "" : "s"} into this parent`
    : "Choose an older version that has newer child versions";
}

// Renders completed versions newest first with explicit parent selection and factual counts.
function renderVersions(versions) {
  if (!versions.some((version) => version.path === state.parentVersionPath)) state.parentVersionPath = "";
  byId("backup-version-list").innerHTML = versions.length ? versions.map((version) => `
    <div class="backup-version-row${state.parentVersionPath === version.path ? " selected-parent" : ""}">
      <label class="backup-version-choice">
        <input type="radio" name="backup-parent-version" data-backup-parent-version="${escapeHtml(version.path)}"
          ${state.parentVersionPath === version.path ? "checked" : ""}
          ${state.busy || state.mergeBusy ? "disabled" : ""}>
        <span><strong>${escapeHtml(version.name)}</strong>
        <small>${version.file_count} files · ${sizeLabel(version.total_bytes)}
          · +${version.changes.added} ~${version.changes.modified} −${version.changes.deleted}
          ${version.skipped_count ? ` · ${version.skipped_count} skipped` : ""}</small></span>
      </label>
      <button type="button" data-open-backup-version="${escapeHtml(version.path)}"
        ${state.busy || state.mergeBusy ? "disabled" : ""}>Open</button>
    </div>
  `).join("") : '<div class="empty-state">No backup versions created yet.</div>';
  renderMergeAction(versions);
}

// Applies one canonical backend payload to every Backup Mode surface.
function applyState(data) {
  state.data = data || {};
  const backup = state.data.backup || { scan: {}, versions: [] };
  const hasDestination = Boolean(backup.destination);
  byId("backup-destination").textContent = backup.destination || "No destination selected";
  byId("backup-destination").title = backup.destination || "";
  byId("open-backup-destination").disabled = !hasDestination;
  byId("scan-backup-changes").disabled = !hasDestination || !backup.latest_snapshot || state.busy;
  byId("sync-backup").disabled = !hasDestination || state.busy;
  byId("sync-backup").textContent = backup.latest_snapshot ? "Sync backup" : "Create first backup";
  byId("backup-summary").textContent = backup.latest_snapshot
    ? `${backup.versions.length} version${backup.versions.length === 1 ? "" : "s"} · ${backup.scan.total || 0} changes`
    : hasDestination ? "Destination ready for the first backup version." : "Choose a backup destination.";
  renderInventory(state.data.inventory || {});
  renderChanges(backup.scan || {});
  renderVersions(backup.versions || []);
  renderNotification(backup);
}

// Runs one Backup action with explicit busy and diagnostic feedback.
async function runAction(action, payload, successMessage) {
  if (state.busy) return null;
  state.busy = true;
  setBusy(true);
  showMessage("");
  if (state.data) applyState(state.data);
  try {
    const data = await callNative(action, payload || {});
    if (data) applyState(data);
    if (successMessage) appendActivity(successMessage);
    return data;
  } catch (error) {
    const message = error.message || "Backup operation failed.";
    console.error(`Backup action failed: ${action}`, error);
    showMessage(message, true);
    appendActivity(message, true);
    throw error;
  } finally {
    state.busy = false;
    setBusy(false);
    if (state.data) applyState(state.data);
  }
}

// Loads non-scanning state whenever Backup Mode becomes visible.
async function activate() {
  await runAction("backupState", {}, "");
}

// Opens the in-app parent picker while leaving persistence to its explicit Apply action.
function chooseDestination() {
  const backup = state.data && state.data.backup ? state.data.backup : {};
  destinationModal.open(backup, applyState);
}

// Synchronizes modal-owned snapshot work with scheduled scans and page controls.
function setSelectionBusy(isBusy) {
  state.busy = isBusy;
  if (state.data) applyState(state.data);
}

// Runs an explicit selected-scope scan and records the start time used by focus scheduling.
async function scanChanges() {
  state.lastScanStarted = Date.now();
  await runAction("scanBackupChanges", {}, "Backup changes scanned");
}

// Opens mandatory source review and confirmation before any dated version transaction.
function syncBackup() {
  const backup = state.data && state.data.backup ? state.data.backup : {};
  selectionModal.open(backup, applyState, setSelectionBusy).catch(() => {});
}

// Runs one verified child replay while retaining the chosen parent and every child folder.
async function mergeDown() {
  if (!state.parentVersionPath || state.busy) return;
  state.mergeBusy = true;
  if (state.data) applyState(state.data);
  try {
    const data = await runAction("mergeDownBackupVersions", {
      parent_path: state.parentVersionPath,
    }, "");
    const childCount = Number(data.merged_children || 0);
    const message = data.cleanup_warning || (data.merge_no_changes
      ? "The selected parent already contains the newer Backup content."
      : `Merged ${childCount} newer Backup version${childCount === 1 ? "" : "s"} into the parent.`);
    showMessage(message, Boolean(data.cleanup_warning));
    appendActivity(message, Boolean(data.cleanup_warning));
  } finally {
    state.mergeBusy = false;
    if (state.data) applyState(state.data);
  }
}

// Keeps automatic scan timing stable across app restarts without replacing a newer in-session start time.
function latestScanStartedAt(backup) {
  const persisted = Date.parse(String((backup.scan || {}).scanned_at || ""));
  const persistedTime = Number.isFinite(persisted) ? persisted : 0;
  return Math.max(state.lastScanStarted, persistedTime);
}

// Runs a quiet scheduled scan only when configured, visible, idle, and due.
function scheduledScan() {
  const backup = state.data && state.data.backup ? state.data.backup : {};
  const pendingChanges = Boolean((backup.scan || {}).has_changes);
  const due = Date.now() - latestScanStartedAt(backup) >= SCAN_INTERVAL_MS;
  if (!backup.destination || !backup.latest_snapshot || pendingChanges
    || state.busy || document.hidden || !due) return;
  scanChanges().catch(() => {});
}

// Starts one in-app schedule and uses focus as a manual resumption checkpoint.
function startSchedule() {
  if (state.timer) return;
  state.timer = window.setInterval(scheduledScan, SCAN_INTERVAL_MS);
  window.addEventListener("focus", scheduledScan);
}

// Binds stable controls and delegated version opening after dynamic markup exists.
function bindEvents() {
  byId("choose-backup-destination").addEventListener("click", chooseDestination);
  byId("scan-backup-changes").addEventListener("click", () => scanChanges().catch(() => {}));
  byId("sync-backup").addEventListener("click", syncBackup);
  byId("open-backup-destination").addEventListener("click", () => {
    runAction("openBackupDestination", {}, "Backup destination opened").catch(() => {});
  });
  byId("backup-version-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-open-backup-version]");
    if (!button) return;
    runAction("openBackupVersion", { path: button.dataset.openBackupVersion }, "Backup version opened")
      .catch(() => {});
  });
  byId("backup-version-list").addEventListener("change", (event) => {
    if (!event.target.matches("[data-backup-parent-version]")) return;
    state.parentVersionPath = event.target.dataset.backupParentVersion;
    document.querySelectorAll(".backup-version-row").forEach((row) => {
      row.classList.toggle("selected-parent", row.contains(event.target));
    });
    const versions = state.data && state.data.backup ? state.data.backup.versions || [] : [];
    renderMergeAction(versions);
  });
  byId("merge-down-backup").addEventListener("click", () => mergeDown().catch(() => {}));
  document.querySelector('.tab-button[data-tab="backup"]').addEventListener("click", () => {
    activate().catch(() => {});
  });
}

// Installs the page before workspace and app tab binding, then begins non-blocking state recovery.
function init() {
  injectToolbarButton();
  injectPanel();
  bindEvents();
  startSchedule();
  activate().catch(() => {});
}

// Backup Mode has no transient preview resources, so leaving it preserves scan and notification state.
function deactivate() {}

window.GitDeskBackupMode = { activate, deactivate };

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
})();
