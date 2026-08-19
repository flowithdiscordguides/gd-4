/*
  GitDesk frontend controller. It owns UI state and sends all privileged work to Python.
*/

// Keeps controller state private while using explicit frontend APIs published by earlier scripts.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const accountManager = window.GitDeskAccounts;
const repositoryManager = window.GitDeskRepositories;
const overviewManager = window.GitDeskOverview;
const aiSkillsManager = window.GitDeskAISkills;
const pagesManager = window.GitDeskPages;
const actionsManager = window.GitDeskActions;
const releasesManager = window.GitDeskReleases;
const workspaceMode = window.GitDeskWorkspaceMode;
const localPermissions = window.GitDeskLocalPermissions;
const themeSettings = window.GitDeskThemeSettings;
const editorSettings = window.GitDeskEditorSettings;
const actionJingles = window.GitDeskActionJingles;

if (!nativeBridge || !renderHelpers || !accountManager || !repositoryManager) {
  throw new Error("GitDesk frontend dependencies did not load.");
}
if (!overviewManager || !aiSkillsManager || !pagesManager || !actionsManager || !releasesManager
    || !themeSettings || !editorSettings || !actionJingles) {
  throw new Error("GitDesk frontend dependencies did not load.");
}

const { callNative } = nativeBridge;
const {
  appendActivity,
  byId,
  renderBranches,
  setBusy,
  setText,
  setValue,
  showMessage,
  showPanel,
} = renderHelpers;

const state = {
  settings: {},
  branches: null,
  autoRefreshTimer: null,
  autoRefreshRunning: false,
  foregroundActionCount: 0,
};

// Returns the active repository path from the managed repository picker.
function repositoryPayload() {
  return repositoryManager.payload();
}

// Returns the GitHub owner/repo pair from settings inputs.
function githubPayload() {
  const payload = repositoryPayload();
  payload.owner = byId("github-owner").value.trim();
  payload.repo = byId("github-repo").value.trim();
  return payload;
}

// Copies extra request fields onto a base payload without using object spread syntax.
function withFields(basePayload, extraFields) {
  Object.keys(extraFields).forEach((key) => {
    basePayload[key] = extraFields[key];
  });
  return basePayload;
}

// Wraps native calls with consistent busy, message, and activity handling.
async function runAction(action, payload, successMessage, options = {}) {
  const quiet = Boolean(options.quiet);
  if (!quiet) {
    state.foregroundActionCount += 1;
    setBusy(true);
    showMessage("");
  }

  try {
    const data = await callNative(action, payload);
    if (successMessage && !quiet) {
      appendActivity(successMessage);
    }
    return data;
  } catch (error) {
    const message = error.message || "Operation failed.";
    if (!quiet) {
      console.error(`Native action failed: ${action}`, error);
      showMessage(message, true);
      appendActivity(message, true);
    }
    throw error;
  } finally {
    if (!quiet) {
      state.foregroundActionCount = Math.max(0, state.foregroundActionCount - 1);
      setBusy(false);
    }
  }
}

// Applies settings returned by Python to the form controls and state object.
function applySettings(settings) {
  state.settings = settings || {};
  setValue("github-owner", state.settings.github_owner);
  setValue("github-repo", state.settings.github_repo);
  repositoryManager.applySettings(state.settings);
  themeSettings.applySettings(state.settings);
  editorSettings.applySettings(state.settings);
  const localModeDeferred = localPermissions ? localPermissions.applySettings(state.settings) : false;
  if (workspaceMode && !localModeDeferred) {
    workspaceMode.applySettings(state.settings);
  }
  actionsManager.reset();
  pagesManager.syncHistoryAvailability(state.branches);
}

// Applies a status payload to the Overview panel.
function applyStatus(status) {
  overviewManager.applyStatus(status);
}

// Stores branch metadata and renders the Branches panel from one app-owned path.
function applyBranches(branches) {
  state.branches = branches;
  renderBranches(branches);
  pagesManager.syncHistoryAvailability(branches);
}

// Opens a successfully mirrored repository destination under its owning account with fresh local Git state.
function handleSyncedDestination(event) {
  const data = event.detail || {};
  if (!data.settings || !data.status || !data.branches) return;
  accountManager.apply(data.auth);
  applySettings(data.settings);
  overviewManager.reset();
  applyStatus(data.status);
  applyBranches(data.branches);
  showPanel("overview");
  const label = data.destination_label || "Destination repository";
  appendActivity(`${label} opened in Repo Mode`);
}

// Clears local selections and repository-dependent panels when no account repo is selected.
function resetRepositoryView() {
  overviewManager.reset();
  applyBranches(null);
}

// Refreshes status while preserving selected files that still exist in the new status result.
async function refreshStatus(options = {}) {
  const message = options.quiet ? "" : "Status refreshed";
  const status = await runAction("refreshStatus", repositoryPayload(), message, options);
  applyStatus(status);
}

// Returns whether automatic status refresh has a concrete repository to inspect.
function canAutoRefreshStatus() {
  const repoMode = !workspaceMode || workspaceMode.isRepoMode();
  return repoMode && Boolean(repositoryManager.activePath && repositoryManager.activePath());
}

// Refreshes status without Activity noise so external file edits appear while the app is open.
async function refreshStatusQuietly() {
  if (!canAutoRefreshStatus() || state.autoRefreshRunning || state.foregroundActionCount > 0 || document.hidden) {
    return;
  }
  state.autoRefreshRunning = true;
  try {
    await refreshStatus({ quiet: true });
  } catch (error) {
    // Manual refreshes still surface errors; quiet polling should not spam Activity.
  } finally {
    state.autoRefreshRunning = false;
  }
}

// Starts lightweight refresh triggers for files changed by editors outside GitDesk.
function startAutoStatusRefresh() {
  if (state.autoRefreshTimer) {
    return;
  }
  state.autoRefreshTimer = window.setInterval(refreshStatusQuietly, 5000);
  window.addEventListener("focus", refreshStatusQuietly);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      refreshStatusQuietly();
    }
  });
}

// Loads branches from Python and renders the branch management panel.
async function refreshBranches() {
  const branches = await runAction("listBranches", repositoryPayload(), "Branches refreshed");
  applyBranches(branches);
}

// Clones a GitHub repository, opens it, and switches into the Overview workflow.
async function cloneRepository(event) {
  event.preventDefault();
  const payload = {
    url: byId("clone-url").value,
    parent_path: byId("clone-parent-path").value,
    folder_name: byId("clone-folder-name").value,
    use_saved_token: byId("clone-use-token").checked,
    account_login: accountManager.activeLogin(),
  };
  const data = await runAction("cloneRepository", payload, "Repository cloned");
  accountManager.apply(data.auth);
  applySettings(data.settings);
  overviewManager.reset();
  applyStatus(data.status);
  applyBranches(data.branches);
  setText("clone-summary", `Cloned ${data.repository.github_owner}/${data.repository.github_repo}`);
  setText("clone-target-preview", data.repository.path);
  showPanel("overview");
}

// Applies settings returned by an account switch and refreshes the active account's repository.
function handleAccountSettings(settings) {
  applySettings(settings);
  if (!repositoryManager.activePath()) {
    resetRepositoryView();
    return;
  }
  overviewManager.reset();
  refreshStatus()
    .then(refreshBranches)
    .catch(() => {});
}

// Builds the visible clone target path from the selected parent folder and local folder name.
function cloneTargetPath() {
  const parentPath = byId("clone-parent-path").value.trim();
  const folderName = byId("clone-folder-name").value.trim();
  if (!parentPath) {
    return "Not selected";
  }
  if (!folderName) {
    return parentPath;
  }
  const lastCharacter = parentPath.charAt(parentPath.length - 1);
  const usesBackslash = parentPath.indexOf("\\") >= 0 && parentPath.indexOf("/") < 0;
  const separator = lastCharacter === "/" || lastCharacter === "\\" ? "" : (usesBackslash ? "\\" : "/");
  return `${parentPath}${separator}${folderName}`;
}

// Refreshes the clone target preview as the destination controls change.
function updateCloneTargetPreview() {
  setText("clone-target-preview", cloneTargetPath());
}

// Opens a native destination-folder picker and writes the selected parent path into the clone form.
async function chooseCloneDestination() {
  const data = await runAction("chooseCloneDestination", {
    initial_path: byId("clone-parent-path").value,
  });
  if (!data.path) return;
  setValue("clone-parent-path", data.path);
  updateCloneTargetPreview();
  appendActivity("Destination folder selected");
}

// Saves owner/repo settings without touching the GitHub token.
async function saveGithubSettings(event) {
  event.preventDefault();
  const data = await runAction("saveSettings", githubPayload(), "GitHub repository saved");
  applySettings(data.settings);
}

// Checks out the branch attached to the clicked branch row button.
async function checkoutBranch(branchName) {
  const payload = withFields(repositoryPayload(), { branch: branchName });
  const data = await runAction("checkoutBranch", payload, "Branch checked out");
  applyBranches(data.branches);
  applyStatus(data.status);
}

// Creates a new branch from the current HEAD and checks it out.
async function createBranch() {
  const input = byId("new-branch-name");
  const payload = withFields(repositoryPayload(), { branch: input.value });
  const data = await runAction("createBranch", payload, "Branch created");
  input.value = "";
  applyBranches(data.branches);
  applyStatus(data.status);
}

// Handles checkout button clicks from the delegated branches list.
function handleBranchClick(event) {
  const button = event.target.closest(".checkout-branch");
  if (!button) {
    return;
  }
  checkoutBranch(button.dataset.branch);
}

// Wires all static controls after the DOM is ready.
function bindEvents() {
  actionJingles.bind(runAction);
  accountManager.bind(runAction, handleAccountSettings, { githubPayload });
  overviewManager.bind({
    runAction,
    repositoryPayload,
    renderBranches: applyBranches,
  });
  aiSkillsManager.bind(runAction);
  pagesManager.bind({
    runAction,
    repositoryPayload,
    githubPayload,
    applyStatus,
    renderBranches: applyBranches,
    currentBranch() {
      return state.branches && state.branches.current ? state.branches.current : "";
    },
  });
  actionsManager.bind({ runAction, githubPayload });
  releasesManager.bind({ runAction, githubPayload });
  repositoryManager.bind({
    runAction,
    applySettings,
    applyStatus,
    renderBranches: applyBranches,
    resetSelections() {
      overviewManager.reset();
    },
  });
  document.querySelectorAll(".tab-button[data-tab]").forEach((button) => {
    button.addEventListener("click", () => showPanel(button.dataset.tab));
  });
  byId("refresh-status").addEventListener("click", refreshStatus);
  byId("clone-form").addEventListener("submit", cloneRepository);
  byId("choose-clone-parent").addEventListener("click", chooseCloneDestination);
  byId("clone-parent-path").addEventListener("input", updateCloneTargetPreview);
  byId("clone-folder-name").addEventListener("input", updateCloneTargetPreview);
  byId("refresh-branches").addEventListener("click", refreshBranches);
  byId("create-branch").addEventListener("click", createBranch);
  byId("branches-list").addEventListener("click", handleBranchClick);
  byId("github-form").addEventListener("submit", saveGithubSettings);
  window.addEventListener("gitdesk:sync-destination-ready", handleSyncedDestination);
  startAutoStatusRefresh();
}

// Loads initial settings and token state from Python before the user interacts with the app.
async function bootstrap() {
  bindEvents();
  try {
    const data = await runAction("bootstrap", {}, "Application ready");
    accountManager.apply(data.auth);
    actionJingles.applySettings(data.action_jingles);
    applySettings(data.settings);
    const repoModeActive = state.settings.workspace_mode === "repo" && (!workspaceMode || workspaceMode.isRepoMode());
    if (repoModeActive) {
      actionsManager.refreshOnLoad();
    }
    setText("settings-location", data.settings_location || "Not loaded");
    if (repoModeActive && repositoryManager.activePath()) {
      await refreshStatus();
      await refreshBranches();
    } else {
      resetRepositoryView();
    }
  } catch (error) {
    showMessage("Startup failed. Check DevTools for details.", true);
  }
}

// Runs a callback immediately when the document is already parsed, or waits for parsing to finish.
function onDocumentReady(callback) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", callback);
    return;
  }
  callback();
}

onDocumentReady(bootstrap);
})();
