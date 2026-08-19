/*
  Rendering and dynamic markup helpers for GitDesk Local Mode.
*/

// Keeps Local Mode markup generation separate from the controller's backend workflow.
(() => {
const renderHelpers = window.GitDeskRender;
const localActions = window.GitDeskLocalActions;
const localVersionDetail = window.GitDeskLocalVersionDetail;
const localVersionWorkspace = window.GitDeskLocalVersionWorkspace;

if (!renderHelpers || !localActions || !localVersionDetail || !localVersionWorkspace) {
  throw new Error("GitDesk Local Mode render dependencies did not load.");
}

const { byId, setText } = renderHelpers;

// Escapes backend and filesystem values before inserting them into dynamic markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Inserts the Local Mode toolbar button before repository-specific tabs.
function injectToolbarButton() {
  if (document.querySelector('.tab-button[data-tab="local"]')) return;
  const button = document.createElement("button");
  button.className = "tab-button";
  button.type = "button";
  button.dataset.tab = "local";
  button.title = "Local Mode";
  button.setAttribute("aria-label", "Local Mode");
  button.innerHTML = `
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M3 6h6l2 2h10v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
      <path d="M8 13h8M8 16h5"></path>
    </svg>
  `;
  const cloneButton = document.querySelector('.tab-button[data-tab="clone"]');
  cloneButton.parentNode.insertBefore(button, cloneButton);
}

// Inserts the Local Mode project/feature/version workspace panel.
function injectLocalPanel() {
  if (document.getElementById("panel-local")) return;
  const panel = document.createElement("section");
  panel.id = "panel-local";
  panel.className = "panel";
  panel.setAttribute("aria-labelledby", "local-title");
  panel.innerHTML = `
    <div class="panel-header local-panel-header">
      <div class="local-panel-heading">
        <h2 id="local-title">Local Projects</h2>
        <p id="local-summary">No local project selected</p>
      </div>
      <div class="local-panel-actions">
        <button id="open-new-project-modal" class="new-project-button local-panel-primary" type="button">
          <img src="./newproject-icon.svg" alt="" draggable="false">
          <span>New project</span>
        </button>
        <details class="local-panel-more">
          <summary>Maintenance</summary>
          <div class="local-panel-more-menu">
            <button id="scan-local-categories" type="button"
              title="Repair saved project paths from a categories folder">Scan categories</button>
            <button id="refresh-local-projects" type="button">Refresh projects</button>
          </div>
        </details>
      </div>
    </div>
    <div id="local-layout" class="local-layout">
      <section id="local-projects-card" class="local-project-identity-card local-project-ribbon">
        <div class="local-project-details">
          <div class="local-project-artwork">
            <div class="local-project-icon-frame">
              <img id="local-project-icon" src="./folder-icon.svg" alt="" draggable="false">
            </div>
            <p id="local-project-icon-status" aria-live="polite">Folder icon</p>
          </div>
          <dl class="local-project-metadata-list local-project-selection-list">
            <div class="local-project-selector-row">
              <dt>Project</dt>
              <dd class="local-project-picker">
                <button id="local-project-picker-trigger" class="local-project-picker-trigger" type="button"
                  aria-haspopup="menu" aria-expanded="false" aria-controls="local-project-picker-menu" disabled>
                  <span id="local-project-picker-label" class="local-project-picker-trigger-label">
                    No local projects
                  </span>
                  <span class="local-project-picker-caret" aria-hidden="true"></span>
                </button>
              </dd>
            </div>
          </dl>
          <dl class="local-project-metadata-list local-feature-selection-list">
            <div>
              <dt>Feature</dt>
              <dd class="local-feature-picker">
                <button id="local-feature-picker-trigger" class="local-feature-picker-trigger" type="button"
                  aria-haspopup="dialog" aria-expanded="false" aria-controls="local-feature-picker-menu" disabled>
                  <span id="local-feature-picker-label" class="local-feature-picker-trigger-label">
                    No project selected
                  </span>
                  <span class="local-feature-picker-caret" aria-hidden="true"></span>
                </button>
              </dd>
            </div>
          </dl>
          <div class="local-project-category-block">
            <dl class="local-project-metadata-list local-project-category-list">
              <div>
                <dt>Category</dt>
                <dd id="local-active-project-category">Uncategorized</dd>
              </div>
            </dl>
            <div class="local-project-action-dock" role="group" aria-label="Project metadata actions">
              <button id="edit-local-project-metadata" class="local-rename-icon" type="button"
                aria-haspopup="dialog" aria-controls="local-project-metadata-modal" aria-expanded="false"
                disabled>Edit project details</button>
              <button id="remove-active-local-project" type="button" disabled>Remove from GitDesk</button>
            </div>
          </div>
        </div>
      </section>
      <div class="local-workbench">
        <section id="local-versions-card" class="settings-block local-versions-card local-accordion-card">
          <div class="local-version-header">
            <label>Versions</label>
            <button class="local-accordion-toggle" type="button" data-local-menu-toggle="versions"></button>
          </div>
          <div class="local-version-workspace">
            <div id="local-version-list" class="local-list" aria-live="polite"></div>
            <aside id="local-version-detail" class="local-version-detail" aria-live="polite">
              <div id="local-version-detail-empty" class="local-version-detail-empty">
                <span>Version inspector</span>
                <h3>No version selected</h3>
                <p>Choose a version to inspect its folder and available actions.</p>
              </div>
              <div id="local-version-detail-content" class="local-version-detail-content" hidden>
                <div class="local-version-detail-heading">
                  <span>Version inspector</span>
                  <span id="local-selected-version-order" class="status-pill"></span>
                </div>
                <h3 id="local-selected-version-name"></h3>
                <dl class="local-version-context" aria-label="Selected version context">
                  <div>
                    <dt>Project</dt>
                    <dd id="local-selected-version-project"></dd>
                  </div>
                  <div>
                    <dt>Feature</dt>
                    <dd id="local-selected-version-feature"></dd>
                  </div>
                </dl>
                <div class="local-version-path-block">
                  <span>Location</span>
                  <code id="local-selected-version-path"></code>
                </div>
                <div class="local-version-resources-block">
                  <span>Shared Resources</span>
                  <div id="local-selected-version-resources" class="local-version-resource-list"></div>
                </div>
                ${localVersionWorkspace.actionMarkup()}
              </div>
            </aside>
          </div>
        </section>
      </div>
    </div>
  `;
  document.getElementById("panel-clone").before(panel);
}

// Inserts the duplicate dialog used for move-vs-copy cleanup choices.
function injectDuplicateDialog() {
  if (document.getElementById("local-duplicate-dialog")) return;
  document.body.insertAdjacentHTML("beforeend", `
    <section id="local-duplicate-dialog" class="local-duplicate-dialog" hidden>
      <div class="local-duplicate-panel" role="dialog" aria-modal="true">
        <div class="panel-header">
          <div>
            <h2>Create New Version</h2>
            <p id="local-duplicate-summary">0 move paths selected</p>
          </div>
          <div class="button-row local-duplicate-header-actions">
            <button id="create-local-version" type="submit" form="local-duplicate-form">Create Version</button>
            <button id="close-local-duplicate" type="button">Close</button>
          </div>
        </div>
        <form id="local-duplicate-form" class="local-duplicate-form">
          <label for="local-version-label">Version label</label>
          <input id="local-version-label" type="text" spellcheck="true" placeholder="add feature">
          <div class="local-move-label-row">
            <label>Move to new version</label>
            <details class="local-move-help">
              <summary aria-label="Move to new version help">i</summary>
              <p>Checked files and folders move into the new version. Unchecked items are copied and stay here.</p>
            </details>
          </div>
          <div id="local-cleanup-tree" class="local-cleanup-tree" aria-live="polite"></div>
        </form>
      </div>
    </section>
  `);
}

// Inserts every Local Mode surface before event binding starts.
function injectUI() {
  injectToolbarButton();
  injectLocalPanel();
  injectDuplicateDialog();
}

// Renders available Shared Resources as project-creation checkboxes.
function renderResources(categories, selected) {
  const list = byId("local-ai-categories");
  if (!categories.length) {
    list.innerHTML = '<div class="empty-state">No Shared Resources yet</div>';
    return;
  }
  list.innerHTML = categories.map((category) => {
    const checked = selected.indexOf(category.name) >= 0 ? "checked" : "";
    const disabled = category.recorded ? "" : "disabled";
    return `
      <label class="local-check-row">
        <input type="checkbox" class="local-ai-check" value="${escapeHtml(category.name)}"
          ${checked} ${disabled}>
        <span>${escapeHtml(category.name)} · ${escapeHtml(category.version_label)}</span>
      </label>
    `;
  }).join("");
}

// Returns the selected local project record from a local-state payload.
function activeProject(localState) {
  return (localState.projects || []).find((project) => project.path === localState.active_project) || null;
}

// Returns the selected feature record nested under the active project.
function activeFeature(localState) {
  const project = activeProject(localState);
  if (!project) {
    return null;
  }
  return (project.features || []).find((feature) => feature.path === localState.active_feature) || null;
}

// Returns the selected version record nested under the active feature.
function activeVersion(localState) {
  const feature = activeFeature(localState);
  if (!feature) {
    return null;
  }
  return (feature.versions || []).find((version) => version.path === localState.active_version) || null;
}

// Applies collapsed menu state after each render because rows are rebuilt from backend state.
function applyAccordionState(menus) {
  ["versions"].forEach((name) => {
    const card = byId(`local-${name}-card`);
    const collapsed = Boolean(menus && menus[name]);
    card.classList.toggle("local-collapsed", collapsed);
    const button = card.querySelector("[data-local-menu-toggle]");
    button.textContent = "";
    button.title = `${collapsed ? "Expand" : "Collapse"} ${name}`;
    button.setAttribute("aria-label", button.title);
    button.setAttribute("aria-expanded", String(!collapsed));
  });
}

// Renders all Local Mode stateful surfaces.
function renderLocalState(localState) {
  const project = activeProject(localState);
  const feature = activeFeature(localState);
  const version = activeVersion(localState);
  localVersionDetail.render(localState, project, feature, version);
  localActions.render(localState, project, version);
}

// Renders one cleanup tree row and its nested children.
function renderTreeNode(node, level) {
  const checked = node.checked ? "checked" : "";
  const size = node.size_label ? `<small>${escapeHtml(node.size_label)}</small>` : "";
  const pruned = node.pruned ? '<span class="status-pill warning">entire folder</span>' : "";
  const children = (node.children || []).map((child) => renderTreeNode(child, level + 1)).join("");
  const isBranch = node.type === "directory" && Boolean(children);
  const kind = node.type === "directory" ? "folder" : "file";
  const tag = isBranch ? "summary" : "div";
  const row = `
    <${tag} class="local-tree-row local-tree-${kind}" style="--local-tree-indent:${level * 18}px">
      <span class="${isBranch ? "local-tree-caret" : "local-tree-caret-spacer"}" aria-hidden="true"></span>
      <input type="checkbox" class="local-move-check" value="${escapeHtml(node.path)}"
        aria-label="Move ${escapeHtml(node.name)} to new version" ${checked}>
      <span class="local-tree-icon" aria-hidden="true"></span>
      <span class="local-tree-name">${escapeHtml(node.name)}</span>
      ${size}
      ${pruned}
    </${tag}>
  `;
  if (isBranch) return `<details class="local-tree-branch">${row}<div class="local-tree-children">`
    + `${children}</div></details>`;
  return row;
}

// Renders the duplicate cleanup tree into the modal.
function renderCleanupTree(tree) {
  byId("local-cleanup-tree").innerHTML = tree.children.length
    ? tree.children.map((node) => renderTreeNode(node, 0)).join("")
    : '<div class="empty-state">No files in selected version</div>';
}

// Returns selected cleanup paths that should move into the new version.
function collectMovePaths() {
  return Array.from(document.querySelectorAll(".local-move-check"))
    .filter((check) => check.checked)
    .map((check) => check.value);
}

// Updates the duplicate dialog summary from checked move paths.
function updateMoveSummary() {
  const count = collectMovePaths().length;
  setText("local-duplicate-summary", `${count} move path${count === 1 ? "" : "s"} selected`);
}

window.GitDeskLocalRender = {
  applyAccordionState,
  collectMovePaths,
  injectUI,
  renderResources,
  renderCleanupTree,
  renderLocalState,
  updateMoveSummary,
};
})();
