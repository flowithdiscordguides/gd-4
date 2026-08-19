/*
  Project Hub rendering helpers.
*/

// Renders Project Hub state while keeping workflow actions in project-hub.js.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk Project Hub render dependencies did not load.");
}

const { byId, setValue } = renderHelpers;

// Escapes backend and filesystem values before inserting them into dynamic HTML.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Returns the active local version path from the latest hub state.
function activeVersionPath(state) {
  return state.hub && state.hub.active_version ? state.hub.active_version.path || "" : "";
}

// Mirrors fresh settings into shared managers that are already loaded.
function syncSharedSettings(settings) {
  if (!settings) return;
  if (window.GitDeskRepositories) window.GitDeskRepositories.applySettings(settings);
  if (window.GitDeskWorkspaceMode) window.GitDeskWorkspaceMode.applySettings(settings);
  if (document.getElementById("github-owner")) setValue("github-owner", settings.github_owner || "");
  if (document.getElementById("github-repo")) setValue("github-repo", settings.github_repo || "");
}

// Converts a status into the existing pill color vocabulary.
function statusClass(status) {
  if (status === "published" || status === "current" || status === "success") return "success";
  if (status === "archived" || status === "warning") return "warning";
  return "";
}

// Renders import scan feedback without changing files.
function renderImportScan(state) {
  const target = byId("hub-import-scan");
  if (!state.scan) {
    target.innerHTML = '<div class="empty-state">Scan a folder before importing it.</div>';
    return;
  }
  const summary = state.scan.summary || {};
  target.innerHTML = `
    <div class="project-hub-row">
      <div>
        <div class="row-title">${escapeHtml(state.scan.project.name)}</div>
        <div class="row-meta">${escapeHtml(state.scan.project.path)}</div>
        <div class="row-meta">
          ${summary.features || 0} features - ${summary.direct_versions || 0} direct versions -
          ${summary.loose_folders || 0} loose folders
        </div>
      </div>
      <span class="status-pill ${state.scan.git_present ? "success" : "warning"}">
        ${state.scan.git_present ? "git" : "local"}
      </span>
    </div>
  `;
}

// Renders recent GitHub Actions workflow runs inside the Builds card.
function renderBuilds(state) {
  const list = byId("hub-build-list");
  const runs = state.workflowRuns && state.workflowRuns.runs ? state.workflowRuns.runs : [];
  if (!runs.length) {
    list.innerHTML = '<div class="empty-state">No builds loaded</div>';
    return;
  }
  list.innerHTML = runs.slice(0, 5).map((run) => {
    const active = run.status && run.status !== "completed";
    const conclusion = active ? (run.status === "in_progress" ? "building" : run.status) : run.conclusion || "complete";
    const pillClass = active
      ? "building"
      : conclusion === "success"
        ? "success"
        : conclusion === "failure" ? "danger" : "warning";
    return `
      <div class="project-hub-row">
        <span class="project-hub-select-label">
          <strong>${escapeHtml(run.name)}</strong>
          <small>${escapeHtml(run.branch)} #${escapeHtml(run.run_number)} ${escapeHtml(run.event)}</small>
        </span>
        <span class="status-pill ${pillClass}">${escapeHtml(conclusion)}</span>
      </div>
    `;
  }).join("");
}

// Renders Git branch, stash, and tag controls from the latest safety refresh.
function renderGitBasics(state) {
  const branches = state.branches && state.branches.branches ? state.branches.branches : [];
  byId("hub-branch-select").innerHTML = branches.length
    ? branches.map((branch) => (
      `<option value="${escapeHtml(branch.name)}">`
        + `${escapeHtml(branch.name)}${branch.active ? " (active)" : ""}</option>`
    )).join("")
    : '<option value="">No branches loaded</option>';
  if (state.branches && state.branches.current) byId("hub-branch-select").value = state.branches.current;
  const stashes = state.stashes && state.stashes.stashes ? state.stashes.stashes : [];
  byId("hub-stash-select").innerHTML = stashes.length
    ? stashes.map((stash) => (
      `<option value="${escapeHtml(stash.name)}">${escapeHtml(stash.name)} - ${escapeHtml(stash.message)}</option>`
    )).join("")
    : '<option value="">No snapshots loaded</option>';
  const tags = state.tags && state.tags.tags ? state.tags.tags : [];
  byId("hub-tag-list").innerHTML = tags.length
    ? tags.slice(0, 8).map((tag) => (
      `<div class="row-meta">${escapeHtml(tag.name)} ${escapeHtml(tag.target.slice(0, 7))}</div>`
    )).join("")
    : '<div class="row-meta">No tags loaded</div>';
}

// Renders Project Hub timeline events.
function renderTimeline(state) {
  const events = state.hub && state.hub.timeline ? state.hub.timeline : [];
  byId("hub-timeline").innerHTML = events.length ? events.slice(0, 20).map((event) => `
    <div class="project-hub-timeline-row">
      <div>
        <div class="project-hub-timeline-title">${escapeHtml(event.title)}</div>
        <div class="project-hub-timeline-meta">${escapeHtml(event.timestamp)} - ${escapeHtml(event.detail)}</div>
      </div>
      <span class="status-pill ${statusClass(event.status)}">${escapeHtml(event.status)}</span>
    </div>
  `).join("") : '<div class="empty-state">No Project Hub history yet.</div>';
}

// Disables controls that need an active local version.
function renderDisabledStates(state) {
  const hasVersion = Boolean(activeVersionPath(state));
  const github = state.hub && state.hub.github ? state.hub.github : {};
  const repository = github.repository || {};
  const hasRepository = Boolean((repository.owner || github.owner) && (repository.repo || github.repo));
  [
    "hub-git-refresh", "hub-stash-create", "hub-branch-rename", "hub-branch-delete", "hub-stash-apply",
  ].forEach((id) => {
    byId(id).disabled = !hasVersion;
  });
  byId("hub-refresh-builds").disabled = !hasRepository;
}

// Renders every Project Hub surface from current state.
function render(state) {
  if (!state.hub) return;
  byId("project-hub-summary").textContent = "Commit activity, build health, history, and Git safety";
  renderImportScan(state);
  renderBuilds(state);
  renderGitBasics(state);
  renderTimeline(state);
  renderDisabledStates(state);
}

window.GitDeskProjectHubRender = {
  activeVersionPath,
  render,
  renderBuilds,
  renderGitBasics,
  renderImportScan,
  syncSharedSettings,
};
})();
