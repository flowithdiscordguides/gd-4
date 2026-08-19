/*
  Repo Mode GitHub Pages source selection and deployment-status controller.
*/

// Keeps Pages setup independent from the commit-history behavior that shares the toolbar module.
(() => {
const renderHelpers = window.GitDeskRender;
const deploymentSiteControl = window.GitDeskDeploymentSiteControl;

if (!renderHelpers || !deploymentSiteControl) {
  throw new Error("GitDesk Pages deployment dependencies did not load.");
}

const { byId, setText } = renderHelpers;
let runActionRef = null;
let repositoryPayloadRef = null;
let githubPayloadRef = null;
let applyStatusRef = null;
let renderBranchesRef = null;

// Escapes repository branch names and workflow paths before inserting them into generated markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Adds the Pages navigation control next to the other repository workflow surfaces.
function injectToolbarButton() {
  if (document.querySelector('.tab-button[data-tab="pages"]')) return;
  const button = document.createElement("button");
  button.className = "tab-button";
  button.type = "button";
  button.dataset.tab = "pages";
  button.title = "GitHub Pages";
  button.setAttribute("aria-label", "GitHub Pages");
  button.innerHTML = `
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M4 5h16v14H4z"></path>
      <path d="M4 9h16M8 13h4M8 16h8"></path>
    </svg>
  `;
  const settingsButton = document.querySelector('.tab-button[data-tab="settings"]');
  settingsButton.parentNode.insertBefore(button, settingsButton);
  button.addEventListener("click", () => loadPagesState().catch(() => {}));
}

// Builds the purpose-fit source form and published-site status surface used by Repo Mode.
function injectPagesPanel() {
  if (document.getElementById("panel-pages")) return;
  const panel = document.createElement("section");
  panel.id = "panel-pages";
  panel.className = "panel";
  panel.setAttribute("aria-labelledby", "pages-title");
  panel.innerHTML = `
    <div class="panel-header">
      <div>
        <h2 id="pages-title">GitHub Pages</h2>
        <p id="pages-summary">Not loaded</p>
      </div>
      <button id="refresh-pages" type="button">Refresh</button>
    </div>
    <div class="pages-deployment-layout">
      <form id="pages-form" class="settings-block pages-form">
        <div class="pages-form-heading">
          <h3>Build and deployment</h3>
          <p>Choose how GitHub publishes this repository.</p>
        </div>
        <label for="pages-build-type">Source</label>
        <select id="pages-build-type">
          <option value="legacy">Deploy from a branch</option>
          <option value="workflow">GitHub Actions</option>
        </select>
        <div id="pages-branch-fields" class="pages-source-fields">
          <label for="pages-branch">Branch</label>
          <select id="pages-branch"><option value="">None</option></select>
          <label for="pages-source-folder">Folder</label>
          <select id="pages-source-folder">
            <option value="/">/ (root)</option>
            <option value="/docs">/docs</option>
          </select>
        </div>
        <div id="pages-actions-fields" class="pages-actions-fields" hidden>
          <strong>Repository workflows</strong>
          <p>GitHub Actions will use the existing YAML workflows in <code>.github/workflows</code>.</p>
          <div id="pages-workflow-files" class="pages-workflow-files"></div>
        </div>
        <button id="save-pages" type="submit">Save changes</button>
      </form>
      <section class="pages-status" aria-labelledby="pages-publication-title">
        <div>
          <h3 id="pages-publication-title">Published site</h3>
          <p>Latest GitHub Pages deployment</p>
        </div>
        <div id="pages-publication" class="pages-publication" aria-live="polite">Not configured</div>
        <dl class="pages-status-details">
          <div><dt>Build source</dt><dd id="pages-build-source">Not configured</dd></div>
          <div><dt>Source branch</dt><dd id="pages-source-summary">Not used</dd></div>
        </dl>
      </section>
    </div>
  `;
  const settingsPanel = document.getElementById("panel-settings");
  settingsPanel.parentNode.insertBefore(panel, settingsPanel);
}

// Combines repository and GitHub context without mutating the shared payload objects.
function payload(extraFields) {
  return {
    ...repositoryPayloadRef(),
    ...githubPayloadRef(),
    ...(extraFields || {}),
  };
}

// Renders local branches while preserving GitHub's currently configured source when possible.
function renderBranchOptions(branches, selectedBranch) {
  const options = ['<option value="">None</option>'];
  (branches || []).forEach((branch) => {
    const selected = branch === selectedBranch ? "selected" : "";
    options.push(`<option value="${escapeHtml(branch)}" ${selected}>${escapeHtml(branch)}</option>`);
  });
  byId("pages-branch").innerHTML = options.join("");
}

// Shows the workflow files GitHub may execute without implying GitDesk selects or rewrites one of them.
function renderWorkflowFiles(workflowFiles) {
  const files = Array.isArray(workflowFiles) ? workflowFiles : [];
  if (!files.length) {
    byId("pages-workflow-files").innerHTML = `
      <span class="pages-workflow-empty">No local .yml or .yaml workflows found.</span>
    `;
    return;
  }
  byId("pages-workflow-files").innerHTML = files.map((file) => (
    `<code title="${escapeHtml(file)}">${escapeHtml(file)}</code>`
  )).join("");
}

// Switches between the fields GitHub accepts for legacy and workflow build types.
function syncSourceFields() {
  const workflowMode = byId("pages-build-type").value === "workflow";
  byId("pages-branch-fields").hidden = workflowMode;
  byId("pages-actions-fields").hidden = !workflowMode;
  byId("pages-branch").disabled = workflowMode;
  byId("pages-source-folder").disabled = workflowMode;
}

// Renders a native-browser button only after GitHub reports success; failures remain non-interactive.
function renderPublication(deployment) {
  const publication = byId("pages-publication");
  const state = deployment && deployment.state ? deployment.state : "";
  const url = deployment && deployment.url ? deployment.url : "";
  if (state === "success" && url) {
    publication.innerHTML = deploymentSiteControl.render(url);
    return;
  }
  if (state === "failure") {
    publication.innerHTML = `
      <span class="pages-publication-failure" role="status">
        <span class="pages-publication-mark" aria-hidden="true">×</span>
        <span>Deployment failed</span>
      </span>
    `;
    return;
  }
  if (state === "building") {
    publication.innerHTML = '<span class="pages-publication-building">Deployment in progress</span>';
    return;
  }
  if (state === "unavailable") {
    publication.innerHTML = `
      <span class="pages-publication-unavailable">${escapeHtml(deployment.error || "Status unavailable")}</span>
    `;
    return;
  }
  publication.textContent = state === "success" ? "Published URL unavailable" : "Not published yet";
}

// Sends successful publication clicks through Python so the operating system opens the user's default browser.
function openPublishedSite(event) {
  const url = deploymentSiteControl.urlFromEvent(event);
  if (!url) return;
  runActionRef(
    "openExternalUrl",
    { url },
    "Published site opened in your default browser",
  ).catch(() => {});
}

// Applies local source choices and authoritative remote deployment state to the panel.
function renderPagesState(state) {
  const local = state && state.local ? state.local : {};
  const config = local.config || {};
  const remote = state && state.remote ? state.remote : {};
  const source = remote.source || {};
  const selectedBranch = source.branch || config.branch || local.current_branch || "";
  const buildType = remote.build_type || "legacy";
  renderBranchOptions(local.branches || [], selectedBranch);
  renderWorkflowFiles(local.workflow_files || []);
  byId("pages-build-type").value = buildType === "workflow" ? "workflow" : "legacy";
  byId("pages-source-folder").value = source.path || config.source_folder || "/";
  setText("pages-build-source", buildType === "workflow" ? "GitHub Actions" : "Deploy from a branch");
  setText("pages-source-summary", buildType === "workflow" ? "Not used" : selectedBranch || "Not selected");
  setText("pages-summary", remote.configured ? `Pages ${remote.status || "configured"}` : "Not configured");
  syncSourceFields();
  renderPublication(state ? state.deployment : null);
}

// Loads both local workflow discovery and GitHub's live Pages/deployment state.
async function loadPagesState() {
  const state = await runActionRef("pagesState", payload({}), "GitHub Pages refreshed");
  renderPagesState(state);
}

// Saves the selected GitHub build type and refreshes the complete panel from the returned authoritative state.
async function savePages(event) {
  event.preventDefault();
  const data = await runActionRef("savePagesSettings", payload({
    build_type: byId("pages-build-type").value,
    branch: byId("pages-branch").value,
    source_folder: byId("pages-source-folder").value,
  }), "GitHub Pages saved");
  applyStatusRef(data.status);
  renderBranchesRef(data.branches);
  renderPagesState(data);
}

// Installs the Pages surface after the main app provides native action and repository-state boundaries.
function bind(options) {
  runActionRef = options.runAction;
  repositoryPayloadRef = options.repositoryPayload;
  githubPayloadRef = options.githubPayload;
  applyStatusRef = options.applyStatus;
  renderBranchesRef = options.renderBranches;
  injectToolbarButton();
  injectPagesPanel();
  byId("refresh-pages").addEventListener("click", () => loadPagesState().catch(() => {}));
  byId("pages-build-type").addEventListener("change", syncSourceFields);
  byId("pages-form").addEventListener("submit", savePages);
  byId("pages-publication").addEventListener("click", openPublishedSite);
}

// Publishes the focused controller consumed by pages.js during application bootstrap.
window.GitDeskPagesDeployment = { bind };
})();
