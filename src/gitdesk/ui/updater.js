/*
  Settings-panel updater controller for checking GitDesk releases and installing matching updates.
*/

// Keeps updater UI behavior isolated from the main app controller while sharing bridge/render helpers.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;

if (!nativeBridge || !renderHelpers) {
  throw new Error("GitDesk updater dependencies did not load.");
}

const { appendActivity, byId, setBusy, setText, showMessage } = renderHelpers;
const { callNative } = nativeBridge;
let checkedUpdateVersion = "";

// Creates the System settings card dynamically so the static HTML file does not need to grow.
function createUpdaterCard() {
  if (document.getElementById("settings-updater-card")) {
    return;
  }

  const settingsMount = document.getElementById("settings-system-content")
    || document.querySelector("#panel-settings .settings-grid");
  if (!settingsMount) {
    return;
  }

  const card = document.createElement("div");
  card.id = "settings-updater-card";
  card.className = "settings-block settings-updater-card";
  card.innerHTML = `
    <label>GitDesk updates</label>
    <p id="updater-summary" class="row-meta" role="status" aria-live="polite">Not checked yet</p>
    <div class="button-row settings-updater-actions">
      <button id="check-gitdesk-update" type="button">Check for updates</button>
      <button id="install-gitdesk-update" class="primary" type="button" disabled>Install update</button>
    </div>
    <div id="updater-details" class="updater-details" aria-live="polite"></div>
  `;
  settingsMount.append(card);
}

// Returns both action controls so each workflow can enforce the same check-before-install gate.
function updaterButtons() {
  return {
    check: byId("check-gitdesk-update"),
    install: byId("install-gitdesk-update"),
  };
}

// Keeps the installation action locked unless the current session has checked a compatible newer release.
function setCheckedUpdate(versionValue) {
  checkedUpdateVersion = String(versionValue || "").trim();
  const { install } = updaterButtons();
  install.disabled = !checkedUpdateVersion;
}

// Replaces updater detail rows using textContent so release data cannot inject markup.
function renderDetailRows(rows) {
  const detailElement = byId("updater-details");
  detailElement.textContent = "";
  rows.forEach((row) => {
    const rowElement = document.createElement("p");
    rowElement.className = "row-meta";
    rowElement.textContent = row;
    detailElement.append(rowElement);
  });
}

// Builds a consistent version label for current and latest release details.
function versionLabel(currentVersion, latestVersion) {
  return `Current ${currentVersion || "unknown"} - latest ${latestVersion || "unknown"}`;
}

// Renders the no-update path after the backend confirms the release tag is not newer.
function renderCurrentResult(data) {
  setText("updater-summary", "GitDesk is up to date.");
  renderDetailRows([
    versionLabel(data.current_version, data.latest_version),
    data.target && data.target.label ? data.target.label : "Current platform",
    data.release_source ? `Public releases: ${data.release_source}` : "Public GitDesk releases",
  ]);
}

// Renders the check-only result and explains whether this platform can perform the automatic install step.
function renderAvailableResult(data) {
  const target = data.target || {};
  const latestVersion = data.latest_version || "the latest update";
  const summary = data.install_supported
    ? `${latestVersion} is ready to install.`
    : `${latestVersion} is available for manual installation.`;
  setText("updater-summary", summary);
  renderDetailRows([
    versionLabel(data.current_version, data.latest_version),
    target.label || "Current platform",
    data.install_supported
      ? "Install update is now available."
      : "Automatic install and restart are currently available only on macOS.",
    data.release_source ? `Public releases: ${data.release_source}` : "Public GitDesk releases",
  ]);
}

// Renders the automatic install path after the helper has been staged successfully.
function renderRestartingResult(data) {
  const download = data.download || {};
  const install = data.install || {};
  const target = data.target || {};
  setText("updater-summary", `Installing ${data.latest_version || "the latest update"} and restarting.`);
  renderDetailRows([
    target.label || "Current platform",
    download.filename ? `File: ${download.filename}` : "Update downloaded",
    install.target_app ? `Relaunching from: ${install.target_app}` : "Relaunching GitDesk",
    install.helper_log ? `Helper log: ${install.helper_log}` : "Install helper started",
  ]);
}

// Renders the backend result shape returned by the updater action.
function renderCheckResult(data) {
  const result = data || {};
  if (result.status === "current") {
    setCheckedUpdate("");
    renderCurrentResult(result);
    return "GitDesk is up to date";
  }
  if (result.status === "available") {
    setCheckedUpdate(result.install_supported ? result.latest_version : "");
    renderAvailableResult(result);
    return `GitDesk update ${result.latest_version || "available"}`;
  }
  setText("updater-summary", "Update check finished.");
  renderDetailRows([versionLabel(result.current_version, result.latest_version)]);
  setCheckedUpdate("");
  return "GitDesk update check finished";
}

// Renders expected updater failures such as unsupported OS or no visible published release.
function renderUpdaterError(error) {
  const message = error && error.message ? error.message : "Update check failed.";
  setText("updater-summary", message);
  renderDetailRows([error && error.code ? `Code: ${error.code}` : "Code: UPDATER_FAILED"]);
}

// Checks the public release repository without downloading or staging any update artifact.
async function checkGitDeskUpdate() {
  const buttons = updaterButtons();
  buttons.check.disabled = true;
  buttons.install.disabled = true;
  setBusy(true);
  showMessage("");
  setText("updater-summary", "Checking public releases.");
  renderDetailRows([]);

  try {
    const data = await callNative("checkGitDeskUpdate", {});
    appendActivity(renderCheckResult(data));
  } catch (error) {
    console.error("GitDesk update check failed", error);
    setCheckedUpdate("");
    renderUpdaterError(error);
    showMessage(error.message || "Update check failed.", true);
    appendActivity(error.message || "Update check failed.", true);
  } finally {
    buttons.check.disabled = false;
    setBusy(false);
  }
}

// Installs only the exact public release tag returned by the successful check in this UI session.
async function installGitDeskUpdate() {
  const buttons = updaterButtons();
  if (!checkedUpdateVersion) {
    setText("updater-summary", "Check for updates before installing.");
    return;
  }

  let restartStarted = false;
  buttons.check.disabled = true;
  buttons.install.disabled = true;
  setBusy(true);
  showMessage("");
  setText("updater-summary", `Preparing ${checkedUpdateVersion} for installation.`);
  renderDetailRows([]);

  try {
    const data = await callNative("installGitDeskUpdate", { expected_version: checkedUpdateVersion });
    restartStarted = data && data.status === "restarting";
    if (restartStarted) {
      renderRestartingResult(data);
      showMessage("GitDesk will close and reopen.");
      appendActivity("GitDesk update installing and restarting");
    }
  } catch (error) {
    console.error("GitDesk update install failed", error);
    if (error && ["UPDATER_CHECK_REQUIRED", "UPDATER_RELEASE_CHANGED"].includes(error.code)) {
      setCheckedUpdate("");
    }
    renderUpdaterError(error);
    showMessage(error.message || "Update installation failed.", true);
    appendActivity(error.message || "Update installation failed.", true);
  } finally {
    if (!restartStarted) {
      buttons.check.disabled = false;
      buttons.install.disabled = !checkedUpdateVersion;
      setBusy(false);
    }
  }
}

// Wires the separate check and install controls after their Settings card has been injected.
function bindUpdater() {
  createUpdaterCard();
  const buttons = updaterButtons();
  if (!buttons.check || !buttons.install) {
    return;
  }
  buttons.check.addEventListener("click", checkGitDeskUpdate);
  buttons.install.addEventListener("click", installGitDeskUpdate);
}

// Runs the updater setup after static Settings markup exists, matching the app controller startup pattern.
function onDocumentReady(callback) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", callback);
    return;
  }
  callback();
}

onDocumentReady(bindUpdater);
})();
