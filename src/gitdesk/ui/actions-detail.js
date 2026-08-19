// Keeps the selected run detail view separate from the run history controller.
(() => {
const renderHelpers = window.GitDeskRender;
const issuesRenderer = window.GitDeskActionsIssues;
const stepLogsRenderer = window.GitDeskActionsStepLogs;
const deploymentRenderer = window.GitDeskActionsDeployment;

if (!renderHelpers || !issuesRenderer || !stepLogsRenderer || !deploymentRenderer) {
  throw new Error("GitDesk Actions detail dependencies did not load.");
}

const { byId } = renderHelpers;
let installed = false;
let backHandler = null;
const state = {
  detail: null,
  run: null,
  selectedKey: "",
};

// Escapes GitHub Actions names and annotation text before rendering dynamic markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Returns the single detail container created beside the workflow history list.
function detailElement() {
  return byId("workflow-run-detail");
}

// Converts an optional GitHub timestamp into milliseconds for duration math.
function timestamp(value) {
  const parsed = Date.parse(value || "");
  return Number.isNaN(parsed) ? 0 : parsed;
}

// Identifies queued or running jobs whose completion time should continue advancing.
function isActive(item) {
  return item && item.status && item.status !== "completed";
}

// Maps GitHub job state to the shared visual status classes.
function statusClass(item) {
  if (isActive(item)) return "building";
  if (item && item.conclusion === "success") return "success";
  return item && item.conclusion ? "danger" : "warning";
}

// Produces the concise job state label displayed in headers and navigation.
function statusLabel(item) {
  if (!item) return "queued";
  if (isActive(item)) return item.status === "in_progress" ? "building" : item.status;
  return item.conclusion || "complete";
}

// Computes job duration from reported timestamps while keeping active jobs live.
function elapsedMs(item) {
  const start = timestamp(item && item.started_at);
  const end = isActive(item) ? Date.now() : timestamp(item && item.completed_at);
  return start ? Math.max(0, (end || Date.now()) - start) : 0;
}

// Formats elapsed milliseconds as compact minutes/seconds or hours/minutes.
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

// Formats artifact byte counts into the smallest readable binary unit.
function formatSize(bytes) {
  const size = Number(bytes || 0);
  if (size >= 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  if (size >= 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${size} B`;
}

// Formats GitHub timestamps in the user's local desktop locale.
function formatDateTime(value) {
  const parsed = new Date(value || "");
  return Number.isNaN(parsed.getTime()) ? "Not reported" : parsed.toLocaleString();
}

// Returns the selected run's current serialized jobs.
function jobs() {
  return state.detail && state.detail.jobs ? state.detail.jobs : [];
}

// Returns the selected run's current serialized artifacts.
function artifacts() {
  return state.detail && state.detail.artifacts ? state.detail.artifacts : [];
}

// Builds collision-free sidebar keys across job and artifact id namespaces.
function itemKey(type, item) {
  return `${type}:${String(item && item.id ? item.id : "")}`;
}

// Picks the first meaningful detail item rather than showing every job at once.
function defaultKey() {
  const activeJob = jobs().find(isActive);
  if (activeJob) return itemKey("job", activeJob);
  if (jobs().length) return itemKey("job", jobs()[0]);
  if (artifacts().length) return itemKey("artifact", artifacts()[0]);
  return "summary";
}

// Confirms a preserved selection still exists after live detail refresh.
function hasKey(key) {
  if (key === "summary") return true;
  return Boolean(findJob(key) || findArtifact(key));
}

// Resolves a job navigation key to its current live record.
function findJob(key) {
  return jobs().find((job) => itemKey("job", job) === key) || null;
}

// Resolves an artifact navigation key to its current live record.
function findArtifact(key) {
  return artifacts().find((artifact) => itemKey("artifact", artifact) === key) || null;
}

// Renders one left-navigation button for a job, artifact, or summary item.
function navButton(key, label, item, detail) {
  const active = key === state.selectedKey ? " active" : "";
  const status = detail || (item ? statusLabel(item) : "");
  const dotClass = detail === "expired" ? "danger" : detail === "uploaded" ? "success" : statusClass(item);
  return `
    <button class="actions-detail-nav-button${active}" type="button"
      data-action-detail-key="${escapeHtml(key)}">
      <span class="actions-status-dot ${dotClass}"></span>
      <span>${escapeHtml(label)}</span>
      <small>${escapeHtml(status || "")}</small>
    </button>
  `;
}

// Renders the left side menu of jobs and uploaded artifacts.
function renderSidebar() {
  const jobButtons = jobs().map((job) => navButton(itemKey("job", job), job.name, job, ""));
  const artifactButtons = artifacts().map((artifact) => {
    const label = artifact.expired ? "expired" : "uploaded";
    return navButton(itemKey("artifact", artifact), artifact.name, artifact, label);
  });
  return `
    <aside class="actions-detail-sidebar">
      <button class="actions-back" type="button">Back to runs</button>
      <nav class="actions-detail-nav" aria-label="Workflow run detail">
        ${navButton("summary", "Summary", null, `${jobs().length} jobs`)}
        <span class="actions-nav-label">Jobs</span>
        ${jobButtons.length ? jobButtons.join("") : '<span class="actions-empty-nav">No jobs yet</span>'}
        <span class="actions-nav-label">Artifacts</span>
        ${artifactButtons.length ? artifactButtons.join("") : '<span class="actions-empty-nav">No artifacts yet</span>'}
      </nav>
    </aside>
  `;
}

// Renders compact run-level metadata.
function renderSummaryPane() {
  const completed = jobs().filter((job) => job.status === "completed").length;
  const warningCount = state.detail && state.detail.warning_count ? state.detail.warning_count : 0;
  const errorCount = state.detail && state.detail.error_count ? state.detail.error_count : 0;
  const annotationErrors = state.detail && state.detail.annotation_errors ? state.detail.annotation_errors : [];
  return `
    <section class="actions-detail-pane">
      <div class="actions-pane-header">
        <div>
          <h3>${escapeHtml(state.run ? state.run.name : "Workflow run")}</h3>
          <p>${escapeHtml(state.run ? state.run.message || state.run.display_title || "" : "")}</p>
        </div>
      </div>
      ${deploymentRenderer.render(state.detail ? state.detail.pages_deployment : null)}
      <div class="actions-stat-grid">
        <span><strong>${completed}/${jobs().length}</strong><small>jobs completed</small></span>
        <span><strong>${artifacts().length}</strong><small>artifacts</small></span>
        <span><strong>${warningCount} / ${errorCount}</strong><small>warnings / errors</small></span>
      </div>
      <h3>Warnings and errors</h3>
      <div class="annotation-list">
        ${issuesRenderer.renderAnnotations(issuesRenderer.allAnnotations(jobs()), annotationErrors)}
      </div>
    </section>
  `;
}

// Renders the selected job's steps and warnings in the right pane.
function renderJobPane(job) {
  const annotationErrors = job.annotation_error ? [{ job: job.name, message: job.annotation_error }] : [];
  return `
    <section class="actions-detail-pane">
      <div class="actions-pane-header">
        <div>
          <h3>${escapeHtml(job.name)}</h3>
          <p>${escapeHtml(job.runner_name || (job.labels || []).join(", ") || "Runner pending")}</p>
        </div>
        <span class="status-pill ${statusClass(job)}">${escapeHtml(statusLabel(job))}</span>
      </div>
      ${deploymentRenderer.render(state.detail ? state.detail.pages_deployment : null)}
      <div class="actions-stat-grid">
        <span><strong>${escapeHtml(formatElapsed(elapsedMs(job)))}</strong><small>duration</small></span>
        <span><strong>${escapeHtml(formatDateTime(job.started_at))}</strong><small>started</small></span>
        <span><strong>${escapeHtml(formatDateTime(job.completed_at))}</strong><small>completed</small></span>
      </div>
      <h3>Steps</h3>
      <div class="action-step-list">${stepLogsRenderer.render(job)}</div>
      <h3>Warnings and errors</h3>
      <div class="annotation-list">
        ${issuesRenderer.renderAnnotations(job.annotations || [], annotationErrors)}
      </div>
    </section>
  `;
}

// Renders one uploaded artifact's metadata in the right pane.
function renderArtifactPane(artifact) {
  const status = artifact.expired ? "expired" : "uploaded";
  return `
    <section class="actions-detail-pane">
      <div class="actions-pane-header">
        <div>
          <h3>${escapeHtml(artifact.name)}</h3>
          <p>${escapeHtml(formatSize(artifact.size))}</p>
        </div>
        <span class="status-pill ${artifact.expired ? "danger" : "success"}">${status}</span>
      </div>
      ${deploymentRenderer.render(state.detail ? state.detail.pages_deployment : null)}
      <div class="actions-stat-grid">
        <span><strong>${escapeHtml(formatDateTime(artifact.created_at))}</strong><small>created</small></span>
        <span><strong>${escapeHtml(formatDateTime(artifact.updated_at))}</strong><small>updated</small></span>
        <span><strong>${escapeHtml(formatDateTime(artifact.expires_at))}</strong><small>expires</small></span>
      </div>
      ${artifact.archive_download_url ? `
        <a class="actions-download-link" href="${escapeHtml(artifact.archive_download_url)}" target="_blank">
          Download artifact
        </a>
      ` : ""}
    </section>
  `;
}

// Renders the selected right pane.
function renderPane() {
  const job = findJob(state.selectedKey);
  if (job) return renderJobPane(job);
  const artifact = findArtifact(state.selectedKey);
  if (artifact) return renderArtifactPane(artifact);
  return renderSummaryPane();
}

// Renders the full detail page shell.
function renderShell() {
  const focusedToggle = document.activeElement
    ? document.activeElement.closest("[data-action-step-index]")
    : null;
  const focusedStepIndex = focusedToggle ? focusedToggle.dataset.actionStepIndex : "";
  detailElement().hidden = false;
  detailElement().innerHTML = `
    <div class="actions-detail-shell">
      ${renderSidebar()}
      ${renderPane()}
    </div>
  `;
  if (focusedStepIndex !== "") {
    const replacement = detailElement().querySelector(`[data-action-step-index="${focusedStepIndex}"]`);
    if (replacement) replacement.focus();
  }
}

// Handles internal clicks for the detail page.
function handleClick(event) {
  const backButton = event.target.closest(".actions-back");
  if (backButton && backHandler) {
    backHandler();
    return;
  }
  if (deploymentRenderer.handleClick(event)) {
    return;
  }
  const selectedJob = findJob(state.selectedKey);
  if (stepLogsRenderer.handleClick(event, selectedJob, renderShell)) {
    return;
  }
  const navButtonElement = event.target.closest("[data-action-detail-key]");
  if (!navButtonElement) {
    return;
  }
  state.selectedKey = navButtonElement.dataset.actionDetailKey || "summary";
  renderShell();
}

// Creates the detail container after the workflow run list.
function install(options) {
  backHandler = options && options.onBack ? options.onBack : backHandler;
  if (options && options.runAction && options.githubPayload) {
    deploymentRenderer.install(options.runAction);
    stepLogsRenderer.install(options);
  }
  let detail = document.getElementById("workflow-run-detail");
  if (!detail) {
    detail = document.createElement("div");
    detail.id = "workflow-run-detail";
    detail.className = "actions-detail";
    detail.hidden = true;
    byId("workflow-runs").after(detail);
  }
  if (!installed) {
    detail.addEventListener("click", handleClick);
    installed = true;
  }
}

// Hides the detail page without clearing the selected run state.
function hide() {
  install();
  detailElement().hidden = true;
}

// Clears the detail panel when repositories or accounts change.
function reset() {
  install();
  state.detail = null;
  state.run = null;
  state.selectedKey = "";
  stepLogsRenderer.reset();
  detailElement().hidden = true;
  detailElement().innerHTML = "";
}

// Shows a lightweight loading state for the selected run detail.
function renderLoading(run) {
  install();
  state.run = run || null;
  detailElement().hidden = false;
  detailElement().innerHTML = `
    <div class="actions-detail-loading">
      <button class="actions-back" type="button">Back to runs</button>
      <span class="run-spinner" aria-hidden="true"></span>
      <strong>Loading workflow detail</strong>
    </div>
  `;
}

// Shows a recoverable detail error without replacing the run list.
function renderError(error) {
  const message = error && error.message ? error.message : "Workflow detail could not be loaded.";
  detailElement().innerHTML = `
    <div class="actions-detail-loading">
      <button class="actions-back" type="button">Back to runs</button>
      <div class="empty-state">${escapeHtml(message)}</div>
    </div>
  `;
}

// Renders the complete selected-run detail payload returned by Python.
function renderDetail(detail, run) {
  const previousRunId = state.run ? String(state.run.id || "") : "";
  const nextRunId = run ? String(run.id || "") : "";
  state.detail = detail || {};
  state.run = run || null;
  if (previousRunId !== nextRunId || !hasKey(state.selectedKey)) {
    state.selectedKey = defaultKey();
  }
  renderShell();
}

// Publishes the renderer API used by actions.js.
window.GitDeskActionsDetail = {
  hide,
  install,
  renderDetail,
  renderError,
  renderLoading,
  reset,
};
})();
