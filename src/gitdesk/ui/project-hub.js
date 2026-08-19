/*
  Project Hub workflow controller.
*/

// Keeps Project Hub workflows separate from the main app controller.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const hubUI = window.GitDeskProjectHubUI;
const hubRender = window.GitDeskProjectHubRender;
const activityTracker = window.GitDeskActivityTracker;

if (!nativeBridge || !renderHelpers || !hubUI || !hubRender || !activityTracker) {
  throw new Error("GitDesk Project Hub dependencies did not load.");
}

const { appendActivity, byId, setBusy, setValue, showMessage } = renderHelpers;
const { callNative } = nativeBridge;
const state = {
  settings: {},
  hub: null,
  scan: null,
  branches: null,
  stashes: null,
  tags: null,
  workflowRuns: null,
};

// Runs a native action with Project Hub busy, Activity, and error feedback.
async function runAction(action, payload, successMessage) {
  setBusy(true);
  showMessage("");
  try {
    const data = await callNative(action, payload || {});
    if (successMessage) appendActivity(successMessage);
    return data;
  } catch (error) {
    const message = error.message || "Project Hub operation failed.";
    console.error(`Project Hub action failed: ${action}`, error);
    showMessage(message, true);
    appendActivity(message, true);
    throw error;
  } finally {
    setBusy(false);
  }
}

// Applies a backend response carrying Project Hub settings and re-renders the panel.
function applyHubResponse(data) {
  if (data && data.settings) {
    state.settings = data.settings;
    hubRender.syncSharedSettings(data.settings);
  }
  if (data && data.hub) state.hub = data.hub;
  hubRender.render(state);
}

// Returns the active local version path from render helpers.
function activeVersionPath() {
  return hubRender.activeVersionPath(state);
}

// Shows one tab inside the New Project modal while hiding the other workflow.
function showNewProjectTab(tabName) {
  const activeTab = tabName === "import" ? "import" : "create";
  document.querySelectorAll("[data-new-project-tab]").forEach((button) => {
    const isActive = button.dataset.newProjectTab === activeTab;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", String(isActive));
  });
  document.querySelectorAll("[data-new-project-pane]").forEach((pane) => {
    const isActive = pane.dataset.newProjectPane === activeTab;
    pane.classList.toggle("active", isActive);
    pane.hidden = !isActive;
  });
  const createAction = document.getElementById("create-local-project");
  // The create action sits in the header, but it should behave like part of the Create tab.
  if (createAction) {
    createAction.hidden = activeTab !== "create";
  }
}

// Opens the shared New Project modal on the requested create/import tab.
function openNewProjectModal(tabName) {
  showNewProjectTab(tabName);
  byId("new-project-modal").hidden = false;
  const active = document.querySelector(`[data-new-project-tab="${tabName === "import" ? "import" : "create"}"]`);
  if (active) active.focus();
}

// Closes the New Project modal without discarding any typed form values.
function closeNewProjectModal() {
  byId("new-project-modal").hidden = true;
}

// Reloads the complete Project Hub state.
async function refreshHub() {
  const data = await runAction("projectHubState", {}, "Project Hub refreshed");
  applyHubResponse(data);
  await activityTracker.refresh(false);
}

// Chooses a folder and scans it for import metadata.
async function chooseImportFolder() {
  const data = await runAction(
    "chooseExistingProject",
    { initial_path: byId("hub-import-path").value },
    "Project folder selected",
  );
  if (data.path) {
    setValue("hub-import-path", data.path);
    await scanImportFolder();
  }
}

// Scans an existing project folder without changing saved settings.
async function scanImportFolder() {
  state.scan = await runAction(
    "scanExistingProject",
    { project_path: byId("hub-import-path").value },
    "Project folder scanned",
  );
  hubRender.renderImportScan(state);
}

// Imports a scanned folder into Local Mode and refreshes the hub.
async function importProject() {
  const data = await runAction(
    "importExistingProject",
    { project_path: byId("hub-import-path").value },
    "Project imported",
  );
  state.scan = null;
  applyHubResponse(data);
  closeNewProjectModal();
}

// Refreshes recent GitHub Actions runs for the active managed repository.
async function refreshBuilds() {
  const github = state.hub && state.hub.github ? state.hub.github : {};
  const repository = github.repository || {};
  state.workflowRuns = await runAction("listWorkflowRuns", {
    owner: repository.owner || github.owner || "",
    repo: repository.repo || github.repo || "",
  }, "Builds refreshed");
  hubRender.renderBuilds(state);
}

// Refreshes branch, stash, and tag data for the active version repository.
async function refreshGitBasics() {
  const payload = { path: activeVersionPath() };
  state.branches = await runAction("listBranches", payload, "");
  state.stashes = await runAction("listStashes", payload, "");
  state.tags = await runAction("listTags", payload, "");
  hubRender.renderGitBasics(state);
  appendActivity("Git basics refreshed");
}

// Creates a safety stash, refreshes Project Hub state, and reloads stash controls.
async function createSafetySnapshot() {
  const data = await runAction(
    "createSafetyStash",
    { path: activeVersionPath(), reason: "project hub" },
    "Safety snapshot created",
  );
  applyHubResponse(data);
  await refreshGitBasics();
}

// Applies the selected stash without dropping it.
async function applySafetySnapshot() {
  await runAction(
    "applyStash",
    { path: activeVersionPath(), stash: byId("hub-stash-select").value },
    "Safety snapshot applied",
  );
  await refreshGitBasics();
}

// Renames the selected branch for the active version repository.
async function renameBranch() {
  const data = await runAction("renameBranch", {
    path: activeVersionPath(),
    old_name: byId("hub-branch-select").value,
    new_name: byId("hub-branch-new").value,
  }, "Branch renamed");
  state.branches = data.branches;
  hubRender.renderGitBasics(state);
}

// Deletes the selected branch for the active version repository.
async function deleteBranch() {
  const data = await runAction("deleteBranch", {
    path: activeVersionPath(),
    branch: byId("hub-branch-select").value,
    force: byId("hub-branch-force").checked,
  }, "Branch deleted");
  state.branches = data.branches;
  hubRender.renderGitBasics(state);
}

// Exports non-secret Project Hub metadata into the backup textarea.
async function exportBackup() {
  const data = await runAction("exportProjectHubSettings", {}, "Project Hub metadata exported");
  setValue("hub-backup-json", data.json || "");
}

// Imports a Project Hub metadata backup from the backup textarea.
async function importBackup() {
  const data = await runAction(
    "importProjectHubSettings",
    { json: byId("hub-backup-json").value },
    "Project Hub metadata imported",
  );
  applyHubResponse(data);
}

// Removes missing project records while leaving existing folders untouched.
async function repairProjects() {
  const data = await runAction("repairMissingProjects", {}, "Project index repaired");
  applyHubResponse(data);
}

// Handles delegated clicks for the modal trigger, tab strip, backdrop, and close button.
function handleNewProjectClick(event) {
  if (event.target.closest("#open-new-project-modal")) {
    openNewProjectModal("create");
    return;
  }
  const tab = event.target.closest("[data-new-project-tab]");
  if (tab) {
    showNewProjectTab(tab.dataset.newProjectTab);
    return;
  }
  if (event.target.id === "close-new-project-modal" || event.target.id === "new-project-modal") {
    closeNewProjectModal();
  }
}

// Lets keyboard users dismiss the modal without invoking either project workflow.
function handleNewProjectKeydown(event) {
  if (event.key === "Escape" && !byId("new-project-modal").hidden) {
    closeNewProjectModal();
  }
}

// Binds Project Hub controls after injected markup exists.
function bindEvents() {
  document.addEventListener("click", handleNewProjectClick);
  document.addEventListener("keydown", handleNewProjectKeydown);
  byId("project-hub-refresh").addEventListener("click", refreshHub);
  byId("hub-choose-import").addEventListener("click", chooseImportFolder);
  byId("hub-scan-import").addEventListener("click", scanImportFolder);
  byId("hub-import-project").addEventListener("click", importProject);
  byId("hub-refresh-builds").addEventListener("click", refreshBuilds);
  byId("hub-git-refresh").addEventListener("click", refreshGitBasics);
  byId("hub-stash-create").addEventListener("click", createSafetySnapshot);
  byId("hub-stash-apply").addEventListener("click", applySafetySnapshot);
  byId("hub-branch-rename").addEventListener("click", renameBranch);
  byId("hub-branch-delete").addEventListener("click", deleteBranch);
  byId("hub-export-settings").addEventListener("click", exportBackup);
  byId("hub-import-settings").addEventListener("click", importBackup);
  byId("hub-repair-projects").addEventListener("click", repairProjects);
}

// Initializes dynamic markup, events, and first Project Hub state load.
function init() {
  hubUI.injectUI();
  activityTracker.bind();
  bindEvents();
  callNative("projectHubState", {}).then(applyHubResponse).catch(() => {});
}

// Runs initialization when static HTML has been parsed.
function onReady(callback) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", callback);
    return;
  }
  callback();
}

window.GitDeskProjectHub = { refresh: refreshHub };
window.GitDeskProjectHubModal = { close: closeNewProjectModal, open: openNewProjectModal };
onReady(init);
})();
