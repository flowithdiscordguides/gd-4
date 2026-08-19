/*
  Shared Resources catalog management for Settings and Overview.
*/

// Keeps Shared Resources UI state private while exposing a small app integration API.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk Shared Resources dependencies did not load.");
}

const { appendActivity, byId, showMessage } = renderHelpers;
let runActionRef = null;
const state = {
  root: "",
  categories: [],
  selected: [],
};

// Escapes category names and paths before rendering them into settings/overview surfaces.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Applies backend category state to both UI surfaces.
function applyCategoryState(data) {
  state.root = data.root || "";
  state.categories = data.categories || [];
  state.selected = data.selected || [];
  renderSettings();
  renderDialog();
  renderOverviewPanel();
}

// Injects the User settings tab section without growing index.html beyond its line ceiling.
function injectSettingsSection() {
  const mount = document.getElementById("settings-user-content")
    || document.querySelector("#panel-settings .settings-grid");
  if (!mount || document.getElementById("ai-skills-block")) return;

  mount.insertAdjacentHTML("beforeend", `
    <section id="ai-skills-block" class="settings-block ai-skills-block">
      <label>Shared Resources</label>
      <form id="ai-skill-form" class="ai-skill-form">
        <input id="ai-skill-name" type="text" spellcheck="false" placeholder="coding">
        <button id="create-ai-skill-category" type="submit">Create resource</button>
      </form>
      <p class="row-meta">Reusable project files live under <code id="ai-skills-root">Not loaded</code></p>
      <p class="row-meta">Legacy means no numbered version was detected. Record a vN release for version tracking.</p>
      <div id="ai-skill-category-list" class="ai-skill-category-list" aria-live="polite"></div>
    </section>
  `);
}

// Injects the Overview Shared Resources dialog used to create resources and open folders.
function injectOverviewDialog() {
  if (document.getElementById("ai-skills-dialog")) return;

  document.body.insertAdjacentHTML("beforeend", `
    <section id="ai-skills-dialog" class="ai-skills-dialog" hidden>
      <div class="ai-skills-dialog-panel" role="dialog" aria-modal="true">
        <div class="panel-header">
          <div>
            <h2>Shared Resources</h2>
            <p>Create reusable file groups and choose the defaults for new projects.</p>
          </div>
          <button id="close-ai-skills-dialog" type="button">Close</button>
        </div>
        <form id="ai-skill-dialog-form" class="ai-skill-form">
          <input id="ai-skill-dialog-name" type="text" spellcheck="false" placeholder="coding">
          <button type="submit">Create resource</button>
        </form>
        <p class="row-meta">Resource files live under <code id="ai-skills-dialog-root">Not loaded</code></p>
        <div id="ai-skill-dialog-list" class="ai-skill-dialog-list" aria-live="polite"></div>
      </div>
    </section>
  `);
}

// Renders the Settings category list and open-folder actions.
function renderSettings() {
  if (!document.getElementById("ai-skills-block")) return;

  byId("ai-skills-root").textContent = state.root || "Not loaded";
  const list = byId("ai-skill-category-list");
  if (!state.categories.length) {
    list.innerHTML = '<div class="empty-state">No Shared Resources yet</div>';
    return;
  }

  list.innerHTML = state.categories.map((category) => `
    <div class="ai-skill-category-row">
      <div>
        <div class="row-title">${escapeHtml(category.name)}</div>
        <div class="row-meta">${escapeHtml(category.working_file_count)} working files ·
          ${escapeHtml(category.version_label)}${category.has_unrecorded_changes
            ? " · changes not recorded" : ""}</div>
        ${category.tracking_message
          ? `<div class="row-meta">${escapeHtml(category.tracking_message)}</div>` : ""}
      </div>
      <div class="ai-skill-category-actions">
        <button class="open-ai-skill-category" type="button" data-name="${escapeHtml(category.name)}"
          ${category.source_available ? "" : "disabled"}>Open folder</button>
        <button class="record-shared-resource" type="button" data-name="${escapeHtml(category.name)}"
          ${category.source_available ? "" : "disabled"}>
          ${category.recorded ? "Update" : "Record version"}
        </button>
      </div>
    </div>
  `).join("");
}

// Renders the Overview dialog category checklist and open-folder actions.
function renderDialog() {
  if (!document.getElementById("ai-skills-dialog")) return;

  byId("ai-skills-dialog-root").textContent = state.root || "Not loaded";
  const list = byId("ai-skill-dialog-list");
  if (!state.categories.length) {
    list.innerHTML = '<div class="empty-state">No Shared Resources yet</div>';
    return;
  }

  list.innerHTML = state.categories.map((category) => {
    const checked = state.selected.indexOf(category.name) >= 0 ? "checked" : "";
    const disabled = category.recorded ? "" : "disabled";
    return `
      <div class="ai-skill-category-row">
        <label class="ai-skill-check-row">
          <input
            type="checkbox"
            class="ai-skill-category-check"
            value="${escapeHtml(category.name)}"
            ${checked}
            ${disabled}
          >
          <span>${escapeHtml(category.name)} · ${escapeHtml(category.version_label)}</span>
        </label>
        <div class="ai-skill-category-actions">
          <button class="open-ai-skill-category" type="button" data-name="${escapeHtml(category.name)}">
            Add files
          </button>
          <button class="add-ai-skill-to-repo" type="button" data-name="${escapeHtml(category.name)}"
            ${disabled}>
            Add to repo
          </button>
        </div>
      </div>
    `;
  }).join("");
}

// Builds the Overview button that opens Shared Resources management.
function renderOverviewPanel() {
  const panel = document.getElementById("ai-skill-overview-panel");
  if (!panel) return;

  const selected = state.selected.length ? `${state.selected.length} selected` : "No resources selected";
  panel.innerHTML = `
    <button id="open-ai-skills-dialog" type="button">Manage Shared Resources</button>
    <p class="row-meta">${escapeHtml(selected)}</p>
  `;
}

// Fetches the current category list from Python.
async function refreshCategories() {
  const data = await runActionRef("listSharedResources", {});
  applyCategoryState(data);
}

// Creates a category from an input element id and clears the field after success.
async function createCategoryFromInput(inputId) {
  const input = byId(inputId);
  const name = input.value.trim();
  const data = await runActionRef("createSharedResource", { name }, "Shared Resource created");
  input.value = "";
  applyCategoryState(data);
}

// Creates one category folder from the Settings form.
async function createCategory(event) {
  event.preventDefault();
  await createCategoryFromInput("ai-skill-name");
}

// Creates one category folder from the Overview dialog.
async function createCategoryFromDialog(event) {
  event.preventDefault();
  await createCategoryFromInput("ai-skill-dialog-name");
}

// Opens one category folder in the platform file manager.
async function openCategory(name) {
  await runActionRef("openSharedResource", { name }, "Shared Resource folder opened");
}

// Records manual folder additions, removals, and edits as the next numbered release only on explicit user action.
async function recordResource(name) {
  const data = await runActionRef(
    "recordSharedResourceUpdate",
    { name },
    "Shared Resource version recorded",
  );
  applyCategoryState(data);
  if (window.GitDeskWorkspaceMode) {
    window.GitDeskWorkspaceMode.refreshLocalState().catch(() => {});
  }
  const release = data.recorded_release || {};
  showMessage(release.changed
    ? `${name} recorded as ${release.version_label}.`
    : `${name} has no unrecorded changes.`);
}

// Copies one category folder into the current active repository.
async function addCategoryToRepo(name) {
  const data = await runActionRef("addSharedResourceToRepo", { name }, "Shared Resource added to repo");
  showMessage(`${data.file_count} Shared Resource files added to the repo root.`);
  if (data.status && window.GitDeskOverview) {
    window.GitDeskOverview.applyStatus(data.status);
  }
}

// Persists the selected Overview categories.
async function saveSelection() {
  const checks = document.querySelectorAll(".ai-skill-category-check");
  const categories = Array.from(checks).filter((check) => check.checked).map((check) => check.value);
  const data = await runActionRef("saveSharedResourceSelection", { resources: categories }, "Defaults saved");
  applyCategoryState(data);
}

// Opens the Overview Shared Resources dialog.
async function openModal() {
  byId("ai-skills-dialog").hidden = false;
  await refreshCategories();
}

// Closes the Overview Shared Resources dialog.
function closeModal() {
  byId("ai-skills-dialog").hidden = true;
}

// Handles delegated Settings clicks for category folders.
function handleSettingsClick(event) {
  const openButton = event.target.closest(".open-ai-skill-category");
  if (openButton) {
    openCategory(openButton.dataset.name || "");
    return;
  }
  const recordButton = event.target.closest(".record-shared-resource");
  if (recordButton) {
    recordResource(recordButton.dataset.name || "").catch(
      (error) => showMessage(error.message || "Shared Resource update failed.", true),
    );
  }
}

// Handles the Overview toggle and checklist changes.
function handleOverviewClick(event) {
  if (event.target.id === "open-ai-skills-dialog") {
    openModal().catch((error) => appendActivity(error.message || "Shared Resources failed", true));
  }
}

// Handles dialog close and open-folder actions.
function handleDialogClick(event) {
  if (event.target.id === "close-ai-skills-dialog" || event.target.id === "ai-skills-dialog") {
    closeModal();
    return;
  }

  const button = event.target.closest(".open-ai-skill-category");
  if (button) {
    openCategory(button.dataset.name || "");
    return;
  }

  const addButton = event.target.closest(".add-ai-skill-to-repo");
  if (addButton) {
    addCategoryToRepo(addButton.dataset.name || "");
  }
}

// Binds the dynamically injected Settings section and Overview Shared Resources controls.
function bind(runAction) {
  runActionRef = runAction;
  injectSettingsSection();
  injectOverviewDialog();
  byId("ai-skill-form").addEventListener("submit", createCategory);
  byId("ai-skill-dialog-form").addEventListener("submit", createCategoryFromDialog);
  byId("ai-skill-category-list").addEventListener("click", handleSettingsClick);
  byId("ai-skills-dialog").addEventListener("click", handleDialogClick);
  byId("diff-viewer").addEventListener("click", handleOverviewClick);
  byId("ai-skill-dialog-list").addEventListener("change", (event) => {
    if (event.target.classList.contains("ai-skill-category-check")) {
      saveSelection().catch((error) => showMessage(error.message || "Shared Resources failed.", true));
    }
  });
  refreshCategories().catch((error) => appendActivity(error.message || "Shared Resources failed", true));
}

// Publishes the small API used by Overview after it re-renders repo actions.
window.GitDeskAISkills = {
  bind,
  refresh: refreshCategories,
  renderOverviewPanel,
};
})();
