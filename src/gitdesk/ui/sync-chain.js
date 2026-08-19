/* Project Sync Chain setup and forward synchronization controller. */
// Owns chain state and delegates all privileged filesystem and GitHub work to Python.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const syncUI = window.GitDeskSyncChainUI;
const syncRender = window.GitDeskSyncChainRender;
const artifactJobs = window.GitDeskSyncChainArtifactJob;

if (!nativeBridge || !renderHelpers || !syncUI || !syncRender || !artifactJobs) {
  throw new Error("GitDesk Sync Chain dependencies did not load.");
}

const { callNative } = nativeBridge;
const { appendActivity, byId, setBusy, showMessage } = renderHelpers;
const state = {
  settings: {},
  sync: { chains: [], projects: [], repositories: [] },
  activeChainId: "",
  notifications: [],
  notificationRefreshPromise: null,
};

// Returns whether a backend-detected Local Mode change remains pending for one chained project.
function hasProjectNotification(projectPath) {
  const chain = chainForProject(projectPath);
  return Boolean(chain && state.notifications.some((item) => item.project_path === projectPath));
}

// Keeps the toolbar badge and its accessible label aligned with project-scoped pending changes.
function renderToolbarNotification() {
  const button = document.querySelector('.tab-button[data-tab="sync-chain"]');
  const dot = button ? button.querySelector("[data-sync-chain-alert]") : null;
  if (!button || !dot) return;
  const hasNotification = (state.sync.chains || []).some((chain) => {
    return state.notifications.some((item) => item.project_path === chain.project_path);
  });
  dot.hidden = !hasNotification;
  button.classList.toggle("has-success-notification", hasNotification);
  const label = hasNotification ? "Sync Chain Setup, local changes ready to sync" : "Sync Chain Setup";
  button.title = label;
  button.setAttribute("aria-label", label);
}

// Applies factual pending-change records returned by the Local Mode activity scan.
function applyActivityNotifications(payload) {
  state.notifications = Array.isArray(payload && payload.sync_chain_notifications)
    ? payload.sync_chain_notifications.filter((item) => item && item.project_path)
    : [];
  renderToolbarNotification();
  syncRender.renderChainList(state.sync, state.activeChainId, state.notifications);
  if (window.GitDeskWorkspaceMode && window.GitDeskWorkspaceMode.refreshSyncAvailability) {
    window.GitDeskWorkspaceMode.refreshSyncAvailability();
  }
}

// Clears one project immediately after its Local Mode sync while the durable activity refresh catches up.
function clearProjectNotification(projectPath) {
  state.notifications = state.notifications.filter((item) => item.project_path !== projectPath);
  renderToolbarNotification();
  syncRender.renderChainList(state.sync, state.activeChainId, state.notifications);
  if (window.GitDeskWorkspaceMode && window.GitDeskWorkspaceMode.refreshSyncAvailability) {
    window.GitDeskWorkspaceMode.refreshSyncAvailability();
  }
}

// Scans Local Mode fingerprints without the Project Activity view's more expensive Git-history work.
function refreshNotifications() {
  if (state.notificationRefreshPromise) return state.notificationRefreshPromise;
  state.notificationRefreshPromise = callNative("syncChainNotifications", {})
    .then((payload) => {
      applyActivityNotifications(payload);
      return payload;
    })
    .finally(() => {
      state.notificationRefreshPromise = null;
    });
  return state.notificationRefreshPromise;
}

// Polls only while Local Mode is visible and at least one project has a saved Sync Chain.
function refreshNotificationsQuietly() {
  const localMode = window.GitDeskWorkspaceMode && window.GitDeskWorkspaceMode.isLocalMode();
  if (!localMode || document.hidden || !(state.sync.chains || []).length) return;
  refreshNotifications().catch(() => {});
}

// Waits out an older scan before recomputing notifications from the completed Local sync receipt.
async function refreshNotificationsAfterLocalSync() {
  if (state.notificationRefreshPromise) {
    try {
      await state.notificationRefreshPromise;
    } catch (error) {
      // The receipt-aware retry below remains required after a failed or stale scan.
    }
  }
  return refreshNotifications();
}

async function runAction(action, payload, successMessage, actionRunner = callNative) {
  setBusy(true);
  showMessage("");
  try {
    const data = await actionRunner(action, payload || {});
    if (successMessage) appendActivity(successMessage);
    return data;
  } catch (error) {
    const message = error.message || "Sync Chain operation failed.";
    console.error(`Sync Chain action failed: ${action}`, error);
    showMessage(message, true);
    appendActivity(message, true);
    throw error;
  } finally {
    setBusy(false);
  }
}

function edgeRunner(chain, edge) {
  if (!chain || chain.artifact_only_edge !== edge) return callNative;
  return (_action, payload) => artifactJobs.run(chain.id, edge, payload.expected_release_tag || "");
}

// Applies backend state while retaining the selected chain when it still exists.
function applyResponse(data) {
  state.settings = data.settings || state.settings;
  state.sync = data.sync || state.sync;
  const chains = state.sync.chains || [];
  if (!chains.some((chain) => chain.id === state.activeChainId)) {
    state.activeChainId = chains.length ? chains[0].id : "";
  }
  syncRender.render(state.sync, state.settings, state.activeChainId, state.notifications);
  renderToolbarNotification();
  if (window.GitDeskRepositories) window.GitDeskRepositories.applySettings(state.settings);
  if (window.GitDeskWorkspaceMode && window.GitDeskWorkspaceMode.refreshSyncAvailability) {
    window.GitDeskWorkspaceMode.refreshSyncAvailability();
  }
}

// Hands a repository-to-repository destination to the main Repo Mode controller after a successful mirror.
function openSyncedDestination(data) {
  const handoff = data.repository_handoff;
  if (!handoff) return;
  window.dispatchEvent(new CustomEvent("gitdesk:sync-destination-ready", {
    detail: {
      ...handoff,
      auth: data.auth,
      settings: data.settings,
    },
  }));
}

// Applies one completed edge consistently for setup-page, Local Mode, and embedded-rail callers.
function applyCompletedSync(data) {
  applyResponse(data);
  openSyncedDestination(data);
  const release = data.sync_result && data.sync_result.release;
  if (release && release.tag_name) appendActivity(`Public release ${release.tag_name} published as latest`);
  if (data.sync_result && data.sync_result.warning) {
    appendActivity(data.sync_result.warning, true);
  }
}

// Resolves a chain by its Local Mode project instead of the setup page's independent selection.
function chainForProject(projectPath) {
  return (state.sync.chains || []).find((item) => item.project_path === projectPath) || null;
}

// Resolves the chain whose second repository stage matches the repository where a release was published.
function chainForPublicBeta(repositoryPath) {
  return (state.sync.chains || []).find((item) => {
    const publicBeta = item.stages && item.stages.public_beta;
    return publicBeta && publicBeta.repository_path === repositoryPath && item.stages.public;
  }) || null;
}

// Returns whether one saved Local Mode project has a configured Private Beta destination.
function canSyncProject(projectPath) {
  const chain = chainForProject(projectPath);
  return Boolean(chain && chain.stages && chain.stages.private_beta);
}

// Loads current project, repository, account, and chain metadata.
async function refresh() {
  applyResponse(await runAction("syncChainsState", {}, "Sync Chains refreshed"));
}

// Creates a chain from the selected metadata-backed Local Mode project.
async function createChain() {
  const projectPath = byId("sync-chain-project").value;
  if (!projectPath) return;
  const data = await runAction("createSyncChain", { project_path: projectPath }, "Sync Chain created");
  const created = (data.sync.chains || []).find((chain) => chain.project_path === projectPath);
  state.activeChainId = created ? created.id : state.activeChainId;
  applyResponse(data);
}

// Selects one existing managed repository for a stage without opening Finder.
async function configureStage(button) {
  const stage = button.dataset.stage || "";
  const select = document.querySelector(`.sync-stage-repository[data-stage="${stage}"]`);
  const option = select.options[select.selectedIndex];
  if (!option || !option.value) return;
  applyResponse(await runAction("configureSyncStage", {
    chain_id: state.activeChainId,
    stage,
    account_login: option.dataset.account || "",
    repository_path: option.value,
  }, "Sync Chain stage configured"));
}

// Reads one field from a stage-specific create repository form.
function formField(form, name) {
  return form.querySelector(`[data-sync-field="${name}"]`);
}

// Creates a separate GitHub/local repository and assigns it to the requested stage.
async function createStageRepository(form) {
  const stage = form.dataset.stage || "";
  const repositoryName = formField(form, "repo").value.trim();
  const folderName = formField(form, "folder").value.trim() || repositoryName;
  applyResponse(await runAction("createSyncStageRepository", {
    chain_id: state.activeChainId,
    stage,
    account_login: formField(form, "account").value,
    owner: formField(form, "owner").value,
    repo: repositoryName,
    parent_path: formField(form, "parent").value,
    folder_name: folderName,
    private: formField(form, "private").checked,
  }, "Sync Chain repository created"));
}

// Opens the existing native parent-folder chooser for one create-stage form.
async function chooseStageParent(button) {
  const form = button.closest("form");
  const parent = formField(form, "parent");
  const data = await runAction("chooseNewRepositoryParent", { initial_path: parent.value }, "");
  if (data.path) parent.value = data.path;
}

async function chooseStageFolder(button) {
  applyResponse(await runAction("chooseSyncStageFolder", {
    chain_id: state.activeChainId,
    stage: button.dataset.stage || "",
  }, "Local Sync Chain folder configured"));
}

// Advances one edge as an unconditional working-tree replacement while preserving destination .git metadata.
async function syncForward(button) {
  const edge = button.dataset.edge || "";
  const localEdge = edge === "local_to_private_beta";
  const source = button.closest(".sync-chain-local-source");
  const version = source ? source.querySelector(".sync-chain-local-version") : null;
  const action = localEdge ? "syncLocalVersionToPrivateBeta" : "syncChainEdge";
  const payload = localEdge
    ? { project_path: button.dataset.projectPath || "", version_path: version ? version.value : "" }
    : { chain_id: state.activeChainId, edge };
  const chain = (state.sync.chains || []).find((item) => item.id === state.activeChainId);
  button.disabled = true;
  try {
    const data = await runAction(action, payload, "Sync Chain advanced", edgeRunner(chain, edge));
    applyCompletedSync(data);
    if (localEdge) clearProjectNotification(button.dataset.projectPath || "");
    if (localEdge) refreshNotificationsAfterLocalSync().catch(() => {});
  } finally {
    if (button.isConnected) button.disabled = false;
  }
}

// Advances an edge for the inspector's selected project without using the setup page selection.
async function syncProjectEdge(projectPath, edge, options = {}) {
  const chain = chainForProject(projectPath);
  if (!chain) {
    throw new Error("The selected Local Mode project has no Sync Chain.");
  }
  const data = await runAction("syncChainEdge", {
    chain_id: chain.id,
    edge,
    expected_release_tag: options.expectedReleaseTag || "",
  }, "Sync Chain advanced", edgeRunner(chain, edge));
  applyCompletedSync(data);
}

async function configureProjectArtifactSync(projectPath, edge, enabled) {
  const chain = chainForProject(projectPath);
  if (!chain) {
    throw new Error("The selected Local Mode project has no Sync Chain.");
  }
  applyResponse(await runAction("configureArtifactSync", {
    chain_id: chain.id,
    edge,
    enabled,
  }, enabled ? "Built-artifact delivery enabled" : "Working-tree delivery enabled"));
}

// Saves the explicit final-edge mode immediately so the next Public sync cannot use a stale checkbox value.
async function configurePublicArtifactSync(input) {
  const edge = input.dataset.edge || "";
  const forwardButton = document.querySelector(`.sync-chain-forward[data-edge="${edge}"]`);
  input.disabled = true;
  if (forwardButton) forwardButton.disabled = true;
  try {
    applyResponse(await runAction("configureArtifactSync", {
      chain_id: state.activeChainId,
      edge,
      enabled: input.checked,
    }, input.checked ? "Built-artifact delivery enabled" : "Working-tree delivery enabled"));
  } catch (error) {
    syncRender.render(state.sync, state.settings, state.activeChainId, state.notifications);
    throw error;
  }
}

// Handles dynamic list, stage, create, remove, and sync controls from one stable panel listener.
function handleClick(event) {
  const chainRow = event.target.closest(".sync-chain-row");
  if (chainRow) {
    state.activeChainId = chainRow.dataset.chainId || "";
    syncRender.render(state.sync, state.settings, state.activeChainId, state.notifications);
    return;
  }
  const configure = event.target.closest(".configure-sync-stage");
  if (configure) configureStage(configure).catch(() => {});
  const choose = event.target.closest(".choose-sync-parent");
  if (choose) chooseStageParent(choose).catch(() => {});
  const chooseFolder = event.target.closest(".choose-sync-stage-folder");
  if (chooseFolder) chooseStageFolder(chooseFolder).catch(() => {});
  const forward = event.target.closest(".sync-chain-forward");
  if (forward) syncForward(forward).catch(() => {});
}

// Handles dynamically rendered create-stage forms.
function handleSubmit(event) {
  const form = event.target.closest(".sync-stage-create-form");
  if (!form) return;
  event.preventDefault();
  createStageRepository(form).catch(() => {});
}

// Keeps owner and local-folder suggestions aligned with the selected account and repository name.
function handleInput(event) {
  if (event.target.matches("[data-sync-artifacts-only]")) {
    configurePublicArtifactSync(event.target).catch(() => {});
    return;
  }
  if (event.target.matches("[data-sync-local-toggle]")) {
    const card = event.target.closest(".sync-chain-stage");
    card.querySelector(".sync-chain-repository-choice").hidden = event.target.checked;
    card.querySelector(".sync-chain-local-choice").hidden = !event.target.checked;
    card.querySelector(".sync-chain-create-repo")?.toggleAttribute("hidden", event.target.checked);
    return;
  }
  const form = event.target.closest(".sync-stage-create-form");
  if (!form) return;
  if (event.target.dataset.syncField === "account") formField(form, "owner").value = event.target.value;
  if (event.target.dataset.syncField === "repo" && !formField(form, "folder").value.trim()) {
    formField(form, "folder").value = event.target.value;
  }
}

// Installs the page before app.js discovers and binds the injected toolbar button.
function init() {
  syncUI.injectUI();
  byId("create-sync-chain").addEventListener("click", () => createChain().catch(() => {}));
  byId("refresh-sync-chains").addEventListener("click", () => refresh().catch(() => {}));
  byId("panel-sync-chain").addEventListener("click", handleClick);
  byId("panel-sync-chain").addEventListener("submit", handleSubmit);
  byId("panel-sync-chain").addEventListener("change", handleInput);
  document.querySelector('.tab-button[data-tab="sync-chain"]').addEventListener("click", () => {
    refresh().catch(() => {});
  });
  window.setInterval(refreshNotificationsQuietly, 5000);
  window.addEventListener("focus", refreshNotificationsQuietly);
  document.addEventListener("visibilitychange", refreshNotificationsQuietly);
  callNative("syncChainsState", {}).then(applyResponse).catch(() => {});
}

// Runs initialization after static markup is parsed.
function onReady(callback) {
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", callback);
  else callback();
}

window.GitDeskSyncChains = {
  applyActivityNotifications,
  applyCompletedSync,
  applyResponse,
  canSyncProject,
  chainForProject,
  chainForPublicBeta,
  clearProjectNotification,
  configureProjectArtifactSync,
  hasProjectNotification,
  refresh,
  refreshNotificationsAfterLocalSync,
  syncProjectEdge,
};
onReady(init);
})();
