/*
  Shared category suggestions for Local Mode project creation and active-project metadata.
*/

// Keeps create-modal category behavior reusable while project identity rendering lives in its own module.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk local organizer dependencies did not load.");
}

const { byId } = renderHelpers;

// Stable IDs keep create-modal suggestions and active-project datalist references synchronized.
const CATEGORY_OPTIONS_ID = "local-project-category-options";
const CREATE_CATEGORY_MENU_ID = "local-project-category-menu";
let lastLocalState = { projects: [] };
let lastSettings = {};

// Escapes saved category values before rendering custom menu and datalist options.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Adds the shared category input and in-app suggestion menu to the create-project form.
function injectCreateCategoryField() {
  if (!document.getElementById("local-project-category")) {
    byId("local-project-name").insertAdjacentHTML("afterend", `
      <label for="local-project-category">Category</label>
      <div class="local-category-field">
        <input id="local-project-category" type="text" spellcheck="true" autocomplete="off"
          placeholder="Client work" role="combobox" aria-autocomplete="list"
          aria-expanded="false" aria-controls="${CREATE_CATEGORY_MENU_ID}"
          aria-describedby="local-project-category-requirement">
        <div id="${CREATE_CATEGORY_MENU_ID}" class="local-category-menu" role="listbox" hidden></div>
      </div>
      <p id="local-project-category-requirement" class="row-meta" hidden>
        Required because Create categories as folders is on.
      </p>
    `);
  }
  if (!document.getElementById(CATEGORY_OPTIONS_ID)) {
    byId("local-project-category").insertAdjacentHTML("afterend", `<datalist id="${CATEGORY_OPTIONS_ID}"></datalist>`);
  }
}

// Builds unique category choices from explicit settings and categories already assigned to projects.
function categoryOptions(localState, settings) {
  const categories = [];
  const savedCategories = settings && settings.local_project_categories ? settings.local_project_categories : [];
  savedCategories.concat(localState.projects || []).forEach((item) => {
    const category = String(item && item.category ? item.category : item || "").trim();
    if (category && categories.indexOf(category) < 0) {
      categories.push(category);
    }
  });
  return categories;
}

// Returns the create-project category input after the shared project modal has been injected.
function createCategoryInput() {
  return document.getElementById("local-project-category");
}

// Reflects the saved path-layout preference in the create form's native required state and guidance.
function applyCategoryFolderSetting(settings) {
  const input = createCategoryInput();
  const requirement = document.getElementById("local-project-category-requirement");
  const required = settings && settings.create_categories_as_folders === true;
  if (input) {
    input.required = required;
  }
  if (requirement) {
    requirement.hidden = !required;
  }
}

// Filters saved categories against the current create-project input so the menu stays concise.
function matchingCreateCategories() {
  const input = createCategoryInput();
  const search = input ? input.value.trim().toLowerCase() : "";
  return categoryOptions(lastLocalState, lastSettings).filter((category) => (
    !search || category.toLowerCase().indexOf(search) >= 0
  ));
}

// Renders matching categories inside the app rather than relying on inconsistent native datalist popovers.
function renderCreateCategoryMenu() {
  const input = createCategoryInput();
  const menu = document.getElementById(CREATE_CATEGORY_MENU_ID);
  if (!input || !menu) {
    return;
  }
  const options = matchingCreateCategories();
  menu.innerHTML = options.map((category) => `
    <button type="button" role="option" data-category="${escapeHtml(category)}">
      ${escapeHtml(category)}
    </button>
  `).join("");
  const visible = document.activeElement === input && Boolean(options.length);
  menu.hidden = !visible;
  input.setAttribute("aria-expanded", String(visible));
}

// Closes the category menu and restores the combobox accessibility state.
function closeCreateCategoryMenu() {
  const input = createCategoryInput();
  const menu = document.getElementById(CREATE_CATEGORY_MENU_ID);
  if (menu) {
    menu.hidden = true;
  }
  if (input) {
    input.setAttribute("aria-expanded", "false");
  }
}

// Commits a pointer-selected category while returning focus to the create form input.
function chooseCreateCategory(event) {
  const button = event.target.closest("[data-category]");
  if (!button) {
    return;
  }
  event.preventDefault();
  byId("local-project-category").value = button.dataset.category || "";
  closeCreateCategoryMenu();
  byId("local-project-category").focus();
}

// Refreshes suggestions only for changes made in the create-project category field.
function handleCreateCategoryInput(event) {
  if (event.target.id === "local-project-category") {
    renderCreateCategoryMenu();
  }
}

// Closes the create menu when pointer focus moves beyond its shared category field.
function handleDocumentClick(event) {
  if (!event.target.closest(".local-category-field")) {
    closeCreateCategoryMenu();
  }
}

// Refreshes category sources for both the create form and active-project category datalist.
function renderCategoryOptions(localState, settings) {
  injectCreateCategoryField();
  lastLocalState = localState || { projects: [] };
  lastSettings = settings || {};
  applyCategoryFolderSetting(lastSettings);
  byId(CATEGORY_OPTIONS_ID).innerHTML = categoryOptions(lastLocalState, lastSettings).map((category) => (
    `<option value="${escapeHtml(category)}"></option>`
  )).join("");
  renderCreateCategoryMenu();
}

// Binds create-category interactions once after Project Hub and Local Mode have injected their markup.
function bind() {
  injectCreateCategoryField();
  byId("local-project-category").addEventListener("focus", renderCreateCategoryMenu);
  byId("local-project-category").addEventListener("input", handleCreateCategoryInput);
  byId(CREATE_CATEGORY_MENU_ID).addEventListener("mousedown", chooseCreateCategory);
  document.addEventListener("click", handleDocumentClick);
}

window.GitDeskLocalOrganizer = {
  bind,
  applyCategoryFolderSetting,
  injectCreateCategoryField,
  renderCategoryOptions,
};
})();
