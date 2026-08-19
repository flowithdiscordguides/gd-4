/*
  User settings controller for future category folders and explicit whole-project migration.
*/

// Keeps path-layout controls independent from the Local Mode renderer while reusing its canonical response API.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;

if (!nativeBridge || !renderHelpers) {
  throw new Error("GitDesk category-folder settings dependencies did not load.");
}

const { appendActivity, byId, setBusy, showMessage } = renderHelpers;
const { callNative } = nativeBridge;
const state = {
  busy: false,
  enabled: false,
  modalOpen: false,
  projects: [],
  returnFocus: null,
  selected: new Set(),
};

// Injects a compact preference row and keeps the longer migration workflow in a body-level modal.
function createCategoryFoldersCard() {
  if (document.getElementById("category-folders-card")) {
    return;
  }
  const mount = document.getElementById("settings-user-content");
  if (!mount) {
    return;
  }
  mount.insertAdjacentHTML("afterbegin", `
    <section id="category-folders-card" class="settings-block category-folders-card"
      aria-labelledby="category-folders-title">
      <div class="category-folders-preference">
        <div class="category-folders-preference-copy">
          <strong id="category-folders-title">Create categories as folders</strong>
          <p>Store future projects at <code>Parent / categories / Category / Project</code>.</p>
        </div>
        <button id="create-categories-as-folders" class="category-folders-switch" type="button"
          role="switch" aria-checked="false" aria-labelledby="category-folders-title">
          <span class="category-folders-switch-thumb" aria-hidden="true"></span>
        </button>
      </div>
      <div id="category-folder-migration-action" class="category-folder-migration-action" hidden>
        <div>
          <strong>Existing projects</strong>
          <p id="category-folder-summary" class="row-meta"></p>
        </div>
        <button id="open-category-folder-modal" type="button">Review projects</button>
      </div>
      <p id="category-folder-status" class="row-meta category-folder-status" role="status" aria-live="polite"></p>
    </section>
  `);
  document.body.insertAdjacentHTML("beforeend", `
    <section id="category-folder-modal" class="category-folder-modal" hidden>
      <div class="category-folder-dialog" role="dialog" aria-modal="true"
        aria-labelledby="category-folder-modal-title" aria-describedby="category-folder-modal-description">
        <header class="category-folder-dialog-header">
          <div>
            <h2 id="category-folder-modal-title">Organize existing projects</h2>
            <p id="category-folder-modal-description">
              Select the complete project folders to move into their metadata category.
            </p>
          </div>
          <button id="close-category-folder-modal" type="button">Close</button>
        </header>
        <p id="category-folder-modal-summary" class="category-folder-modal-summary"></p>
        <div id="category-folder-projects" class="category-folder-projects"
          role="group" aria-label="Existing projects to organize"></div>
        <footer class="category-folder-dialog-footer">
          <p id="category-folder-modal-status" role="status" aria-live="polite"></p>
          <button id="apply-category-folder-migration" class="primary" type="button" disabled>
            Apply selected
          </button>
        </footer>
      </div>
    </section>
  `);
}

// Builds one readable row containing only the project name and its saved metadata category.
function projectRow(project) {
  const row = document.createElement("label");
  row.className = project.eligible
    ? "category-folder-project"
    : "category-folder-project is-blocked";

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "category-folder-project-check";
  checkbox.value = project.source;
  checkbox.disabled = state.busy || !project.eligible;
  checkbox.checked = state.selected.has(project.source);
  if (project.reason) {
    row.title = project.reason;
    checkbox.title = project.reason;
    checkbox.setAttribute(
      "aria-label",
      `${project.name}, category ${project.category || "not assigned"}. ${project.reason}`
    );
  }

  const content = document.createElement("span");
  content.className = "category-folder-project-copy";
  const title = document.createElement("strong");
  title.textContent = project.name;
  const category = document.createElement("span");
  category.className = "row-meta";
  category.textContent = project.category ? `Category: ${project.category}` : "Category: Not assigned";
  content.append(title, category);
  row.append(checkbox, content);
  return row;
}

// Returns the exact saved project roots selected in the modal without rendering their paths.
function selectedProjectPaths() {
  return Array.from(state.selected);
}

// Synchronizes the create-project category requirement whenever Local Mode has already injected its form.
function syncCreateProjectRequirement(settings) {
  const organizer = window.GitDeskLocalOrganizer;
  if (organizer && typeof organizer.applyCategoryFolderSetting === "function") {
    organizer.applyCategoryFolderSetting(settings || {});
  }
}

// Renders the compact setting and, only when opened, the focused project-selection modal.
function renderCategoryFolders() {
  const toggle = byId("create-categories-as-folders");
  const migrationAction = byId("category-folder-migration-action");
  const modal = byId("category-folder-modal");
  const list = byId("category-folder-projects");
  const applyButton = byId("apply-category-folder-migration");
  const eligibleCount = state.projects.filter((project) => project.eligible).length;

  toggle.setAttribute("aria-checked", state.enabled ? "true" : "false");
  toggle.title = state.enabled ? "Turn off category folders" : "Turn on category folders";
  toggle.disabled = state.busy;
  migrationAction.hidden = !state.enabled;
  byId("open-category-folder-modal").disabled = state.busy;
  modal.hidden = !state.modalOpen;
  list.textContent = "";

  if (!state.projects.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Every saved project is already organized.";
    list.append(empty);
  } else {
    state.projects.forEach((project) => list.append(projectRow(project)));
  }

  byId("category-folder-summary").textContent = state.projects.length
    ? `${state.projects.length} project${state.projects.length === 1 ? "" : "s"} need review.`
    : "No projects need to be moved.";
  byId("category-folder-modal-summary").textContent = state.projects.length
    ? `${eligibleCount} of ${state.projects.length} can be selected.`
    : "No existing projects need changes.";
  applyButton.disabled = state.busy || !selectedProjectPaths().length;
  byId("close-category-folder-modal").disabled = state.busy;
}

// Applies a backend response as the sole source of preference and migration-candidate truth.
function applyCategoryFolderState(data) {
  const migration = data && data.migration ? data.migration : {};
  state.enabled = migration.enabled === true;
  state.projects = Array.isArray(migration.projects) ? migration.projects : [];
  const selectable = new Set(
    state.projects.filter((project) => project.eligible).map((project) => project.source)
  );
  state.selected = new Set(Array.from(state.selected).filter((path) => selectable.has(path)));
  if (!state.enabled) {
    state.modalOpen = false;
  }
  syncCreateProjectRequirement(data && data.settings ? data.settings : {});
  renderCategoryFolders();
}

// Loads current candidates so changes made in Local Mode appear when User settings opens.
async function refreshCategoryFolderState() {
  const data = await callNative("categoryFolderSettingsState", {});
  applyCategoryFolderState(data);
}

// Opens the modal and transfers focus into it.
function openMigrationModal() {
  if (!state.enabled || state.busy) {
    return;
  }
  state.returnFocus = document.activeElement;
  state.modalOpen = true;
  byId("category-folder-modal-status").textContent = "";
  renderCategoryFolders();
  byId("close-category-folder-modal").focus();
}

// Closes the modal and returns keyboard focus to the control that opened it.
function closeMigrationModal() {
  if (state.busy || !state.modalOpen) {
    return;
  }
  state.modalOpen = false;
  renderCategoryFolders();
  if (state.returnFocus && typeof state.returnFocus.focus === "function") {
    state.returnFocus.focus();
  }
}

// Persists the switch before changing future project creation behavior.
async function saveCategoryFolderSetting() {
  const requested = !state.enabled;
  const previous = state.enabled;
  let openAfterSave = false;
  state.enabled = requested;
  state.busy = true;
  renderCategoryFolders();
  byId("category-folder-status").textContent = "Saving folder layout setting…";
  setBusy(true);
  try {
    const data = await callNative("saveCreateCategoriesAsFolders", { enabled: requested });
    applyCategoryFolderState(data);
    openAfterSave = requested && state.projects.length > 0;
    byId("category-folder-status").textContent = requested
      ? "Future projects will be created inside their category folders."
      : "Future projects will be created directly inside the selected parent.";
    appendActivity("Category-folder setting saved");
  } catch (error) {
    state.enabled = previous;
    byId("category-folder-status").textContent = error.message || "Could not save the setting.";
    showMessage(error.message || "Could not save the category-folder setting.", true);
    appendActivity(error.message || "Category-folder setting failed", true);
  } finally {
    state.busy = false;
    setBusy(false);
    renderCategoryFolders();
    if (openAfterSave) {
      openMigrationModal();
    }
  }
}

// Moves only checked whole project roots and refreshes every Local Mode path from the backend result.
async function applySelectedMigrations() {
  const projectPaths = selectedProjectPaths();
  if (!projectPaths.length) {
    return;
  }
  state.busy = true;
  renderCategoryFolders();
  byId("category-folder-modal-status").textContent =
    `Moving ${projectPaths.length} complete project folder(s)…`;
  setBusy(true);
  try {
    const data = await callNative("applyCategoryFolderMigration", { project_paths: projectPaths });
    applyCategoryFolderState(data);
    if (window.GitDeskWorkspaceMode && typeof window.GitDeskWorkspaceMode.applyLocalResponse === "function") {
      window.GitDeskWorkspaceMode.applyLocalResponse(data);
    }
    const movedCount = Array.isArray(data.moved) ? data.moved.length : projectPaths.length;
    state.selected.clear();
    byId("category-folder-modal-status").textContent =
      `${movedCount} complete project folder(s) moved.`;
    byId("category-folder-status").textContent = `${movedCount} existing project folder(s) organized.`;
    appendActivity(`${movedCount} project folder(s) moved into categories`);
  } catch (error) {
    byId("category-folder-modal-status").textContent = error.message || "Project migration failed.";
    showMessage(error.message || "Project migration failed.", true);
    appendActivity(error.message || "Project migration failed", true);
  } finally {
    state.busy = false;
    setBusy(false);
    renderCategoryFolders();
  }
}

// Tracks selection independently so rerenders preserve checked projects.
function handleMigrationSelection(event) {
  if (!event.target.classList.contains("category-folder-project-check")) {
    return;
  }
  if (event.target.checked) {
    state.selected.add(event.target.value);
  } else {
    state.selected.delete(event.target.value);
  }
  byId("apply-category-folder-migration").disabled = state.busy || !selectedProjectPaths().length;
}

// Keeps Escape, backdrop dismissal, and Tab navigation contained inside the modal.
function handleModalInteraction(event) {
  if (!state.modalOpen) {
    return;
  }
  if (event.type === "click" && event.target.id === "category-folder-modal") {
    closeMigrationModal();
    return;
  }
  if (event.type !== "keydown") {
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    closeMigrationModal();
    return;
  }
  if (event.key !== "Tab") {
    return;
  }
  const focusable = Array.from(
    byId("category-folder-modal").querySelectorAll("button:not(:disabled), input:not(:disabled)")
  );
  if (!focusable.length) {
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

// Binds the preference and modal after Settings tabs have created the User settings mount.
function bindCategoryFolderSettings() {
  createCategoryFoldersCard();
  if (!document.getElementById("category-folders-card")) {
    return;
  }
  byId("create-categories-as-folders").addEventListener("click", saveCategoryFolderSetting);
  byId("open-category-folder-modal").addEventListener("click", openMigrationModal);
  byId("close-category-folder-modal").addEventListener("click", closeMigrationModal);
  byId("apply-category-folder-migration").addEventListener("click", applySelectedMigrations);
  byId("category-folder-projects").addEventListener("change", handleMigrationSelection);
  byId("category-folder-modal").addEventListener("click", handleModalInteraction);
  document.addEventListener("keydown", handleModalInteraction);
  const userTab = document.getElementById("settings-tab-user");
  if (userTab) {
    userTab.addEventListener("click", () => {
      refreshCategoryFolderState().catch((error) => {
        byId("category-folder-status").textContent = error.message || "Could not refresh existing projects.";
      });
    });
  }
  refreshCategoryFolderState().catch((error) => {
    byId("category-folder-status").textContent = error.message || "Could not load category-folder settings.";
  });
}

// Runs after Settings markup has been injected by the earlier settings-tabs script.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bindCategoryFolderSettings);
} else {
  bindCategoryFolderSettings();
}
})();
