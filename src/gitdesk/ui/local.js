/*
  Local Mode controller for physical project folders and version duplication.
*/

// Coordinates Local Mode backend actions while local-render.js owns markup and rendering.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const localRender = window.GitDeskLocalRender;
const localOrganizer = window.GitDeskLocalOrganizer;
const localFeaturePicker = window.GitDeskLocalFeaturePicker;
const localProjectIdentity = window.GitDeskLocalProjectIdentity;
const localProjectSelection = window.GitDeskLocalProjectSelection;
const localCompare = window.GitDeskLocalCompare;
const localControls = window.GitDeskLocalControls;
const localVersionActions = window.GitDeskLocalVersionActions;
const sharedResourceManager = window.GitDeskSharedResources;
const localVersionDelete = window.GitDeskLocalVersionDelete;
const editorSettings = window.GitDeskEditorSettings;

if (!nativeBridge || !renderHelpers || !localRender || !localOrganizer || !localFeaturePicker || !localProjectIdentity
    || !localProjectSelection
    || !localCompare || !localControls || !localVersionActions
    || !sharedResourceManager || !localVersionDelete || !editorSettings) {
  throw new Error("GitDesk Local Mode dependencies did not load.");
}

const {
  appendActivity,
  byId,
  setBusy,
  setValue,
  showMessage,
} = renderHelpers;
const { callNative } = nativeBridge;
const state = {
  settings: {},
  local: { projects: [], active_project: "", active_feature: "", active_version: "", cleanup_paths: [] },
  resources: [],
  accordions: { versions: false },
};

// Runs a native action with Activity and busy feedback for Local Mode workflows.
async function runAction(action, payload, successMessage) {
  setBusy(true);
  showMessage("");
  try {
    const data = await callNative(action, payload || {});
    if (successMessage) {
      appendActivity(successMessage);
    }
    return data;
  } catch (error) {
    const message = error.message || "Local Mode operation failed.";
    console.error(`Native action failed: ${action}`, error);
    showMessage(message, true);
    appendActivity(message, true);
    throw error;
  } finally {
    setBusy(false);
  }
}

// Applies shared settings without scanning Local Mode folders during a mode-only change.
function applySettings(settings) {
  state.settings = settings || {};
}

// Returns the selected local version path from current state.
function activeVersionPath() {
  return state.local.active_version || "";
}

// Refreshes local project, feature, and version state from Python.
async function refreshState() {
  const data = await runAction("localProjectsState", {}, "");
  state.settings = data.settings || {};
  state.local = data.local || state.local;
  renderOrganizedLocalState();
  localRender.applyAccordionState(state.accordions);
  // Refresh factual activity after Local Mode state changes and use the scan to detect file edits.
  window.GitDeskActivityTracker.refresh(false).catch(() => {});
}

// Refreshes Shared Resources project-creation checkboxes from the revision-aware catalog.
async function refreshResources() {
  const data = await runAction("listSharedResources", {}, "");
  state.resources = data.resources || [];
  localRender.renderResources(state.resources, data.selected || []);
}

// Chooses a local project parent folder through the native dialog.
async function chooseParent() {
  const data = await runAction("chooseLocalParent", {
    initial_path: byId("local-parent-path").value,
  }, "Local parent selected");
  if (data.path) {
    setValue("local-parent-path", data.path);
    if (window.GitDeskLocalParentFavorites) {
      window.GitDeskLocalParentFavorites.sync();
    }
  }
}

// Renders filesystem state, project identity metadata, and version-comparison controls together.
function renderOrganizedLocalState() {
  localRender.renderLocalState(state.local);
  localProjectIdentity.render(state.local, state.settings);
  localFeaturePicker.render(state.local);
  localCompare.applyState(state.local);
}

// Applies backend state returned by mutating Local Mode actions.
function applyLocalResponse(data) {
  state.settings = data.settings || {};
  state.local = data.local || state.local;
  renderOrganizedLocalState();
  localRender.applyAccordionState(state.accordions);
}

const projectSelection = localProjectSelection.create({
  state,
  runAction,
  render() {
    renderOrganizedLocalState();
    localRender.applyAccordionState(state.accordions);
  },
});

// Creates a local project and activates its 01 init/v1 project-name folder.
async function createProject(event) {
  event.preventDefault();
  const data = await runAction("createLocalProject", {
    parent_path: byId("local-parent-path").value,
    name: byId("local-project-name").value,
    category: byId("local-project-category").value,
    shared_resources: localControls.selectedSharedResources(),
  }, "Local project created");
  byId("local-project-name").value = "";
  byId("local-project-category").value = "";
  projectSelection.applyResponse(data);
  if (window.GitDeskWorkspaceMode) {
    window.GitDeskWorkspaceMode.previewMode("local", true);
  }
  if (window.GitDeskProjectHubModal) {
    window.GitDeskProjectHubModal.close();
  }
}


// Creates a new feature from the selected version so work continues from the current project state.
async function createFeature(name) {
  const data = await runAction("createLocalFeature", {
    project_path: state.local.active_project,
    name,
    shared_resources: localControls.selectedSharedResources(),
    source_version_path: state.local.active_version,
  }, "Local feature created");
  applyLocalResponse(data);
}

// Toggles a Local Mode accordion section without asking Python for new state.
function toggleAccordion(name) {
  state.accordions[name] = !state.accordions[name];
  localRender.applyAccordionState(state.accordions);
}

// Renames the selected local project folder and lets the backend remap saved paths.
async function renameProject(path, name) {
  const data = await runAction("renameLocalProject", {
    project_path: path,
    name,
  }, "Local project renamed");
  applyLocalResponse(data);
}

// Selects one saved local project.
async function selectProject(path) {
  await projectSelection.select(path);
}

// Removes a project from Local Mode without deleting its folder.
async function removeProject(path) {
  const data = await runAction("removeLocalProject", { project_path: path }, "Local project removed");
  applyLocalResponse(data);
}

// Saves a project category label and refreshes the organized list.
async function setProjectCategory(path, category) {
  const data = await runAction("setLocalProjectCategory", {
    project_path: path,
    category,
  }, "Local project category saved");
  applyLocalResponse(data);
}

// Chooses, validates, and saves custom artwork for the active project without copying project content.
async function chooseProjectIcon(path) {
  const data = await runAction("chooseLocalProjectIcon", { project_path: path }, "");
  if (data.cancelled) {
    return;
  }
  applyLocalResponse(data);
  appendActivity("Local project icon saved");
}

// Clears custom artwork metadata so automatic app artwork or the packaged folder can resume.
async function clearProjectIcon(path) {
  const data = await runAction("clearLocalProjectIcon", { project_path: path }, "Local project icon cleared");
  applyLocalResponse(data);
}

// Selects one feature folder under the active local project.
async function selectFeature(path) {
  const data = await runAction("selectLocalFeature", {
    project_path: state.local.active_project,
    feature_path: path,
  }, "Local feature selected");
  state.accordions.versions = false;
  applyLocalResponse(data);
}

// Selects one physical version folder under the active feature.
async function selectVersion(path) {
  const data = await runAction("selectLocalVersion", {
    project_path: state.local.active_project,
    feature_path: state.local.active_feature,
    version_path: path,
  }, "Local version selected");
  applyLocalResponse(data);
}

// Renames a legacy selected v1 folder so external editor windows include the project name.
async function nameBareV1Version() {
  const data = await runAction("nameLocalV1Version", {
    project_path: state.local.active_project,
    version_path: activeVersionPath(),
  }, "Local v1 renamed");
  applyLocalResponse(data);
}

// Opens the duplicate dialog after loading the source version's cleanup tree.
async function openDuplicateDialog() {
  const tree = await runAction("localVersionTree", { version_path: activeVersionPath() }, "");
  localRender.renderCleanupTree(tree);
  byId("local-version-label").value = "";
  byId("local-duplicate-dialog").hidden = false;
  localRender.updateMoveSummary();
}

// Closes the duplicate dialog without changing the source version.
function closeDuplicateDialog() {
  byId("local-duplicate-dialog").hidden = true;
}

// Duplicates the active version, moving checked paths and copying unchecked paths.
async function duplicateVersion(event) {
  event.preventDefault();
  const data = await runAction("duplicateLocalVersion", {
    source_path: activeVersionPath(),
    label: byId("local-version-label").value,
    move_paths: localRender.collectMovePaths(),
  }, "Local version created");
  applyLocalResponse(data);
  closeDuplicateDialog();
}

// Opens the selected local version folder.
async function openFolder() {
  await runAction("openLocalVersionFolder", { version_path: activeVersionPath() }, "Local version opened");
}

// Opens the selected local version in the preferred code editor.
async function openVSCode(versionPath = activeVersionPath()) {
  const message = `Local version opened in ${editorSettings.name()}`;
  await runAction("openLocalVersionInVSCode", { version_path: versionPath }, message);
}

// Handles clicks inside the Local Mode version workspace.
function handleClick(event) {
  const accordionButton = event.target.closest("[data-local-menu-toggle]");
  if (accordionButton) {
    toggleAccordion(accordionButton.dataset.localMenuToggle);
    return;
  }
  const versionButton = event.target.closest(".local-version-row");
  if (versionButton) {
    selectVersion(versionButton.dataset.path || "");
  }
}

// Binds Local Mode controls after injected markup exists.
function bindEvents() {
  byId("refresh-local-projects").addEventListener("click", refreshState);
  byId("choose-local-parent").addEventListener("click", chooseParent);
  byId("local-create-form").addEventListener("submit", createProject);
  byId("local-layout").addEventListener("click", handleClick);
  byId("close-local-duplicate").addEventListener("click", closeDuplicateDialog);
  byId("local-duplicate-form").addEventListener("submit", duplicateVersion);
  byId("local-cleanup-tree").addEventListener("change", localRender.updateMoveSummary);
}

// Initializes Local Mode dynamic markup and initial category state.
function init() {
  localRender.injectUI();
  localCompare.injectUI();
  localVersionDelete.bind({ runAction, applyLocalResponse, getLocalState: () => state.local });
  sharedResourceManager.bindLocal({ runAction, getVersionPath: activeVersionPath });
  localOrganizer.bind({});
  localFeaturePicker.bind({
    onFeatureCreate: createFeature,
    onFeatureSelect: selectFeature,
  });
  localVersionActions.bind({
    getLocalState: () => state.local,
    onDuplicate: openDuplicateDialog,
    onNameV1: nameBareV1Version,
    onOpenFolder: openFolder,
    onOpenVSCode: openVSCode,
    runAction,
  });
  localRender.applyAccordionState(state.accordions);
  localProjectIdentity.bind({
    onProjectChange: selectProject,
    onOpenCurrentVersion: openVSCode,
    onLoadProjectIcons: () => runAction("localProjectIconPreviews", {}, ""),
    onChooseIcon: chooseProjectIcon,
    onClearIcon: clearProjectIcon,
    onRemove: removeProject,
    onCategoryChange: setProjectCategory,
    onRename: renameProject,
  });
  localControls.installIcons();
  localCompare.bind({ onLocalResponse: applyLocalResponse });
  bindEvents();
  refreshResources().catch(() => {});
}

window.GitDeskLocalMode = {
  applySettings, applyLocalResponse,
  activate: refreshState,
  refreshState,
  refreshSyncAvailability() {
    renderOrganizedLocalState();
    localRender.applyAccordionState(state.accordions);
  },
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
})();
