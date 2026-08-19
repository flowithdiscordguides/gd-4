/*
  Top-level Repo, Local, Media, and Backup workspace-mode orchestration.
*/

// Owns mode persistence and presentation while feature controllers own their own state.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const localMode = window.GitDeskLocalMode;
const mediaMode = window.GitDeskMediaMode;
const backupMode = window.GitDeskBackupMode;

if (!nativeBridge || !renderHelpers || !localMode || !mediaMode || !backupMode) {
  throw new Error("GitDesk workspace-mode dependencies did not load.");
}

const { callNative } = nativeBridge;
const { appendActivity, setBusy, showMessage, showPanel } = renderHelpers;
let mode = "repo";

// Normalizes persisted or requested modes to one of the four supported workspace values.
function cleanMode(value) {
  return ["repo", "local", "media", "backup"].includes(value) ? value : "repo";
}

// Inserts the four-way global mode switch after the application brand.
function injectModeSwitch() {
  if (document.getElementById("workspace-mode-switch")) return;
  document.querySelector(".brand-block").insertAdjacentHTML("afterend", `
    <div id="workspace-mode-switch" class="workspace-mode-switch" role="group" aria-label="Workspace mode">
      <button type="button" data-workspace-mode-value="repo">Repo Mode</button>
      <button type="button" data-workspace-mode-value="local">Local Mode</button>
      <button type="button" data-workspace-mode-value="media">Media Mode</button>
      <button type="button" data-workspace-mode-value="backup">Backup Mode</button>
    </div>
  `);
}

// Applies mode visibility immediately and optionally navigates to that mode's primary page.
function previewMode(value, switchPanel) {
  const nextMode = cleanMode(value);
  mode = nextMode;
  if (nextMode !== "media") mediaMode.deactivate();
  if (nextMode !== "backup") backupMode.deactivate();
  document.documentElement.setAttribute("data-workspace-mode", nextMode);
  document.querySelectorAll("[data-workspace-mode-value]").forEach((button) => {
    button.classList.toggle("active", button.dataset.workspaceModeValue === nextMode);
  });
  if (switchPanel) {
    showPanel({ repo: "overview", local: "local", media: "media", backup: "backup" }[nextMode]);
  }
}

// Returns the exact current mode so repository polling never treats Media Mode as Repo Mode.
function currentMode() {
  return mode;
}

// Returns whether repository-only polling and startup work are permitted.
function isRepoMode() {
  return mode === "repo";
}

// Returns whether Local Mode is already active and may bypass its permission-entry gate.
function isLocalMode() {
  return mode === "local";
}

// Saves a non-Local mode immediately and rolls presentation back when persistence fails.
async function saveMode(value) {
  const nextMode = cleanMode(value);
  const previousMode = mode;
  // Re-selecting an active mode is navigation and must not trigger another disk write or filesystem scan.
  if (nextMode === previousMode) {
    previewMode(nextMode, true);
    if (nextMode === "media") mediaMode.activate();
    if (nextMode === "backup") backupMode.activate();
    return;
  }
  previewMode(nextMode, true);
  if (nextMode === "media") mediaMode.activate();
  if (nextMode === "backup") backupMode.activate();
  setBusy(true);
  showMessage("");
  try {
    const data = await callNative("saveWorkspaceMode", { mode: nextMode });
    const savedMode = cleanMode((data.settings || {}).workspace_mode);
    previewMode(savedMode, true);
    localMode.applySettings(data.settings || {});
    appendActivity(`${savedMode[0].toUpperCase()}${savedMode.slice(1)} Mode`);
  } catch (error) {
    previewMode(previousMode, true);
    const message = error.message || "Workspace mode could not be saved.";
    console.error("Workspace mode save failed", error);
    showMessage(message, true);
    appendActivity(message, true);
  } finally {
    setBusy(false);
  }
}

// Applies bootstrap settings without performing the Local permission gate's privileged refresh.
function applySettings(settings) {
  localMode.applySettings(settings);
  const savedMode = cleanMode((settings || {}).workspace_mode);
  previewMode(savedMode, ["media", "backup"].includes(savedMode));
  if (savedMode === "media") mediaMode.activate();
  if (savedMode === "backup") backupMode.activate();
}

// Applies permission-verified Local state and activates its page.
function applyLocalResponse(data) {
  localMode.applyLocalResponse(data);
  previewMode("local", true);
}

// Routes global switch and mode-specific toolbar destinations.
function handleClick(event) {
  const switchButton = event.target.closest("[data-workspace-mode-value]");
  const tabButton = event.target.closest(
    '.tab-button[data-tab="local"], .tab-button[data-tab="media"], .tab-button[data-tab="backup"]',
  );
  const requestedMode = switchButton
    ? switchButton.dataset.workspaceModeValue
    : (tabButton ? tabButton.dataset.tab : "");
  if (!requestedMode) return;
  saveMode(requestedMode).catch(() => {});
}

// Initializes global mode controls after Local and Media panels have been injected.
function init() {
  injectModeSwitch();
  document.getElementById("workspace-mode-switch").addEventListener("click", handleClick);
  document.querySelector(".toolbar").addEventListener("click", handleClick);
  previewMode(mode, false);
}

window.GitDeskWorkspaceMode = {
  applyLocalResponse,
  applySettings,
  currentMode,
  isLocalMode,
  isRepoMode,
  previewMode,
  refreshLocalState: localMode.refreshState,
  refreshSyncAvailability: localMode.refreshSyncAvailability,
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
})();
