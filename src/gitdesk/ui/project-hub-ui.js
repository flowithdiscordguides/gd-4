/*
  Dynamic Project Hub markup injection.
*/

// Publishes Project Hub UI injection separately from stateful workflow code.
(() => {
// Inserts the home toolbar button ahead of repository-specific tabs.
function injectToolbarButton() {
  if (document.querySelector('.tab-button[data-tab="project-hub"]')) return;
  const button = document.createElement("button");
  button.className = "tab-button active";
  button.type = "button";
  button.dataset.tab = "project-hub";
  button.title = "Project Hub";
  button.setAttribute("aria-label", "Project Hub");
  button.innerHTML = `
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M4 4h16v5H4zM4 13h7v7H4zM15 13h5v7h-5z"></path>
    </svg>
  `;
  const overview = document.querySelector('.tab-button[data-tab="overview"]');
  overview.classList.remove("active");
  overview.parentNode.insertBefore(button, overview);
}

// Inserts the Project Hub panel as the first workspace surface.
function injectPanel() {
  if (document.getElementById("panel-project-hub")) return;
  document.getElementById("panel-overview").classList.remove("active");
  document.querySelector(".workspace").insertAdjacentHTML("afterbegin", `
    <section id="panel-project-hub" class="panel active" aria-labelledby="project-hub-title">
      <div class="panel-header">
        <div>
          <h2 id="project-hub-title">Project Hub</h2>
          <p id="project-hub-summary">Loading project state</p>
        </div>
        <button id="project-hub-refresh" type="button">Refresh</button>
      </div>
      <div class="project-hub-layout">
        <section class="settings-block project-hub-card project-hub-activity-card">
          <div class="project-hub-card-header">
            <div>
              <label>Project activity</label>
              <div id="activity-range-label" class="project-hub-muted">Loading commit history</div>
            </div>
            <button id="activity-refresh" type="button">Refresh</button>
          </div>
          <div class="activity-range-controls">
            <select id="activity-range" aria-label="Activity range">
              <option value="week">Week</option>
              <option value="month" selected>Month</option>
              <option value="year">Year</option>
              <option value="custom">Custom start</option>
            </select>
            <input id="activity-custom-start" type="date" aria-label="Custom activity start date" disabled>
            <button id="activity-apply-range" type="button">Apply</button>
          </div>
          <div id="activity-atlas" class="activity-atlas" aria-live="polite"></div>
          <div id="activity-warnings" class="activity-warnings" role="status"></div>
        </section>
        <section class="settings-block project-hub-card project-hub-builds-card">
          <div class="project-hub-card-header">
            <label>Builds</label>
            <button id="hub-refresh-builds" type="button">Refresh</button>
          </div>
          <div id="hub-build-list" class="project-hub-build-list"></div>
        </section>
        <section class="settings-block project-hub-card project-hub-git-card">
          <label>Git safety and branches</label>
          <div class="project-hub-git-grid">
            <button id="hub-git-refresh" type="button">Refresh Git</button>
            <button id="hub-stash-create" type="button">Safety snapshot</button>
            <select id="hub-branch-select"></select>
            <input id="hub-branch-new" type="text" spellcheck="false" placeholder="new-branch-name">
          </div>
          <div class="project-hub-actions">
            <button id="hub-branch-rename" type="button">Rename branch</button>
            <label class="project-hub-inline-check">
              <input id="hub-branch-force" type="checkbox">
              <span>Force delete</span>
            </label>
            <button id="hub-branch-delete" class="project-hub-danger" type="button">Delete branch</button>
          </div>
          <div class="project-hub-git-grid">
            <select id="hub-stash-select"></select>
            <button id="hub-stash-apply" type="button">Apply snapshot</button>
          </div>
          <div id="hub-tag-list" class="project-hub-tag-list"></div>
        </section>
        <section class="settings-block project-hub-card project-hub-history-card">
          <div class="project-hub-card-header">
            <label>History</label>
            <button id="hub-repair-projects" type="button">Repair</button>
          </div>
          <div id="hub-timeline" class="project-hub-timeline"></div>
        </section>
        <section class="settings-block project-hub-card project-hub-backup-card">
          <label for="hub-backup-json">Project metadata backup</label>
          <textarea id="hub-backup-json" class="project-hub-backup-text" spellcheck="false"></textarea>
          <div class="project-hub-actions">
            <button id="hub-export-settings" type="button">Export</button>
            <button id="hub-import-settings" type="button">Import backup</button>
          </div>
        </section>
      </div>
    </section>
  `);
}

// Inserts the shared create/import modal used by the Local Projects header action.
function injectNewProjectModal() {
  if (document.getElementById("new-project-modal")) return;
  document.body.insertAdjacentHTML("beforeend", `
    <section id="new-project-modal" class="new-project-modal" hidden>
      <div class="new-project-dialog" role="dialog" aria-modal="true" aria-labelledby="new-project-title">
        <div class="panel-header new-project-dialog-header">
          <div>
            <h2 id="new-project-title">New Project</h2>
            <p id="new-project-summary">Create or import a local project.</p>
          </div>
          <div class="new-project-dialog-actions">
            <button id="create-local-project" type="submit" form="local-create-form">Apply changes</button>
            <button id="close-new-project-modal" type="button">Close</button>
          </div>
        </div>
        <div class="new-project-tabs" role="tablist" aria-label="New project options">
          <button id="new-project-tab-create" class="active" type="button" role="tab" aria-selected="true"
            aria-controls="new-project-pane-create" data-new-project-tab="create">Create Project</button>
          <button id="new-project-tab-import" type="button" role="tab" aria-selected="false"
            aria-controls="new-project-pane-import" data-new-project-tab="import">Import Project</button>
        </div>
        <div id="new-project-pane-create" class="new-project-pane active" role="tabpanel"
          aria-labelledby="new-project-tab-create" data-new-project-pane="create">
          <form id="local-create-form" class="local-create-form new-project-create-form">
            <label for="local-parent-path">Parent folder</label>
            <div class="input-action-row">
              <input id="local-parent-path" type="text" spellcheck="false" placeholder="/absolute/path/to/projects">
              <button id="choose-local-parent" class="icon-button" type="button" aria-label="Choose parent folder">
                <svg aria-hidden="true" viewBox="0 0 24 24">
                  <path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v1H3z"></path>
                  <path d="M3 9h18l-2 9a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z"></path>
                </svg>
              </button>
            </div>
            <label for="local-project-name">Project name</label>
            <input id="local-project-name" type="text" spellcheck="false" placeholder="my-app">
            <label>Shared Resources</label>
            <div id="local-ai-categories" class="local-check-list new-project-check-list"></div>
          </form>
        </div>
        <div id="new-project-pane-import" class="new-project-pane" role="tabpanel"
          aria-labelledby="new-project-tab-import" data-new-project-pane="import" hidden>
          <label for="hub-import-path">Import existing project</label>
          <div class="input-action-row">
            <input id="hub-import-path" type="text" spellcheck="false" placeholder="/absolute/path/to/project">
            <button id="hub-choose-import" class="icon-button" type="button" aria-label="Choose project folder">
              <svg aria-hidden="true" viewBox="0 0 24 24">
                <path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v1H3z"></path>
                <path d="M3 9h18l-2 9a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z"></path>
              </svg>
            </button>
          </div>
          <div class="project-hub-actions">
            <button id="hub-scan-import" type="button">Scan</button>
            <button id="hub-import-project" class="primary" type="button">Import</button>
          </div>
          <div id="hub-import-scan" class="project-hub-scan"></div>
        </div>
      </div>
    </section>
  `);
}

// Inserts every Project Hub surface before app event binding starts.
function injectUI() {
  injectToolbarButton();
  injectPanel();
  injectNewProjectModal();
}

window.GitDeskProjectHubUI = { injectUI };
})();
