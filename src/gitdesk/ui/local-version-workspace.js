/*
  Selected-version action dock and inline configured-stage promotion rendering.
*/

// Keeps the inspector-specific workspace outside the near-limit Local Mode renderer.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk selected-version workspace dependencies did not load.");
}

const { byId } = renderHelpers;
const PROMOTION_PROGRESS_LABELS = Object.freeze({
  local_to_private_beta: "Syncing selected version to Private Beta…",
  private_beta_to_public_beta: "Syncing Private Beta to Public Beta…",
  public_beta_to_public: "Syncing Public Beta to Public…",
});

// Escapes repository account values before inserting them into the promotion rail.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Returns the complete selected-version action mount used by Local Mode markup injection.
function actionMarkup() {
  return `
    <div class="local-version-detail-actions">
      <div class="local-version-core-actions" role="group" aria-label="Primary version actions">
        <button id="duplicate-local-version" type="button"
          aria-label="Create new version" title="Create new version"></button>
        <button id="open-local-folder" type="button"
          aria-label="Open version folder" title="Open version folder"></button>
        <button id="open-local-vscode" type="button"
          data-editor-aria-template="Open version in {editor}"
          data-editor-tooltip-template="Open version in {editor}"></button>
      </div>
      <details class="local-version-more-actions">
        <summary>More tools</summary>
        <div class="local-version-icon-dock" role="toolbar" aria-label="More version actions">
          <button id="name-local-v1" class="local-rename-icon" type="button"
            aria-label="Rename v1 folder" title="Rename v1 folder" hidden></button>
          <button id="open-local-notes" type="button" aria-haspopup="dialog"
            aria-controls="local-notes-modal" aria-expanded="false"
            aria-label="Project Markdown notes" title="Project Markdown notes"></button>
          <button id="sync-local-private-beta" type="button"
            aria-label="Sync selected version to Private Beta"
            title="Sync selected version to Private Beta"></button>
          <button id="open-sync-ignore" type="button" aria-haspopup="dialog"
            aria-controls="sync-ignore-dialog" aria-expanded="false"
            aria-label="Edit Sync Ignore" title="Edit Sync Ignore"></button>
          <button id="manage-local-shared-resources" type="button"
            aria-label="Manage Shared Resources" title="Manage Shared Resources"></button>
        </div>
      </details>
      <div id="local-version-sync-rail" class="local-version-sync-rail" hidden></div>
    </div>
  `;
}

// Describes the last completed edge without treating a receipt as stage availability.
function receiptLabel(receipt) {
  if (!receipt) {
    return "Not synced";
  }
  const count = Number(receipt.file_count || 0);
  if (receipt.sync_mode === "release_artifacts") {
    const tag = receipt.release_tag ? ` · ${receipt.release_tag}` : "";
    return `${count} artifact${count === 1 ? "" : "s"} published${tag}`;
  }
  return `${count} file${count === 1 ? "" : "s"} synced`;
}

// Builds one promotion stage with repository ownership and receipt context.
function stageMarkup(label, stage, receipt, terminal, optionMarkup = "", notification = false) {
  const account = stage && stage.local_only ? "Local folder" : stage && stage.account_login ? stage.account_login : "";
  const status = receipt ? receiptLabel(receipt) : terminal ? "Destination" : "Not synced";
  return `
    <div class="local-promotion-stage${receipt ? " complete" : ""}${optionMarkup ? " with-option" : ""}
      ${notification ? " has-notification" : ""}">
      <span class="local-promotion-dot" aria-hidden="true"></span>
      ${notification ? `<span class="local-sync-change-dot" role="img"
        aria-label="Unsynced local changes detected" title="Unsynced local changes detected"></span>` : ""}
      <div class="local-promotion-stage-title">
        <strong>${escapeHtml(label)}</strong>
        ${optionMarkup}
      </div>
      <small>${escapeHtml(account || status)}</small>
      ${account ? `<span>${escapeHtml(status)}</span>` : ""}
    </div>
  `;
}

// Renders the Public destination's saved source-free publication mode inside its stage.
function artifactOptionMarkup(chain, edge, disabled) {
  const checked = chain.artifact_only_edge === edge ? "checked" : "";
  return `
    <label class="local-promotion-artifact-option"
      title="Publish only the source stage's latest release assets">
      <input type="checkbox" data-local-artifacts-only data-edge="${escapeHtml(edge)}"
        ${checked} ${disabled ? "disabled" : ""}>
      <span>Built artifacts only</span>
    </label>
  `;
}

// Builds one icon-only edge action between two visible promotion stages.
function edgeButton(edge, label, disabled, complete, pendingEdge) {
  const icon = (window.GitDeskIcons || {}).sync || "";
  const pending = edge === pendingEdge;
  const accessibleLabel = pending
    ? PROMOTION_PROGRESS_LABELS[edge]
    : complete ? `Step 1 complete. ${label}` : label;
  return `
    <button class="local-promotion-edge${complete ? " complete" : ""}${pending ? " is-syncing" : ""}"
      type="button" aria-busy="${pending}"
      data-local-sync-edge="${escapeHtml(edge)}" aria-label="${escapeHtml(accessibleLabel)}"
      title="${escapeHtml(accessibleLabel)}" ${disabled || pendingEdge ? "disabled" : ""}>
      ${icon}
    </button>
  `;
}

// Renders every configured repository stage, including the optional final Public edge.
function render(localState, project, version) {
  const rail = byId("local-version-sync-rail");
  const syncManager = window.GitDeskSyncChains;
  const chain = syncManager && project
    ? syncManager.chainForProject(localState.active_project)
    : null;
  const stages = chain ? chain.stages || {} : {};
  const receipts = chain ? chain.receipts || {} : {};
  const hasTwoSteps = Boolean(stages.private_beta && stages.public_beta);
  const hasPublic = Boolean(stages.public);
  const actionManager = window.GitDeskLocalVersionActions;
  const pendingEdge = actionManager ? actionManager.currentPendingPromotionEdge() : "";
  rail.hidden = !hasTwoSteps;
  rail.setAttribute("aria-busy", String(Boolean(pendingEdge)));
  if (!hasTwoSteps) {
    rail.innerHTML = "";
    return;
  }
  const localReceipt = receipts.local_to_private_beta;
  const publicBetaReceipt = receipts.private_beta_to_public_beta;
  const publicReceipt = receipts.public_beta_to_public;
  const selectedReceipt = localReceipt && version && localReceipt.source_path === version.path
    ? localReceipt
    : null;
  // Step 1 is current only for this version and only until the next ordered edge succeeds.
  const firstStepComplete = Boolean(selectedReceipt && !publicBetaReceipt);
  const middleAction = chain.artifact_only_edge === "private_beta_to_public_beta"
    ? "Publish Private Beta release artifacts to Public Beta"
    : "Sync Private Beta to Public Beta";
  const finalAction = chain.artifact_only_edge === "public_beta_to_public"
    ? "Publish Public Beta release artifacts to Public"
    : "Sync Public Beta to Public";
  const finalStageMarkup = hasPublic ? `
    ${edgeButton("public_beta_to_public", finalAction, false, false, pendingEdge)}
    ${stageMarkup("Public", stages.public, publicReceipt, true,
      artifactOptionMarkup(chain, "public_beta_to_public", pendingEdge))}
  ` : "";
  rail.innerHTML = `
    <div class="local-promotion-heading">
      <span>Sync chain</span>
      <small aria-live="polite">${escapeHtml(
        PROMOTION_PROGRESS_LABELS[pendingEdge]
          || `Run ${hasPublic ? "all three" : "both"} configured steps here`,
      )}</small>
    </div>
    <div class="local-promotion-flow${hasPublic ? " has-public" : ""}"
      aria-label="Selected version promotion chain">
      ${stageMarkup(
        "Selected version",
        null,
        selectedReceipt,
        false,
        "",
        syncManager.hasProjectNotification(localState.active_project),
      )}
      ${edgeButton(
        "local_to_private_beta",
        "Sync selected version to Private Beta",
        !version,
        firstStepComplete,
        pendingEdge,
      )}
      ${stageMarkup("Private Beta", stages.private_beta, localReceipt, false)}
      ${edgeButton(
        "private_beta_to_public_beta",
        middleAction,
        false,
        false,
        pendingEdge,
      )}
      ${stageMarkup("Public Beta", stages.public_beta, publicBetaReceipt, !hasPublic,
        !hasPublic && !stages.private_beta.local_only && !stages.public_beta.local_only
          ? artifactOptionMarkup(chain, "private_beta_to_public_beta", pendingEdge)
          : "")}
      ${finalStageMarkup}
    </div>
  `;
}

window.GitDeskLocalVersionWorkspace = { actionMarkup, render };
})();
