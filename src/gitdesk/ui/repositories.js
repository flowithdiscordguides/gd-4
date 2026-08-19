/*
  Account-scoped managed repository picker and GitHub clone catalog.
*/

// Keeps repository picker state private while exposing a small API to the main controller.
(() => {
const renderHelpers = window.GitDeskRender;
const accountManager = window.GitDeskAccounts;
const repositoryRender = window.GitDeskRepositoryRender;

if (!renderHelpers || !accountManager || !repositoryRender) {
  throw new Error("GitDesk repository dependencies did not load.");
}

const {
  byId,
  setValue,
  showMessage,
  showPanel,
} = renderHelpers;

let runActionRef = null;
let callbacks = {};
const state = {
  settings: {},
  githubRepositories: [],
  githubOrganizations: [],
  organizationAccess: "complete",
  existingRepository: null,
  aiCategories: [],
  selectedAiCategories: [],
  catalogAccount: "",
  dialogOpen: false,
  dialogMode: "clone",
};

// Returns the active account login from the account manager.
function activeLogin() {
  return accountManager.activeLogin();
}

// Returns repository records visible to the active account only.
function repositoriesForActiveAccount() {
  return repositoryRender.repositoriesForAccount(state.settings, activeLogin());
}

// Returns the persisted active repository path if it belongs to the active account.
function activePathFromSettings() {
  const login = activeLogin();
  const activeByAccount = state.settings.active_repository_by_account || {};
  const path = login ? activeByAccount[login] || "" : "";
  return repositoriesForActiveAccount().some((record) => record.path === path) ? path : "";
}

// Returns the selected repository path shown in the topbar selector.
function activePath() {
  const select = byId("managed-repo-select");
  return select.disabled ? "" : select.value.trim();
}

// Renders the topbar repository dropdown for the currently active account.
function renderPicker() {
  const login = activeLogin();
  repositoryRender.renderPicker({
    accountLogin: login,
    activePath: activePathFromSettings(),
    repositories: repositoriesForActiveAccount(),
  });
  byId("add-managed-repo").disabled = !login;
  byId("refresh-github-repos").disabled = !login;
  byId("refresh-status").disabled = !activePath();
}

// Applies settings returned by Python and refreshes all repository picker surfaces.
function applySettings(settings) {
  state.settings = settings || {};
  renderPicker();
  if (state.dialogOpen) {
    renderDialog();
  }
}

// Renders all repository dialog surfaces from the latest account/settings/catalog state.
function renderDialog() {
  repositoryRender.renderMode(state.dialogMode);
  repositoryRender.renderManagedList({
    accountLogin: activeLogin(),
    activePath: activePathFromSettings(),
    repositories: repositoriesForActiveAccount(),
  });
  const catalogMatchesAccount = state.catalogAccount === activeLogin();
  const catalog = catalogMatchesAccount ? state.githubRepositories : [];
  const organizationContext = {
    accountLogin: activeLogin(),
    credentialProfiles: accountManager.signedInProfiles(),
    organizations: catalogMatchesAccount ? state.githubOrganizations : [],
    organizationAccess: catalogMatchesAccount ? state.organizationAccess : "complete",
  };
  repositoryRender.renderOrganizationContext(organizationContext, catalog);
  repositoryRender.renderCatalog(catalog, organizationContext);
  repositoryRender.renderExistingRemote(state.existingRepository, organizationContext);
  repositoryRender.renderCreateAiCategories(state.aiCategories, state.selectedAiCategories);
  repositoryRender.renderRemoteFields();
}

// Returns the standard repository payload used by Git operations.
function payload() {
  return {
    path: activePath(),
    account_login: activeLogin(),
  };
}

// Opens the GitHub repository catalog dialog and optionally refreshes it immediately.
async function openDialog(forceRefresh) {
  if (!activeLogin()) {
    showMessage("Save a GitHub PAT profile before adding repositories.", true);
    return;
  }

  state.dialogOpen = true;
  byId("repo-add-dialog").hidden = false;
  state.dialogMode = forceRefresh ? "clone" : state.dialogMode;
  if (!byId("managed-clone-parent").value && byId("clone-parent-path")) {
    setValue("managed-clone-parent", byId("clone-parent-path").value);
  }
  if (!byId("new-repo-parent").value && byId("clone-parent-path")) {
    setValue("new-repo-parent", byId("clone-parent-path").value);
  }
  if (!byId("new-repo-owner").value) {
    setValue("new-repo-owner", activeLogin());
  }
  await refreshAiCategories();
  if (forceRefresh || state.catalogAccount !== activeLogin()) {
    await refreshGithubRepositories();
    return;
  }
  renderDialog();
}

// Hides the catalog dialog without clearing fetched repository data.
function closeDialog() {
  state.dialogOpen = false;
  byId("repo-add-dialog").hidden = true;
}

// Loads the latest GitHub repository list for the active account.
async function refreshGithubRepositories() {
  const data = await runActionRef(
    "listGitHubRepositories",
    { account_login: activeLogin() },
    "GitHub repositories refreshed",
  );
  state.githubRepositories = data.repositories || [];
  state.githubOrganizations = data.organizations || [];
  state.organizationAccess = data.organization_access || "complete";
  state.catalogAccount = data.account_login || activeLogin();
  renderDialog();
}

// Loads Shared Resources so create-new repositories can receive reusable files immediately.
async function refreshAiCategories() {
  const data = await runActionRef("listSharedResources", {}, "");
  state.aiCategories = data.categories || [];
  state.selectedAiCategories = data.selected || [];
  if (state.dialogOpen) {
    renderDialog();
  }
}

// Selects a managed local repository and asks Python to verify it belongs to the active account.
async function selectManagedRepository(pathValue) {
  const selectedPath = String(pathValue || activePath()).trim();
  if (!selectedPath) {
    byId("refresh-status").disabled = true;
    return;
  }

  const previousPath = activePathFromSettings();
  byId("managed-repo-select").value = selectedPath;
  const requestPayload = payload();
  requestPayload.path = selectedPath;
  const selectionRequest = runActionRef("selectManagedRepository", requestPayload, "Repository selected");
  showMessage("Loading repository status and branches…");
  let data;
  try {
    data = await selectionRequest;
  } catch (error) {
    byId("managed-repo-select").value = previousPath;
    renderPicker();
    return;
  }
  callbacks.applySettings(data.settings);
  callbacks.resetSelections();
  callbacks.applyStatus(data.status);
  callbacks.renderBranches(data.branches);
  showPanel("overview");
  showMessage("");
}

// Opens a native folder picker for the managed clone destination field.
async function chooseManagedCloneDestination() {
  const data = await runActionRef("chooseCloneDestination", {
    initial_path: byId("managed-clone-parent").value,
  });
  if (data.path) {
    setValue("managed-clone-parent", data.path);
  }
}

// Opens a native folder picker for adding an existing repository.
async function chooseExistingRepository() {
  const data = await runActionRef("chooseExistingRepository", {
    initial_path: byId("existing-repo-path").value,
  });
  if (data.path) {
    setValue("existing-repo-path", data.path);
    state.existingRepository = data.repository || null;
    renderDialog();
  }
}

// Opens a native folder picker for the new repository parent folder.
async function chooseNewRepositoryParent() {
  const data = await runActionRef("chooseNewRepositoryParent", {
    initial_path: byId("new-repo-parent").value,
  });
  if (data.path) {
    setValue("new-repo-parent", data.path);
  }
}

// Applies a backend response that opened a repository and switches to Overview.
function applyOpenedRepository(data) {
  accountManager.apply(data.auth);
  callbacks.applySettings(data.settings);
  callbacks.resetSelections();
  callbacks.applyStatus(data.status);
  callbacks.renderBranches(data.branches);
  closeDialog();
  showPanel("overview");
}

// Clones the clicked GitHub repository and registers it under the matching owner profile.
async function cloneGithubRepository(button) {
  const cloneUrl = button.dataset.cloneUrl || "";
  const folderName = button.dataset.folderName || "";
  const payloadData = {
    account_login: activeLogin(),
    repository_owner: button.dataset.repositoryOwner || "",
    clone_url: cloneUrl,
    parent_path: byId("managed-clone-parent").value,
    folder_name: folderName,
    category: byId("managed-clone-category").value,
  };
  const data = await runActionRef("cloneManagedRepository", payloadData, "Repository cloned");
  applyOpenedRepository(data);
}

// Adds a local Git repository without moving or cloning it.
async function addExistingRepository(event) {
  event.preventDefault();
  const data = await runActionRef("addExistingRepository", {
    account_login: activeLogin(),
    path: byId("existing-repo-path").value,
    category: byId("existing-repo-category").value,
  }, "Repository added");
  applyOpenedRepository(data);
}

// Creates a new GitHub repository and opens the matching local checkout folder.
async function createNewRepository(event) {
  event.preventDefault();
  const repositoryName = byId("new-repo-name").value.trim();
  const folderName = byId("new-repo-folder").value.trim() || repositoryName;
  const data = await runActionRef("createNewRepository", {
    account_login: activeLogin(),
    parent_path: byId("new-repo-parent").value,
    folder_name: folderName,
    category: byId("new-repo-category").value,
    owner: byId("new-repo-owner").value,
    repo: repositoryName,
    private: byId("new-repo-private").checked,
    shared_resources: repositoryRender.selectedCreateAiCategories(),
  }, "Repository created");
  applyOpenedRepository(data);
}

// Removes one saved repository record without deleting local files.
async function removeManagedRepository(path) {
  const wasActive = path === activePathFromSettings();
  const data = await runActionRef("removeManagedRepository", {
    account_login: activeLogin(),
    path,
  }, "Repository removed from GitDesk");
  callbacks.applySettings(data.settings);
  if (wasActive) {
    callbacks.resetSelections();
  }
}

// Persists the category attached to one saved repository record.
async function setManagedRepositoryCategory(input) {
  const data = await runActionRef("setManagedRepositoryCategory", {
    account_login: activeLogin(),
    path: input.dataset.path || "",
    category: input.value,
  }, "Repository category saved");
  callbacks.applySettings(data.settings);
}

// Switches the dialog between clone, add-existing, and create-new modes.
function setDialogMode(mode) {
  state.dialogMode = mode || "clone";
  renderDialog();
}

// Handles delegated clone clicks from the GitHub repository list.
function handleCatalogClick(event) {
  const button = event.target.closest(".clone-github-repo");
  if (!button) {
    return;
  }
  cloneGithubRepository(button);
}

// Handles repository setup mode tab clicks inside the dialog.
function handleDialogModeClick(event) {
  const button = event.target.closest("[data-repo-mode]");
  if (!button) {
    return;
  }
  setDialogMode(button.dataset.repoMode);
}

// Handles saved repository open and remove actions from the dialog list.
function handleManagedListClick(event) {
  const removeButton = event.target.closest(".remove-managed-repo");
  if (removeButton) {
    removeManagedRepository(removeButton.dataset.path || "");
    return;
  }
  const openButton = event.target.closest(".managed-repo-open");
  if (openButton) {
    selectManagedRepository(openButton.dataset.path || "");
  }
}

// Saves category edits when the user leaves or commits a category input.
function handleManagedListChange(event) {
  if (!event.target.classList.contains("managed-repo-category")) {
    return;
  }
  setManagedRepositoryCategory(event.target);
}

// Binds repository controls after the main app provides native and render callbacks.
function bind(options) {
  runActionRef = options.runAction;
  callbacks = options;
  repositoryRender.injectUI();
  repositoryRender.renderRemoteFields();
  byId("managed-repo-select").addEventListener("change", () => selectManagedRepository());
  byId("add-managed-repo").addEventListener("click", () => openDialog(false));
  byId("refresh-github-repos").addEventListener("click", () => openDialog(true));
  byId("close-managed-repo-dialog").addEventListener("click", closeDialog);
  byId("repo-dialog-modes").addEventListener("click", handleDialogModeClick);
  byId("managed-repo-list").addEventListener("click", handleManagedListClick);
  byId("managed-repo-list").addEventListener("change", handleManagedListChange);
  byId("refresh-managed-repo-list").addEventListener("click", refreshGithubRepositories);
  byId("choose-managed-clone-parent").addEventListener("click", chooseManagedCloneDestination);
  byId("choose-existing-repo").addEventListener("click", chooseExistingRepository);
  byId("choose-new-repo-parent").addEventListener("click", chooseNewRepositoryParent);
  byId("existing-repo-form").addEventListener("submit", addExistingRepository);
  byId("new-repo-form").addEventListener("submit", createNewRepository);
  byId("new-repo-folder").addEventListener("input", repositoryRender.syncNewRepoName);
  byId("new-repo-name").addEventListener("input", repositoryRender.syncNewFolderName);
  byId("github-owner-filter").addEventListener("change", renderDialog);
  byId("github-repo-filter").addEventListener("input", renderDialog);
  byId("existing-repo-path").addEventListener("input", () => {
    state.existingRepository = null;
    repositoryRender.renderExistingRemote(null, {
      accountLogin: activeLogin(),
      organizations: state.githubOrganizations,
    });
  });
  byId("github-repo-list").addEventListener("click", handleCatalogClick);
}

// Publishes repository picker helpers for the main controller.
window.GitDeskRepositories = {
  activePath,
  applySettings,
  bind,
  payload,
};
})();
