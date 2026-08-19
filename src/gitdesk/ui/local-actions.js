/*
  Local Mode project, version, and Sync Chain action availability rendering.
*/

// Keeps action-state decisions out of the near-limit Local Mode markup renderer.
(() => {
const renderHelpers = window.GitDeskRender;
const localVersionWorkspace = window.GitDeskLocalVersionWorkspace;

if (!renderHelpers || !localVersionWorkspace) {
  throw new Error("GitDesk Local Mode action dependencies did not load.");
}

const { byId } = renderHelpers;

// Enables project and version controls only when their required physical records are selected.
function render(localState, project, version) {
  const hasProject = Boolean(project && project.exists);
  const hasVersion = Boolean(version);
  const nameV1Button = byId("name-local-v1");
  nameV1Button.hidden = !(project && version && version.name === "v1");
  nameV1Button.disabled = nameV1Button.hidden;
  [
    "duplicate-local-version",
    "open-local-folder",
    "open-local-vscode",
    "open-local-notes",
    "open-sync-ignore",
    "manage-local-shared-resources",
  ].forEach((id) => {
    byId(id).disabled = !hasVersion;
  });
  const syncManager = window.GitDeskSyncChains;
  const canSync = Boolean(hasProject && hasVersion && syncManager && syncManager.canSyncProject(
    localState.active_project,
  ));
  const syncButton = byId("sync-local-private-beta");
  syncButton.hidden = false;
  syncButton.disabled = !canSync;
  syncButton.title = canSync
    ? "Sync selected version to Private Beta"
    : "Configure this project's Private Beta Sync Chain first.";
  localVersionWorkspace.render(localState, project, version);
}

window.GitDeskLocalActions = { render };
})();
