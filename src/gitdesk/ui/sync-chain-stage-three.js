/*
  Post-release Stage 3 continuation dialog for configured Public destinations.
*/

// Keeps release continuation state separate from the main Sync Chain setup controller.
(() => {
const renderHelpers = window.GitDeskRender;
const artifactJobs = window.GitDeskSyncChainArtifactJob;

if (!renderHelpers || !artifactJobs) throw new Error("GitDesk Stage 3 prompt dependencies did not load.");

const { appendActivity, byId } = renderHelpers;
const state = { pending: null, busy: false, previousFocus: null };

// Inserts one body-level modal so it cannot be clipped by a repository panel.
function injectModal() {
  if (document.getElementById("sync-stage-three-modal")) return;
  document.body.insertAdjacentHTML("beforeend", `
    <section id="sync-stage-three-modal" class="sync-stage-three-modal" hidden>
      <div class="sync-stage-three-dialog" role="dialog" aria-modal="true"
        aria-labelledby="sync-stage-three-title" aria-describedby="sync-stage-three-description">
        <header class="sync-stage-three-header">
          <span class="sync-stage-three-symbol" aria-hidden="true"></span>
          <div>
            <small>Stage 2 release published</small>
            <h2 id="sync-stage-three-title">Continue to Stage 3?</h2>
            <p id="sync-stage-three-description"></p>
          </div>
          <button id="close-sync-stage-three" type="button" aria-label="Close Stage 3 prompt">Close</button>
        </header>
        <div class="sync-stage-three-release">
          <span>Published release</span>
          <strong id="sync-stage-three-tag"></strong>
          <small>Public Beta <span aria-hidden="true">→</span> Public</small>
        </div>
        <label class="sync-stage-three-mode">
          <input id="sync-stage-three-artifacts" type="checkbox">
          <span>
            <strong>Built artifacts only</strong>
            <small id="sync-stage-three-mode-copy"></small>
          </span>
          <span id="sync-stage-three-mode-state" class="status-pill"></span>
        </label>
        <p id="sync-stage-three-status" class="sync-stage-three-status" role="status" aria-live="polite"></p>
        <footer class="sync-stage-three-actions">
          <button id="defer-sync-stage-three" type="button">Not now</button>
          <button id="confirm-sync-stage-three" type="button">Sync to Stage 3</button>
        </footer>
      </div>
    </section>
  `);
}

// Updates the explicit source-code boundary whenever the persisted checkbox changes.
function renderMode() {
  const checked = byId("sync-stage-three-artifacts").checked;
  const eligible = Boolean(state.pending && state.pending.artifactReleaseEligible);
  const modeState = byId("sync-stage-three-mode-state");
  modeState.textContent = checked ? "Enabled" : "Disabled";
  modeState.className = `status-pill ${checked ? "success" : ""}`;
  if (checked && eligible) {
    byId("sync-stage-three-mode-copy").textContent =
      "Only this release's attached assets will be published. Source code stays out of Public.";
  } else if (checked) {
    byId("sync-stage-three-mode-copy").textContent =
      "Artifact sync requires the release to be a full release published as latest.";
  } else {
    byId("sync-stage-three-mode-copy").textContent =
      "Stage 3 will use working-tree sync, which includes source files.";
  }
  byId("confirm-sync-stage-three").disabled = state.busy || (checked && !eligible);
}

// Keeps all modal controls consistent while a saved mode or Stage 3 sync is unresolved.
function renderBusy() {
  byId("sync-stage-three-artifacts").disabled = state.busy;
  byId("close-sync-stage-three").disabled = state.busy;
  byId("defer-sync-stage-three").disabled = state.busy;
  renderMode();
}

// Formats byte progress without implying a transfer speed or completion estimate the backend cannot prove.
function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value >= 1024 * 1024 * 1024) return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

// Converts a backend phase into one compact live status without injecting remote asset names as markup.
function renderJobProgress(progress = {}) {
  const message = String(progress.message || "Synchronizing Stage 3");
  const assetIndex = Number(progress.asset_index || 0);
  const assetCount = Number(progress.asset_count || 0);
  const transferred = Number(progress.bytes_transferred || 0);
  const total = Number(progress.bytes_total || 0);
  const assetText = assetIndex > 0 && assetCount > 0 ? ` · artifact ${assetIndex} of ${assetCount}` : "";
  const byteText = total > 0 ? ` · ${formatBytes(transferred)} of ${formatBytes(total)}` : "";
  byId("sync-stage-three-status").textContent = `${message}${assetText}${byteText}`;
}

// Closes the prompt without changing Stage 3 or the user's saved checkbox mode.
function close() {
  if (state.busy || !state.pending) return;
  byId("sync-stage-three-modal").hidden = true;
  state.pending = null;
  if (state.previousFocus && typeof state.previousFocus.focus === "function") state.previousFocus.focus();
}

// Opens only for a release published from a configured Public Beta repository with a Public stage.
function prompt(repositoryPath, release, options = {}) {
  const manager = window.GitDeskSyncChains;
  const chain = manager && manager.chainForPublicBeta(repositoryPath);
  if (!chain) return false;
  const tagName = String((release && release.tag_name) || options.tagName || "").trim();
  if (!tagName) return false;
  state.pending = {
    projectPath: chain.project_path,
    tagName,
    artifactReleaseEligible: options.artifactReleaseEligible === true,
  };
  state.previousFocus = document.activeElement;
  byId("sync-stage-three-description").textContent =
    "This project has a configured Public destination. Review the final sync mode before continuing.";
  byId("sync-stage-three-tag").textContent = tagName;
  byId("sync-stage-three-artifacts").checked = Boolean(chain.public_artifacts_only);
  byId("sync-stage-three-status").textContent = "";
  byId("sync-stage-three-modal").hidden = false;
  renderBusy();
  byId("confirm-sync-stage-three").focus();
  return true;
}

// Saves checkbox changes immediately, including when the user closes the prompt without syncing.
async function saveMode() {
  if (!state.pending || state.busy) return;
  const input = byId("sync-stage-three-artifacts");
  const requested = input.checked;
  state.busy = true;
  byId("sync-stage-three-status").textContent = "Saving Stage 3 mode…";
  renderBusy();
  try {
    await window.GitDeskSyncChains.configureProjectArtifactSync(
      state.pending.projectPath,
      "public_beta_to_public",
      requested,
    );
    byId("sync-stage-three-status").textContent = requested
      ? "Artifact-only mode saved."
      : "Working-tree mode saved.";
  } catch (error) {
    const chain = window.GitDeskSyncChains.chainForProject(state.pending.projectPath);
    input.checked = Boolean(chain && chain.public_artifacts_only);
    byId("sync-stage-three-status").textContent = error.message || "Stage 3 mode could not be saved.";
  } finally {
    state.busy = false;
    renderBusy();
  }
}

// Advances the exact prompted release to Public after the saved mode has been reviewed.
async function confirm() {
  if (!state.pending || state.busy || byId("confirm-sync-stage-three").disabled) return;
  state.busy = true;
  byId("sync-stage-three-status").textContent = "Preparing Stage 3 transfer…";
  renderBusy();
  try {
    const manager = window.GitDeskSyncChains;
    if (!byId("sync-stage-three-artifacts").checked) {
      await manager.syncProjectEdge(
        state.pending.projectPath,
        "public_beta_to_public",
        { expectedReleaseTag: state.pending.tagName },
      );
      appendActivity(`Stage 3 synchronized from release ${state.pending.tagName}`);
      state.busy = false;
      close();
      return;
    }
    const chain = manager.chainForProject(state.pending.projectPath);
    if (!chain) throw new Error("The selected Local Mode project has no Sync Chain.");
    const data = await artifactJobs.run(
      chain.id,
      "public_beta_to_public",
      state.pending.tagName,
      renderJobProgress,
    );
    manager.applyCompletedSync(data);
    appendActivity(`Stage 3 synchronized from release ${state.pending.tagName}`);
    state.busy = false;
    close();
  } catch (error) {
    state.busy = false;
    byId("sync-stage-three-status").textContent = error.message || "Stage 3 synchronization failed.";
    renderBusy();
  }
}

// Provides conventional backdrop, Escape, and contained Tab-key behavior.
function handleModalInteraction(event) {
  const modal = byId("sync-stage-three-modal");
  if (!state.pending || modal.hidden) return;
  if (event.type === "click" && (event.target === modal || event.target.id === "close-sync-stage-three"
      || event.target.id === "defer-sync-stage-three")) {
    close();
    return;
  }
  if (event.type === "keydown" && event.key === "Escape") {
    close();
    return;
  }
  if (event.type !== "keydown" || event.key !== "Tab") return;
  const controls = [...modal.querySelectorAll("button:not(:disabled), input:not(:disabled)")];
  if (!controls.length) return;
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

// Installs stable controls after the document body exists.
function init() {
  injectModal();
  byId("sync-stage-three-artifacts").addEventListener("change", () => saveMode().catch(() => {}));
  byId("confirm-sync-stage-three").addEventListener("click", () => confirm().catch(() => {}));
  byId("sync-stage-three-modal").addEventListener("click", handleModalInteraction);
  document.addEventListener("keydown", handleModalInteraction);
}

window.GitDeskSyncStageThree = { prompt };
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
else init();
})();
