/*
  Local Mode permission gate for packaged macOS folder access.
*/

// Intercepts Local Mode entry so protected project folders are authorized before state refresh.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;

if (!nativeBridge || !renderHelpers) {
  throw new Error("GitDesk Local Mode permission dependencies did not load.");
}

const { appendActivity, setBusy, showMessage, showPanel } = renderHelpers;
const { callNative } = nativeBridge;
let permissionRequestRunning = false;
let startupPermissionRequested = false;
let previousMode = "repo";

// Reveals cached Local Mode content before privileged permission and filesystem work starts.
function previewLocalMode() {
  const workspaceMode = window.GitDeskWorkspaceMode;
  if (workspaceMode) {
    previousMode = workspaceMode.currentMode();
    workspaceMode.previewMode("local", true);
  }
}

// Restores the authoritative prior Repo or Media view when permission-gated activation fails.
function restorePreviousMode() {
  const workspaceMode = window.GitDeskWorkspaceMode;
  if (workspaceMode) {
    workspaceMode.previewMode(previousMode, true);
  }
}

// Returns whether a click target is trying to enter Local Mode.
function localModeTarget(target) {
  const tabButton = target.closest ? target.closest('.tab-button[data-tab="local"]') : null;
  const modeButton = target.closest ? target.closest('[data-workspace-mode-value="local"]') : null;
  return tabButton || modeButton;
}

// Creates a coded frontend error so invalid successful responses use the same diagnostic surfaces as bridge failures.
function activationError(message, code) {
  const error = new Error(message);
  error.code = code;
  return error;
}

// Applies a verified Local Mode response and rejects any state that would leave its page hidden in Repo Mode.
function applyPermissionResponse(data) {
  const workspaceMode = window.GitDeskWorkspaceMode;
  if (!workspaceMode || typeof workspaceMode.applyLocalResponse !== "function") {
    throw activationError("Local Mode could not open because its workspace controller did not load.",
      "LOCAL_MODE_UI_UNAVAILABLE");
  }
  if (!data || !data.settings || data.settings.workspace_mode !== "local") {
    throw activationError("Local Mode permissions completed, but the workspace was not activated.",
      "LOCAL_MODE_ACTIVATION_FAILED");
  }
  workspaceMode.applyLocalResponse(data);
  if (!workspaceMode.isLocalMode()) {
    throw activationError("Local Mode could not open because another workspace remained active.",
      "LOCAL_MODE_ACTIVATION_FAILED");
  }
  if (window.GitDeskProjectHubRender) {
    window.GitDeskProjectHubRender.syncSharedSettings(data.settings);
  }
}

// Shows cached Local Mode immediately, then reconciles it with verified state from Python.
async function requestLocalModeAccess(options = {}) {
  if (permissionRequestRunning) {
    return;
  }

  previewLocalMode();
  permissionRequestRunning = true;
  setBusy(true);
  showMessage("Opening Local Mode…");
  try {
    const data = await callNative("requestLocalModePermissions", {});
    applyPermissionResponse(data);
    showPanel("local");
    showMessage("");
    if (!options.quiet) {
      appendActivity("Local Mode permissions verified");
    }
  } catch (error) {
    restorePreviousMode();
    let message = error.message || "Local Mode permission request failed.";
    if (error.code === "LOCAL_PERMISSION_DENIED") {
      message += " After changing macOS settings, choose Local Mode again to retry.";
    }
    console.error("Local Mode entry failed", error);
    showMessage(message, true);
    appendActivity(message, true);
    if (window.GitDeskDebug) {
      window.GitDeskDebug.open();
    }
  } finally {
    permissionRequestRunning = false;
    setBusy(false);
  }
}

// Captures entry from Repo Mode while allowing ordinary Local tab navigation after activation.
function handleClick(event) {
  if (!localModeTarget(event.target)) {
    return;
  }
  const workspaceMode = window.GitDeskWorkspaceMode;
  if (workspaceMode && workspaceMode.isLocalMode()) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  event.stopImmediatePropagation();
  requestLocalModeAccess();
}

// Verifies saved project access on startup when the app opens directly into Local Mode.
function applySettings(settings) {
  if (!settings || settings.workspace_mode !== "local" || startupPermissionRequested) {
    return false;
  }
  startupPermissionRequested = true;
  requestLocalModeAccess({ quiet: true });
  return true;
}

// Binds a capture listener so Local Mode cannot render before permission handling.
function init() {
  document.addEventListener("click", handleClick, true);
}

// Runs initialization once the document can receive delegated click events.
function onReady(callback) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", callback);
    return;
  }
  callback();
}

window.GitDeskLocalPermissions = { applySettings, requestLocalModeAccess };
onReady(init);
})();
