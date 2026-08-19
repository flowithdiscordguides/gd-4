/*
  Rendering helpers for the managed repository dialog.
*/

// Keeps repository markup generation separate from repository workflow actions.
(() => {
const renderHelpers = window.GitDeskRender;
const repositoryCatalog = window.GitDeskRepositoryCatalog;

if (!renderHelpers || !repositoryCatalog) {
  throw new Error("GitDesk repository render dependencies did not load.");
}

const { byId } = renderHelpers;

// Escapes repository metadata before inserting it into dynamic markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Returns the inline trash icon used by remove-from-app buttons.
function trashIcon() {
  return `
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
      <path d="M4 7h16"></path>
      <path d="M10 11v6"></path>
      <path d="M14 11v6"></path>
      <path d="M6 7l1 14h10l1-14"></path>
      <path d="M9 7V4h6v3"></path>
    </svg>
  `;
}

// Returns the folder icon shared by native directory chooser buttons.
function folderIcon() {
  return `
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v1H3z"></path>
      <path d="M3 9h18l-2 9a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z"></path>
    </svg>
  `;
}

// Inserts the repository setup dialog shell when the static HTML has not already provided it.
function injectUI() {
  if (document.getElementById("repo-add-dialog")) return;
  document.querySelector(".topbar").insertAdjacentHTML("afterend", `
    <section id="repo-add-dialog" class="repo-dialog" hidden>
      <div class="repo-dialog-panel" role="dialog" aria-modal="true" aria-labelledby="repo-add-title">
        <div class="panel-header">
          <div>
            <h2 id="repo-add-title">Repositories</h2>
            <p id="repo-dialog-summary">Clone, add, or create under the active account</p>
          </div>
          <button id="close-managed-repo-dialog" type="button">Close</button>
        </div>
        <div class="repo-dialog-body">
          <aside class="repo-dialog-sidebar">
            <div id="repo-dialog-modes" class="repo-dialog-modes" role="tablist">
              <button type="button" data-repo-mode="clone">Clone</button>
              <button type="button" data-repo-mode="existing">Add Existing</button>
              <button type="button" data-repo-mode="create">Create New</button>
            </div>
            <div class="repo-saved-panel">
              <label>Saved repositories</label>
              <div id="managed-repo-list" class="managed-repo-list" aria-live="polite"></div>
            </div>
          </aside>
          <div class="repo-dialog-workspace">
            <section class="repo-setup-panel" data-repo-setup-panel="clone">
              <div class="repo-dialog-controls">
                <label for="managed-clone-parent">Destination folder</label>
                <div class="input-action-row">
                  <input id="managed-clone-parent" type="text" spellcheck="false"
                    placeholder="/absolute/path/to/parent">
                  <button id="choose-managed-clone-parent" class="icon-button" type="button"
                    aria-label="Choose destination folder" title="Choose destination folder">${folderIcon()}</button>
                </div>
                <label for="managed-clone-category">Category</label>
                <input id="managed-clone-category" type="text" spellcheck="true" placeholder="Work">
              </div>
              <div class="repo-catalog-panel">
                <div class="repo-catalog-toolbar">
                  <select id="github-owner-filter" aria-label="Filter repositories by owner"></select>
                  <input id="github-repo-filter" type="text" spellcheck="false" placeholder="Filter repositories">
                  <button id="refresh-managed-repo-list" type="button">Refresh</button>
                </div>
                <p id="github-org-access-note" class="repo-access-note"></p>
                <div id="github-repo-list" class="repo-catalog-list" aria-live="polite"></div>
              </div>
            </section>
            <section class="repo-setup-panel" data-repo-setup-panel="existing" hidden>
              <form id="existing-repo-form" class="repo-setup-form">
                <label for="existing-repo-path">Repository folder</label>
                <div class="input-action-row">
                  <input id="existing-repo-path" type="text" spellcheck="false"
                    placeholder="/absolute/path/to/repository">
                  <button id="choose-existing-repo" class="icon-button" type="button"
                    aria-label="Choose repository folder" title="Choose repository folder">${folderIcon()}</button>
                </div>
                <div id="existing-repo-remote" class="existing-repo-remote" aria-live="polite">
                  Choose a local Git repository to inspect its GitHub origin.
                </div>
                <label for="existing-repo-category">Category</label>
                <input id="existing-repo-category" type="text" spellcheck="true" placeholder="Client work">
                <button id="add-existing-repo" type="submit">Add repository</button>
              </form>
            </section>
            <section class="repo-setup-panel" data-repo-setup-panel="create" hidden>
              <form id="new-repo-form" class="repo-setup-form">
                <label for="new-repo-owner">GitHub owner</label>
                <select id="new-repo-owner"></select>
                <small id="new-repo-owner-note" class="repo-access-note"></small>
                <label for="new-repo-name">GitHub repository</label>
                <input id="new-repo-name" type="text" spellcheck="false" placeholder="repository">
                <label class="check-row">
                  <input id="new-repo-private" type="checkbox">
                  <span>Private</span>
                </label>
                <label for="new-repo-parent">Parent folder</label>
                <div class="input-action-row">
                  <input id="new-repo-parent" type="text" spellcheck="false"
                    placeholder="/absolute/path/to/parent">
                  <button id="choose-new-repo-parent" class="icon-button" type="button"
                    aria-label="Choose parent folder" title="Choose parent folder">${folderIcon()}</button>
                </div>
                <label for="new-repo-folder">Local folder</label>
                <input id="new-repo-folder" type="text" spellcheck="false" placeholder="my-repo">
                <label for="new-repo-category">Category</label>
                <input id="new-repo-category" type="text" spellcheck="true" placeholder="Personal">
                <label>Shared Resources</label>
                <div id="new-repo-ai-categories" class="repo-ai-category-list"></div>
                <button id="create-new-repo" type="submit">Create repository</button>
              </form>
            </section>
          </div>
        </div>
      </div>
    </section>
  `);
}

// Returns the concise repository name shown in the topbar picker.
function repositoryLabel(record) {
  const name = String(record.name || "").trim();
  if (name) {
    return name;
  }
  const fullName = String(record.full_name || "").trim();
  if (fullName) {
    const parts = fullName.split("/");
    return parts[parts.length - 1] || fullName;
  }
  return "Repository";
}

// Returns repository records belonging to one account from the latest settings payload.
function repositoriesForAccount(settings, login) {
  const repositoryMap = settings && settings.managed_repositories
    ? settings.managed_repositories
    : {};
  return login ? repositoryMap[login] || [] : [];
}

// Groups repository records by category while keeping uncategorized repos visible first.
function categoryGroups(records) {
  const groups = [{ category: "", records: [] }];
  records.forEach((record) => {
    const category = String(record.category || "").trim();
    let group = groups.find((item) => item.category === category);
    if (!group) {
      group = { category, records: [] };
      groups.push(group);
    }
    group.records.push(record);
  });
  return groups.filter((group) => group.records.length);
}

// Maps repository source labels into readable badge classes.
function sourceClass(source) {
  const cleanSource = String(source || "added").trim();
  return ["added", "cloned", "created", "published"].indexOf(cleanSource) >= 0 ? cleanSource : "added";
}

// Renders the topbar repository selector with category optgroups.
function renderPicker(context) {
  const select = byId("managed-repo-select");
  const login = context.accountLogin || "";
  const repositories = context.repositories || [];
  const selectedPath = context.activePath || "";

  if (!login) {
    select.innerHTML = '<option value="">Sign in to select repositories</option>';
    select.disabled = true;
    return;
  }
  if (!repositories.length) {
    select.innerHTML = '<option value="">No managed repositories</option>';
    select.disabled = true;
    return;
  }

  const groups = categoryGroups(repositories).map((group) => {
    const options = group.records.map((record) => (
      `<option value="${escapeHtml(record.path)}">${escapeHtml(repositoryLabel(record))}</option>`
    )).join("");
    if (!group.category) {
      return options;
    }
    return `<optgroup label="${escapeHtml(group.category)}">${options}</optgroup>`;
  }).join("");
  select.innerHTML = `<option value="">Select repository</option>${groups}`;
  select.value = selectedPath;
  select.disabled = false;
}

// Renders the saved repository management list inside the dialog.
function renderManagedList(context) {
  const list = byId("managed-repo-list");
  const login = context.accountLogin || "";
  const repositories = context.repositories || [];
  if (!login) {
    list.innerHTML = '<div class="empty-state">No active account</div>';
    return;
  }
  if (!repositories.length) {
    list.innerHTML = '<div class="empty-state">No saved repositories</div>';
    return;
  }

  list.innerHTML = categoryGroups(repositories).map((group) => {
    const label = group.category || "Uncategorized";
    const rows = group.records.map((record) => {
      const active = record.path === context.activePath ? " active" : "";
      const source = record.source || "added";
      const pillClass = sourceClass(source);
      return `
        <div class="managed-repo-row${active}">
          <button class="managed-repo-open" type="button" data-path="${escapeHtml(record.path)}">
            <span>
              <strong>${escapeHtml(record.full_name || record.name)}</strong>
              <small>${escapeHtml(record.path)}</small>
            </span>
            <span class="status-pill ${escapeHtml(pillClass)}">${escapeHtml(source)}</span>
          </button>
          <input class="managed-repo-category" type="text" spellcheck="true"
            data-path="${escapeHtml(record.path)}" value="${escapeHtml(record.category || "")}"
            placeholder="Category">
          <button class="remove-managed-repo icon-button" type="button" data-path="${escapeHtml(record.path)}"
            aria-label="Remove ${escapeHtml(record.name || "repository")}" title="Remove from GitDesk">
            ${trashIcon()}
          </button>
        </div>
      `;
    }).join("");
    return `
      <div class="managed-repo-category-group">
        <div class="managed-repo-category-title">${escapeHtml(label)}</div>
        ${rows}
      </div>
    `;
  }).join("");
}

// Renders personal and organization owner selectors for Clone and Create New.
function renderOrganizationContext(context, repositories) {
  repositoryCatalog.renderOwnerControls(context, repositories);
}

// Delegates owner-aware clone catalog filtering and grouping to the focused catalog module.
function renderCatalog(repositories, context) {
  repositoryCatalog.renderCatalog(repositories, context);
}

// Displays the GitHub origin inferred from an Add Existing local repository.
function renderExistingRemote(repository, context) {
  repositoryCatalog.renderExistingRemote(repository, context);
}

// Shows one setup mode and keeps the tab buttons in sync.
function renderMode(mode) {
  const selectedMode = mode || "clone";
  document.querySelectorAll("[data-repo-mode]").forEach((button) => {
    button.classList.toggle("active", button.dataset.repoMode === selectedMode);
  });
  document.querySelectorAll("[data-repo-setup-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.repoSetupPanel !== selectedMode;
  });
}

// Enables remote-owner fields only when remote creation is selected.
function renderRemoteFields() {
  ["new-repo-owner", "new-repo-name", "new-repo-private"].forEach((id) => {
    byId(id).disabled = false;
  });
}

// Mirrors the local folder name into the GitHub repository field until that field has its own value.
function syncNewRepoName() {
  const remoteName = byId("new-repo-name");
  if (!remoteName.value.trim()) {
    remoteName.value = byId("new-repo-folder").value;
  }
}

// Mirrors the GitHub repository name into the local folder field until that field has its own value.
function syncNewFolderName() {
  const folderName = byId("new-repo-folder");
  if (!folderName.value.trim()) {
    folderName.value = byId("new-repo-name").value;
  }
}

// Returns the Shared Resources checked in the create-new repository form only.
function selectedCreateAiCategories() {
  return Array.from(document.querySelectorAll(".new-repo-ai-check"))
    .filter((check) => check.checked && !check.disabled)
    .map((check) => check.value);
}

// Renders Shared Resources as create-repository starter-file checkboxes.
function renderCreateAiCategories(categories, selected) {
  const list = byId("new-repo-ai-categories");
  const selectedNames = selected || [];
  if (!categories.length) {
    list.innerHTML = '<div class="empty-state">No Shared Resources yet</div>';
    return;
  }
  list.innerHTML = categories.map((category) => {
    const checked = selectedNames.indexOf(category.name) >= 0 ? "checked" : "";
    const count = Number(category.file_count || 0);
    const disabled = category.recorded ? "" : "disabled";
    return `
      <label class="repo-ai-check-row">
        <input type="checkbox" class="new-repo-ai-check" value="${escapeHtml(category.name)}"
          ${checked} ${disabled}>
        <span>${escapeHtml(category.name)} · ${escapeHtml(category.version_label)}</span>
        <small>${escapeHtml(count)} file${count === 1 ? "" : "s"}</small>
      </label>
    `;
  }).join("");
}

window.GitDeskRepositoryRender = {
  injectUI,
  renderCatalog,
  renderCreateAiCategories,
  renderExistingRemote,
  renderManagedList,
  renderOrganizationContext,
  renderPicker,
  renderMode,
  renderRemoteFields,
  repositoryLabel,
  repositoriesForAccount,
  selectedCreateAiCategories,
  syncNewFolderName,
  syncNewRepoName,
};
})();
