/*
  Selected-version action bindings, including every embedded Sync Chain stage.
*/

// Extracts inspector actions from the near-limit Local Mode controller.
(() => {
const renderHelpers = window.GitDeskRender;
const localSync = window.GitDeskLocalSync;
const localNotes = window.GitDeskLocalMarkdownNotes;

if (!renderHelpers || !localSync || !localNotes) {
  throw new Error("GitDesk selected-version action dependencies did not load.");
}

const { byId } = renderHelpers;
let controller = {};
let bound = false;
let pendingPromotionEdge = "";

// Re-renders the rail from module-owned pending state so notification refreshes cannot unlock it early.
function refreshPromotionState() {
  const workspace = window.GitDeskWorkspaceMode;
  if (workspace && workspace.refreshSyncAvailability) {
    workspace.refreshSyncAvailability();
  }
}

// Exposes only the current edge identity to the renderer; receipts remain backend-owned completion facts.
function currentPendingPromotionEdge() {
  return pendingPromotionEdge;
}

// Runs the selected Local version into Private Beta through the shared completion path.
async function syncPrivateBeta() {
  const localState = controller.getLocalState();
  await localSync.syncToPrivateBeta(
    controller.runAction,
    localState.active_project,
    localState.active_version,
  );
}

// Opens the note workspace with the exact current ownership context.
function openNotes(event) {
  const localState = controller.getLocalState();
  localNotes.open({
    project_path: localState.active_project,
    feature_path: localState.active_feature,
    version_path: localState.active_version,
  }, event.currentTarget).catch(() => {});
}

// Owns one Local Mode promotion from click through completion so repeat clicks cannot queue duplicate mirrors.
async function runPromotionEdge(edge) {
  if (!edge || pendingPromotionEdge) {
    return;
  }
  pendingPromotionEdge = edge;
  try {
    refreshPromotionState();
    if (edge === "local_to_private_beta") {
      await syncPrivateBeta();
      return;
    }
    const localState = controller.getLocalState();
    await window.GitDeskSyncChains.syncProjectEdge(localState.active_project, edge);
  } finally {
    pendingPromotionEdge = "";
    refreshPromotionState();
  }
}

// Routes each rail arrow by project path instead of the setup page's selected chain id.
function handlePromotionClick(event) {
  const button = event.target.closest("[data-local-sync-edge]");
  if (button) {
    runPromotionEdge(button.dataset.localSyncEdge || "").catch(() => {});
  }
}

// Saves the Local Mode Public-stage checkbox against this project's chain before final sync can run.
async function configureArtifactOnly(input) {
  const localState = controller.getLocalState();
  const rail = input.closest(".local-version-sync-rail");
  const edge = input.dataset.edge || "";
  const finalButton = rail.querySelector(`[data-local-sync-edge="${edge}"]`);
  input.disabled = true;
  if (finalButton) finalButton.disabled = true;
  try {
    await window.GitDeskSyncChains.configureProjectArtifactSync(
      localState.active_project,
      edge,
      input.checked,
    );
  } catch {
    window.GitDeskWorkspaceMode.refreshSyncAvailability();
  }
}

// Handles the checkbox separately from icon-only promotion edge clicks.
function handlePromotionChange(event) {
  if (event.target.matches("[data-local-artifacts-only]")) {
    configureArtifactOnly(event.target).catch(() => {});
  }
}

// Binds stable inspector controls after Local Mode has injected its markup.
function bind(options) {
  controller = options || {};
  localNotes.bind();
  if (bound) {
    return;
  }
  bound = true;
  byId("name-local-v1").addEventListener("click", controller.onNameV1);
  byId("duplicate-local-version").addEventListener("click", controller.onDuplicate);
  byId("open-local-folder").addEventListener("click", controller.onOpenFolder);
  // Keep the browser click event out of the optional version-path parameter.
  byId("open-local-vscode").addEventListener("click", () => controller.onOpenVSCode());
  byId("open-local-notes").addEventListener("click", openNotes);
  byId("sync-local-private-beta").addEventListener("click", () => {
    runPromotionEdge("local_to_private_beta").catch(() => {});
  });
  byId("local-version-sync-rail").addEventListener("click", handlePromotionClick);
  byId("local-version-sync-rail").addEventListener("change", handlePromotionChange);
}

window.GitDeskLocalVersionActions = { bind, currentPendingPromotionEdge };
})();
