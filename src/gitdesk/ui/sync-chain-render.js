/*
  Rendering helpers for Project Sync Chain setup records and stage controls.
*/

// Keeps backend metadata escaping and markup generation out of the workflow controller.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk Sync Chain render dependencies did not load.");
}

const { byId, setText } = renderHelpers;
const STAGES = [
  { name: "private_beta", label: "Private Beta", edge: "local_to_private_beta" },
  { name: "public_beta", label: "Public Beta", edge: "private_beta_to_public_beta" },
  { name: "public", label: "Public", edge: "public_beta_to_public" },
];

// Escapes all path, account, and repository values inserted into dynamic HTML.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Returns one project record for a saved chain path.
function projectForChain(syncState, chain) {
  return (syncState.projects || []).find((project) => project.path === chain.project_path) || null;
}

// Renders projects that do not already own a chain into the creation selector.
function renderProjectChoices(syncState) {
  const chainedPaths = (syncState.chains || []).map((chain) => chain.project_path);
  const available = (syncState.projects || []).filter((project) => chainedPaths.indexOf(project.path) < 0);
  const select = byId("sync-chain-project");
  select.innerHTML = available.length
    ? '<option value="">Select Local Mode project</option>' + available.map((project) => (
      `<option value="${escapeHtml(project.path)}">${escapeHtml(project.name)}</option>`
    )).join("")
    : '<option value="">Every Local Mode project has a chain</option>';
  select.disabled = !available.length;
  byId("create-sync-chain").disabled = !available.length;
}

// Renders the saved chain selector with stage-completion context.
function renderChainList(syncState, activeChainId, notifications = []) {
  const list = byId("sync-chain-list");
  if (!list) return;
  const chains = syncState.chains || [];
  if (!chains.length) {
    list.innerHTML = '<div class="empty-state">No Sync Chains configured</div>';
    return;
  }
  list.innerHTML = chains.map((chain) => {
    const project = projectForChain(syncState, chain);
    const active = chain.id === activeChainId ? " active" : "";
    const working = Boolean((chain.receipts || {}).local_to_private_beta);
    const statusClass = working ? " working" : " inactive";
    const statusLabel = working ? "Active chain" : "Inactive chain";
    const stageCount = Object.keys(chain.stages || {}).length;
    const pending = notifications.some((item) => item.project_path === chain.project_path);
    const notificationClass = pending ? " has-notification" : "";
    const projectName = project ? project.name : "Missing Local Mode project";
    const pendingLabel = pending ? ", local changes ready to sync" : "";
    return `
      <button class="sync-chain-row${active}${statusClass}${notificationClass}" type="button"
        data-chain-id="${escapeHtml(chain.id)}"
        aria-label="${escapeHtml(projectName + pendingLabel)}">
        <span class="sync-chain-status-icon" title="${statusLabel}" aria-label="${statusLabel}">
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M9.5 14.5 14.5 9.5"></path>
            <path d="M7.2 16.8 5.8 18.2a3 3 0 0 1-4.2-4.2L5 10.6a3 3 0 0 1 4.2 0"></path>
            <path d="m16.8 7.2 1.4-1.4A3 3 0 0 1 22.4 10L19 13.4a3 3 0 0 1-4.2 0"></path>
          </svg>
        </span>
        <span class="sync-chain-row-copy">
          <strong>${escapeHtml(projectName)}</strong>
          <small>${stageCount} of 3 stages configured</small>
        </span>
        ${pending ? `<span class="sync-chain-row-notification" aria-hidden="true"
          title="Unsynced local changes detected"></span>` : ""}
      </button>
    `;
  }).join("");
}

// Renders an explicit physical Local version selector before the first repository stage.
function localSourceMarkup(project, chain, settings) {
  const versions = project ? project.versions || [] : [];
  const activePath = project && project.path === settings.active_local_project
    ? settings.active_local_version || ""
    : "";
  const selectedPath = versions.some((version) => version.path === activePath)
    ? activePath
    : versions.length ? versions[versions.length - 1].path : "";
  const options = versions.length ? versions.map((version) => {
    const selected = version.path === selectedPath ? "selected" : "";
    const label = `${version.feature_name} / ${version.name}`;
    return `<option value="${escapeHtml(version.path)}" ${selected}>${escapeHtml(label)}</option>`;
  }).join("") : '<option value="">No Local versions found</option>';
  const stageReady = Boolean((chain.stages || {}).private_beta);
  const disabled = stageReady && selectedPath ? "" : "disabled";
  const ignoreDisabled = selectedPath ? "" : "disabled";
  return `
    <section class="sync-chain-local-source">
      <div>
        <small>Local source</small>
        <h3>Select the exact version for Stage 1</h3>
      </div>
      <select class="sync-chain-local-version" aria-label="Local version to sync" ${versions.length ? "" : "disabled"}>
        ${options}
      </select>
      <div class="sync-chain-local-actions">
        <button class="sync-chain-forward primary" type="button" data-edge="local_to_private_beta"
          data-project-path="${escapeHtml(chain.project_path)}" ${disabled}>
          Sync Local to Private Beta
        </button>
        <button class="sync-chain-ignore" type="button" data-sync-ignore-trigger="chain"
          aria-haspopup="dialog" aria-controls="sync-ignore-dialog" aria-expanded="false"
          title="Edit Sync Ignore for this Local project" ${ignoreDisabled}>
          Sync Ignore
        </button>
      </div>
      ${stageReady ? "" : "<small>Configure Private Beta before syncing.</small>"}
    </section>
  `;
}

// Returns repositories as exact metadata-backed options, preserving owning account information.
function repositoryOptions(syncState, selectedStage) {
  const selectedPath = selectedStage ? selectedStage.repository_path : "";
  const selectedLogin = selectedStage ? selectedStage.account_login : "";
  return '<option value="">Select saved repository</option>' + (syncState.repositories || []).map((repository) => {
    const selected = repository.path === selectedPath && repository.account_login === selectedLogin ? "selected" : "";
    const label = `${repository.account_login} / ${repository.full_name || repository.name}`;
    return `<option value="${escapeHtml(repository.path)}" data-account="${escapeHtml(repository.account_login)}" `
      + `${selected}>${escapeHtml(label)}</option>`;
  }).join("");
}

// Returns signed-in account choices for creating a missing GitHub repository stage.
function accountOptions(settings) {
  const accounts = (settings.github_accounts || []).filter((account) => account.token_present);
  const activeLogin = settings.active_account || "";
  return accounts.map((account) => {
    const selected = account.login === activeLogin ? "selected" : "";
    const type = account.resource_owner_type === "Organization" ? "Organization" : "Personal";
    const label = `${account.login} — ${type}`;
    return `<option value="${escapeHtml(account.login)}" ${selected}>${escapeHtml(label)}</option>`;
  }).join("");
}

// Formats one saved receipt without displaying its full content digest.
function receiptMarkup(receipt) {
  if (!receipt) return '<div class="sync-chain-receipt">Never synchronized</div>';
  if (receipt.sync_mode === "release_artifacts") {
    return `
      <div class="sync-chain-receipt">
        Last release sync: ${escapeHtml(receipt.release_tag || "unknown")} -
        ${Number(receipt.file_count || 0)} artifacts
      </div>
    `;
  }
  return `
    <div class="sync-chain-receipt">
      Last sync: ${escapeHtml(receipt.synced_at || "unknown")} - ${Number(receipt.file_count || 0)} files
    </div>
  `;
}

// Places release-assets-only policy beside the actual terminal repository stage.
function publicArtifactOptionMarkup(stage, chain, configured) {
  const index = STAGES.findIndex((item) => item.name === stage.name);
  const nextConfigured = STAGES.slice(index + 1).some((item) => Boolean(chain.stages[item.name]));
  const previous = index > 0 ? chain.stages[STAGES[index - 1].name] : null;
  const eligible = configured && previous && !configured.local_only && !previous.local_only && !nextConfigured;
  if (!eligible) return "";
  const checked = chain.artifact_only_edge === stage.edge ? "checked" : "";
  return `
    <label class="sync-chain-artifact-option" title="Publish only the source stage's latest release assets">
      <input type="checkbox" data-sync-artifacts-only data-edge="${escapeHtml(stage.edge)}" ${checked}>
      <span>Built artifacts only</span>
    </label>
  `;
}

// Offers an ordinary folder destination without accepting a WebView-supplied filesystem path.
function destinationChoiceMarkup(stage, configured, syncState, previousReady) {
  const localOnly = Boolean(configured && configured.local_only);
  const disabled = previousReady ? "" : "disabled";
  return `
    <label class="sync-chain-local-option">
      <input type="checkbox" data-sync-local-toggle data-stage="${escapeHtml(stage.name)}"
        ${localOnly ? "checked" : ""} ${disabled}>
      <span>Use a local folder</span>
    </label>
    <div class="sync-chain-repository-choice" ${localOnly ? "hidden" : ""}>
      <div class="sync-chain-stage-select">
        <select class="sync-stage-repository" data-stage="${escapeHtml(stage.name)}" ${disabled}>
          ${repositoryOptions(syncState, localOnly ? null : configured)}
        </select>
        <button class="configure-sync-stage" type="button" data-stage="${escapeHtml(stage.name)}" ${disabled}>
          Save repository
        </button>
      </div>
    </div>
    <div class="sync-chain-local-choice" ${localOnly ? "" : "hidden"}>
      <button class="choose-sync-stage-folder" type="button" data-stage="${escapeHtml(stage.name)}" ${disabled}>
        Choose local folder
      </button>
      <small>Git is not required. The chosen folder becomes this stage's destination.</small>
    </div>
  `;
}

// Builds the create-new repository fields for one unconfigured or replaceable stage.
function createRepositoryMarkup(stage, settings) {
  const prefix = `sync-new-${stage.name}`;
  const checked = stage.name === "private_beta" ? "checked" : "";
  return `
    <details class="sync-chain-create-repo">
      <summary>Create a new ${escapeHtml(stage.label)} repository</summary>
      <form class="sync-stage-create-form" data-stage="${escapeHtml(stage.name)}">
        <label for="${prefix}-account">PAT profile</label>
        <select id="${prefix}-account" data-sync-field="account">${accountOptions(settings)}</select>
        <label for="${prefix}-owner">GitHub owner</label>
        <input id="${prefix}-owner" data-sync-field="owner" type="text" spellcheck="false"
          value="${escapeHtml(settings.active_account || "")}">
        <label for="${prefix}-repo">GitHub repository name</label>
        <input id="${prefix}-repo" data-sync-field="repo" type="text" spellcheck="false" required>
        <label for="${prefix}-parent">Parent folder</label>
        <div class="input-action-row">
          <input id="${prefix}-parent" data-sync-field="parent" type="text" spellcheck="false" required>
          <button class="choose-sync-parent" type="button" title="Choose parent folder">Folder</button>
        </div>
        <label for="${prefix}-folder">Local repository folder</label>
        <input id="${prefix}-folder" data-sync-field="folder" type="text" spellcheck="false" required>
        <label class="check-row">
          <input data-sync-field="private" type="checkbox" ${checked}>
          <span>Private GitHub repository</span>
        </label>
        <button type="submit">Create and assign repository</button>
      </form>
    </details>
  `;
}

// Builds one ordered stage card with existing-repo, create-new, removal, and forward-sync controls.
function stageMarkup(stage, chain, syncState, settings) {
  const configured = (chain.stages || {})[stage.name] || null;
  const index = STAGES.findIndex((item) => item.name === stage.name);
  const previousReady = index === 0 || Boolean((chain.stages || {})[STAGES[index - 1].name]);
  const nextStage = STAGES[index + 1] || null;
  const canSyncForward = nextStage && configured && Boolean((chain.stages || {})[nextStage.name]);
  const artifactOnly = nextStage && chain.artifact_only_edge === nextStage.edge;
  const actionLabel = artifactOnly
    ? "Publish Public Beta release artifacts to Public"
    : `Sync ${stage.label} to ${nextStage ? nextStage.label : "next stage"}`;
  const syncButton = canSyncForward ? `
    <button class="sync-chain-forward primary" type="button" data-edge="${escapeHtml(nextStage.edge)}">
      ${escapeHtml(actionLabel)}
    </button>
  ` : "";
  const removeButton = configured
    ? `<button class="remove-sync-stage" type="button" data-chain-id="${escapeHtml(chain.id)}"
        data-stage="${escapeHtml(stage.name)}">Remove stage</button>`
    : "";
  return `
    <section class="sync-chain-stage${configured ? " configured" : ""}">
      <div class="sync-chain-stage-header">
        <div class="sync-chain-stage-heading">
          <div>
            <small>Stage ${index + 1}</small>
            <h3>${escapeHtml(stage.label)}</h3>
          </div>
          ${publicArtifactOptionMarkup(stage, chain, configured)}
        </div>
        ${removeButton}
      </div>
      ${destinationChoiceMarkup(stage, configured, syncState, previousReady)}
      ${configured ? `<code>${escapeHtml(configured.repository_path)}</code>` : ""}
      ${receiptMarkup((chain.receipts || {})[stage.edge])}
      ${previousReady && !(configured && configured.local_only) ? createRepositoryMarkup(stage, settings) : ""}
      ${previousReady ? "" : '<p>Configure the previous stage first.</p>'}
      ${syncButton}
    </section>
  `;
}

// Renders the selected chain editor or a clear empty state when no chain exists.
function renderEditor(syncState, settings, activeChainId) {
  const editor = byId("sync-chain-editor");
  const chain = (syncState.chains || []).find((item) => item.id === activeChainId) || null;
  if (!chain) {
    editor.innerHTML = '<div class="empty-state">Select or create a Sync Chain</div>';
    return;
  }
  const project = projectForChain(syncState, chain);
  setText("sync-chain-summary", project ? `${project.name} promotion chain` : "Missing Local Mode project");
  editor.innerHTML = `
    <div class="sync-chain-editor-header">
      <div>
        <small>Local Mode source</small>
        <h3>${escapeHtml(project ? project.name : "Missing project")}</h3>
        <code>${escapeHtml(chain.project_path)}</code>
      </div>
      <button id="delete-sync-chain" class="sync-chain-danger" type="button"
        data-chain-id="${escapeHtml(chain.id)}">Delete chain</button>
    </div>
    ${localSourceMarkup(project, chain, settings)}
    <div class="sync-chain-flow">
      ${STAGES.map((stage) => stageMarkup(stage, chain, syncState, settings)).join("")}
    </div>
  `;
}

// Renders every page surface from one backend-owned state snapshot.
function render(syncState, settings, activeChainId, notifications = []) {
  renderProjectChoices(syncState);
  renderChainList(syncState, activeChainId, notifications);
  renderEditor(syncState, settings || {}, activeChainId);
}

window.GitDeskSyncChainRender = { render, renderChainList, stages: STAGES };
})();
