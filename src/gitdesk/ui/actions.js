/*
  GitHub Actions panel manager with live build polling and elapsed timers.
*/

// Keeps workflow polling isolated from the main app controller.
(() => {
const renderHelpers = window.GitDeskRender;
const detailRenderer = window.GitDeskActionsDetail;
const refreshHelpers = window.GitDeskActionsRefresh;

if (!renderHelpers || !detailRenderer || !refreshHelpers) {
  throw new Error("GitDesk Actions dependencies did not load.");
}

const { byId, setText } = renderHelpers;
let runActionRef = null;
let githubPayloadRef = null;
let refreshCoordinator = null;
const state = {
  loaded: false,
  loading: false,
  refreshQueued: false,
  runs: [],
  selectedRunId: "",
  detailVisible: false,
  detailLoading: false,
  detailRequestId: 0,
};

// Injects the small amount of Actions-specific styling needed for live build status.
function injectStyles() {
  if (document.getElementById("actions-style")) return;
  const style = document.createElement("style");
  style.id = "actions-style";
  style.textContent = `
    .run-spinner{width:14px;height:14px;border:2px solid var(--line);border-top-color:var(--green)}
    .run-spinner{display:inline-block;border-radius:50%;animation:gitdesk-spin .8s linear infinite}
    @keyframes gitdesk-spin{to{transform:rotate(360deg)}}
  `;
  document.head.appendChild(style);
}

// Escapes workflow metadata before rendering it into the Actions panel.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function hasRepositoryConfig() {
  const payload = githubPayloadRef ? githubPayloadRef() : {};
  return Boolean(payload && payload.owner && payload.repo);
}

// Adds the selected run and terminal-state hint to the authenticated detail request.
function detailPayload(runId) {
  const payload = githubPayloadRef();
  payload.run_id = runId;
  payload.run_completed = Boolean(selectedRun() && selectedRun().status === "completed");
  return payload;
}

// Returns the currently selected workflow run from the loaded history list.
function selectedRun() {
  return state.runs.find((run) => String(run.id) === state.selectedRunId) || null;
}

function isActiveRun(run) {
  return run && run.status && run.status !== "completed";
}

function statusLabel(run) {
  if (isActiveRun(run)) {
    return run.status === "in_progress" ? "building" : run.status;
  }
  return "complete";
}

function statusClass(run) {
  if (isActiveRun(run)) return "building";
  if (run.conclusion === "success") return "success";
  return run.conclusion ? "danger" : "warning";
}

function timestamp(value) {
  const parsed = Date.parse(value || "");
  return Number.isNaN(parsed) ? 0 : parsed;
}

function elapsedMs(run) {
  const start = timestamp(run.run_started_at) || timestamp(run.created_at);
  const end = isActiveRun(run) ? Date.now() : timestamp(run.updated_at);
  return start ? Math.max(0, (end || Date.now()) - start) : 0;
}

function formatElapsed(ms) {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const remainder = String(seconds % 60).padStart(2, "0");
  if (minutes >= 60) {
    const hours = Math.floor(minutes / 60);
    return `${hours}h ${String(minutes % 60).padStart(2, "0")}m`;
  }
  return `${minutes}m ${remainder}s`;
}

// Updates elapsed labels without re-rendering workflow rows.
function updateElapsedLabels() {
  state.runs.forEach((run) => {
    const element = document.querySelector(`[data-run-elapsed="${run.id}"]`);
    if (element) {
      element.textContent = formatElapsed(elapsedMs(run));
    }
  });
}

// Keeps the Actions header aligned with either history mode or one selected detail page.
function updateActionsSummary() {
  const activeCount = state.runs.filter(isActiveRun).length;
  const run = selectedRun();
  if (state.detailVisible && run) {
    setText("actions-summary", `${run.name} #${run.run_number}`);
    return;
  }
  const summary = activeCount ? `${activeCount} building - ${state.runs.length} workflow runs` : "";
  setText("actions-summary", summary || `${state.runs.length} workflow runs`);
}

// Marks the selected workflow row without replacing the list during click handling.
function markSelectedRun() {
  document.querySelectorAll(".run-open").forEach((button) => {
    button.classList.toggle("active", String(button.dataset.runId || "") === state.selectedRunId);
  });
}

// Shows the history list as the Actions landing view.
function showRunHistory() {
  state.detailVisible = false;
  state.detailLoading = false;
  state.detailRequestId += 1;
  byId("workflow-runs").hidden = false;
  detailRenderer.hide();
  markSelectedRun();
  updateActionsSummary();
}

// Shows the selected run detail page and hides the history list.
function showRunDetail(run) {
  state.detailVisible = true;
  byId("workflow-runs").hidden = true;
  detailRenderer.renderLoading(run);
  updateActionsSummary();
}

// Renders the Actions panel from the latest workflow payload.
function renderRuns(payload) {
  state.loaded = true;
  state.runs = payload && payload.runs ? payload.runs : [];
  if (window.GitDeskReleaseAlerts) {
    window.GitDeskReleaseAlerts.syncWorkflowRuns(state.runs);
  }
  if (window.GitDeskActionJingles) {
    window.GitDeskActionJingles.syncRuns(state.runs);
  }
  updateActionsSummary();

  const list = byId("workflow-runs");
  if (!state.runs.length) {
    list.innerHTML = '<div class="empty-state">No workflow runs loaded</div>';
    state.selectedRunId = "";
    state.detailVisible = false;
    list.hidden = false;
    detailRenderer.reset();
    refreshCoordinator.sync(state.runs);
    return;
  }

  if (state.detailVisible && !state.runs.some((run) => String(run.id) === state.selectedRunId)) {
    showRunHistory();
  }

  list.innerHTML = state.runs.map((run) => {
    const active = isActiveRun(run);
    const selected = String(run.id) === state.selectedRunId;
    const spinner = active ? '<span class="run-spinner" aria-hidden="true"></span>' : "";
    const conclusion = run.conclusion ? ` - ${escapeHtml(run.conclusion)}` : "";
    return `
      <button class="run-row run-open ${active ? "running" : ""} ${selected ? "active" : ""}"
        type="button" data-run-id="${escapeHtml(run.id)}">
        <div class="run-copy">
          <div class="run-title-line">
            ${spinner}
            <span class="row-title">${escapeHtml(run.name)}</span>
          </div>
          <div class="row-meta">
            ${escapeHtml(run.branch)} ${escapeHtml(run.event)} #${escapeHtml(run.run_number)}
          </div>
          <div class="row-meta">${escapeHtml(run.message || run.display_title || "")}</div>
        </div>
        <div class="run-status-line">
          <span class="run-duration" data-run-elapsed="${escapeHtml(run.id)}">
            ${escapeHtml(formatElapsed(elapsedMs(run)))}
          </span>
          <span class="status-pill ${statusClass(run)}">${escapeHtml(statusLabel(run))}${conclusion}</span>
        </div>
      </button>
    `;
  }).join("");
  markSelectedRun();
  refreshCoordinator.sync(state.runs);
  if (state.detailVisible && !state.detailLoading) {
    refreshRunDetail(state.selectedRunId, { quiet: true }).catch(() => {});
  }
}

// Shows a loading row while the first Actions request is in flight.
function renderLoading() {
  state.detailVisible = false;
  byId("workflow-runs").hidden = false;
  detailRenderer.hide();
  setText("actions-summary", "Loading workflow runs");
  byId("workflow-runs").innerHTML = `
    <div class="run-row running">
      <div class="run-copy">
        <div class="run-title-line">
          <span class="run-spinner" aria-hidden="true"></span>
          <span class="row-title">Loading workflow runs</span>
        </div>
      </div>
    </div>
  `;
}

// Shows a safe Actions error inside the panel when quiet startup/polling cannot load runs.
function renderError(error) {
  const message = error && error.message ? error.message : "Workflow runs could not be loaded.";
  state.detailVisible = false;
  byId("workflow-runs").hidden = false;
  detailRenderer.hide();
  setText("actions-summary", "Workflow runs unavailable");
  byId("workflow-runs").innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
  refreshCoordinator.sync(state.runs);
}

// Loads workflow runs, optionally quietly for startup and polling.
async function refreshRuns(options = {}) {
  if (state.loading) {
    if (options.queueIfBusy) state.refreshQueued = true;
    return;
  }
  if (!hasRepositoryConfig()) {
    state.runs = [];
    state.selectedRunId = "";
    state.detailVisible = false;
    setText("actions-summary", "Select a GitHub repository to load Actions");
    byId("workflow-runs").hidden = false;
    byId("workflow-runs").innerHTML = '<div class="empty-state">No GitHub repository selected</div>';
    detailRenderer.reset();
    refreshCoordinator.sync(state.runs);
    refreshCoordinator.refreshSettled();
    return;
  }

  state.loading = true;
  if (!options.quiet && !state.loaded) {
    renderLoading();
  }
  try {
    const payload = await runActionRef(
      "listWorkflowRuns",
      githubPayloadRef(),
      options.quiet ? "" : "Workflow runs refreshed",
      { quiet: Boolean(options.quiet) },
    );
    renderRuns(payload);
  } catch (error) {
    if (options.surfaceErrors) {
      renderError(error);
    }
    if (!options.quiet) throw error;
  } finally {
    state.loading = false;
    if (state.refreshQueued) {
      state.refreshQueued = false;
      window.setTimeout(() => refreshRuns({ quiet: true }), 0);
    } else {
      refreshCoordinator.refreshSettled();
    }
  }
}

// Loads the selected run's jobs, artifacts, and annotations.
async function refreshRunDetail(runId, options = {}) {
  if (!runId || !hasRepositoryConfig()) {
    return;
  }
  state.detailRequestId += 1;
  const requestId = state.detailRequestId;
  state.detailLoading = true;
  if (!options.quiet) {
    detailRenderer.renderLoading(selectedRun());
  }
  try {
    const detail = await runActionRef(
      "workflowRunDetails",
      detailPayload(runId),
      options.quiet ? "" : "Workflow detail refreshed",
      { quiet: Boolean(options.quiet) },
    );
    if (requestId === state.detailRequestId && state.detailVisible) {
      detailRenderer.renderDetail(detail, selectedRun());
      updateActionsSummary();
    }
  } catch (error) {
    if (requestId === state.detailRequestId && state.detailVisible) {
      detailRenderer.renderError(error);
    }
    if (!options.quiet) throw error;
  } finally {
    if (requestId === state.detailRequestId) {
      state.detailLoading = false;
    }
  }
}

// Handles clicks on workflow runs and opens the selected run's live detail panel.
function openRunDetail(event) {
  const button = event.target.closest(".run-open");
  if (!button) {
    return;
  }
  state.selectedRunId = String(button.dataset.runId || "");
  const run = selectedRun();
  if (!run) {
    return;
  }
  markSelectedRun();
  showRunDetail(run);
  refreshRunDetail(state.selectedRunId).catch(() => {});
}

// Clears loaded runs when the active repository/account context changes.
function reset() {
  state.loaded = false;
  state.refreshQueued = false;
  state.runs = [];
  state.selectedRunId = "";
  state.detailVisible = false;
  state.detailRequestId += 1;
  setText("actions-summary", "No workflow runs loaded");
  byId("workflow-runs").hidden = false;
  byId("workflow-runs").innerHTML = '<div class="empty-state">No workflow runs loaded</div>';
  detailRenderer.reset();
  if (window.GitDeskActionJingles) window.GitDeskActionJingles.resetRuns();
  refreshCoordinator.reset();
}

// Reconciles Actions against the exact pushed revision while GitHub creates its run record.
function refreshAfterPush(commitSha) {
  refreshCoordinator.notePush(commitSha);
}

// Binds Actions controls after the main app provides native action helpers.
function bind(options) {
  runActionRef = options.runAction;
  githubPayloadRef = options.githubPayload;
  refreshCoordinator = refreshHelpers.create({
    isActiveRun,
    refresh: refreshRuns,
    updateElapsedLabels,
  });
  injectStyles();
  detailRenderer.install({ onBack: showRunHistory, runAction: runActionRef, githubPayload: githubPayloadRef });
  byId("refresh-actions").addEventListener("click", () => refreshRuns({ queueIfBusy: true }));
  byId("workflow-runs").addEventListener("click", openRunDetail);
  document.querySelector('.tab-button[data-tab="actions"]').addEventListener("click", () => {
    window.setTimeout(() => refreshRuns({ quiet: state.loaded, queueIfBusy: true }), 0);
  });
}

// Publishes the Actions API used by app bootstrap and push workflows.
window.GitDeskActions = {
  bind,
  refreshAfterPush,
  refreshOnLoad() {
    refreshRuns({ quiet: true, surfaceErrors: true });
  },
  reset,
};
})();
