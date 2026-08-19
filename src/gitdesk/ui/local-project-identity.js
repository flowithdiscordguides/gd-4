/*
  Project dropdown, artwork, and metadata controls for the Local Mode project ribbon.
*/

// Owns the project-focused UI while the main Local Mode controller remains responsible for native actions.
(() => {
const renderHelpers = window.GitDeskRender;
const localOrganizer = window.GitDeskLocalOrganizer;
const projectPicker = window.GitDeskLocalProjectPicker;
const projectLibrary = window.GitDeskLocalProjectLibrary;

if (!renderHelpers || !localOrganizer || !projectPicker || !projectLibrary) {
  throw new Error("GitDesk Local Mode project identity dependencies did not load.");
}

const { byId, setText } = renderHelpers;

// The packaged folder asset is the final fallback after custom and latest-version app artwork.
const FOLDER_ICON_SOURCE = "./folder-icon.svg";
let callbacks = {};
let activeProjectPath = "";
let activeProjectName = "";
let activeProjectCategory = "";
let activeProjectRecord = null;
let metadataOpen = false;
let metadataBusy = false;
let metadataReturnFocus = null;

// Returns the active project record represented by the current Local Mode selection.
function activeProject(localState) {
  return (localState.projects || []).find((project) => project.path === localState.active_project) || null;
}

// Settles controller promises locally because native actions already render their own user-facing errors.
function invokeCallback(callback, args, onFailure) {
  if (!callback) {
    return;
  }
  try {
    Promise.resolve(callback(...args)).catch(onFailure || (() => {}));
  } catch (error) {
    if (onFailure) {
      onFailure(error);
    } else {
      console.error("Local project identity action failed", error);
    }
  }
}

// Injects one body-level editor so card overflow cannot clip project metadata controls.
function injectMetadataEditor() {
  if (document.getElementById("local-project-metadata-modal")) {
    return;
  }
  document.body.insertAdjacentHTML("beforeend", `
    <section id="local-project-metadata-modal" class="local-project-metadata-modal" hidden>
      <div id="local-project-metadata-dialog" class="local-project-metadata-dialog" role="dialog" aria-modal="true"
        aria-labelledby="local-project-metadata-title" aria-describedby="local-project-metadata-context" tabindex="-1">
        <header>
          <span>Project identity</span>
          <h2 id="local-project-metadata-title">Edit project details</h2>
          <p id="local-project-metadata-context">Change the selected project's display details and artwork.</p>
        </header>
        <div class="local-project-metadata-body">
          <section class="local-project-metadata-artwork" aria-labelledby="local-project-metadata-artwork-label">
            <span id="local-project-metadata-artwork-label">Project icon</span>
            <div class="local-project-metadata-icon-frame">
              <img id="local-project-metadata-icon" src="./folder-icon.svg" alt="" draggable="false">
            </div>
            <div class="local-project-metadata-icon-actions">
              <button id="choose-local-project-icon-modal" class="icon-button" type="button"
                aria-label="Choose project icon" title="Choose project icon"></button>
              <button id="clear-local-project-icon" class="icon-button" type="button"
                aria-label="Use automatic icon" title="Use automatic icon" hidden></button>
            </div>
            <p id="local-project-metadata-icon-status" aria-live="polite">Folder icon</p>
            <small>Icon changes save immediately.</small>
          </section>
          <form id="local-project-metadata-form" class="local-project-metadata-form">
            <label for="local-project-metadata-name">Project name</label>
            <input id="local-project-metadata-name" type="text" spellcheck="false" autocomplete="off">
            <label for="local-project-metadata-category">Category</label>
            <input id="local-project-metadata-category" type="text" spellcheck="true" autocomplete="off"
              list="local-project-category-options" placeholder="Uncategorized">
            <p id="local-project-metadata-status" role="status" aria-live="polite"></p>
            <div class="local-project-metadata-actions">
              <button id="cancel-local-project-metadata" type="button">Cancel</button>
              <button id="save-local-project-metadata" type="submit">Save changes</button>
            </div>
          </form>
        </div>
      </div>
    </section>
  `);
}

// Renders the backend-selected custom/app source and keeps the packaged folder as the decode-safe fallback.
function renderArtwork(imageId, statusId, project) {
  const image = byId(imageId);
  const status = byId(statusId);
  const artworkSource = project && project.icon_data_url ? project.icon_data_url : "";
  const sourceKind = project && project.icon_source ? project.icon_source : "";
  image.onerror = () => {
    image.onerror = null;
    image.classList.add("uses-folder-icon");
    image.src = FOLDER_ICON_SOURCE;
    if (sourceKind === "app") {
      status.textContent = "App icon unavailable — using folder";
    } else if (sourceKind === "custom") {
      status.textContent = "Custom icon unavailable — using folder";
    } else {
      status.textContent = "Folder icon unavailable";
    }
  };
  image.classList.toggle("uses-folder-icon", !artworkSource);
  image.src = artworkSource || FOLDER_ICON_SOURCE;

  if (artworkSource && sourceKind === "app") {
    status.textContent = "Latest version app icon";
  } else if (artworkSource) {
    status.textContent = project.icon_name || "Custom project icon";
  } else if (project && project.icon_path) {
    status.textContent = "Custom icon unavailable — using folder";
  } else {
    status.textContent = "Folder icon";
  }
}

// Synchronizes the card and modal previews through the same validated active-project data URL.
function renderProjectArtwork(project) {
  renderArtwork("local-project-icon", "local-project-icon-status", project);
  renderArtwork("local-project-metadata-icon", "local-project-metadata-icon-status", project);
  byId("clear-local-project-icon").hidden = !(project && project.icon_path);
}

// Applies modal visibility, busy state, and control availability without replacing draft field values.
function renderMetadataEditor() {
  const modal = byId("local-project-metadata-modal");
  const dialog = byId("local-project-metadata-dialog");
  const hasProject = Boolean(activeProjectPath);
  modal.hidden = !metadataOpen;
  dialog.setAttribute("aria-busy", String(metadataBusy));
  [
    "local-project-metadata-name",
    "local-project-metadata-category",
    "choose-local-project-icon-modal",
    "clear-local-project-icon",
    "cancel-local-project-metadata",
    "save-local-project-metadata",
  ].forEach((id) => {
    byId(id).disabled = metadataBusy || !hasProject;
  });
  byId("save-local-project-metadata").textContent = metadataBusy ? "Saving…" : "Save changes";
}

// Renders active-project identity, metadata fields, and unavailable-project states as one coherent ribbon.
function render(localState, settings) {
  const project = activeProject(localState);
  const hasProject = Boolean(project);
  const hasAvailableProject = Boolean(project && project.exists);
  const nextProjectPath = project ? project.path : "";
  const nextProjectName = project ? project.name : "";
  activeProjectPath = nextProjectPath;
  activeProjectName = nextProjectName;
  activeProjectCategory = project ? project.category || "" : "";
  activeProjectRecord = project;
  localOrganizer.renderCategoryOptions(localState, settings || {});
  projectPicker.render(localState.projects || [], localState.active_project || "");
  projectLibrary.render(localState);
  renderProjectArtwork(project);
  if (!project) {
    setText("local-summary", "No local project selected");
  }

  setText("local-active-project-category", activeProjectCategory || "Uncategorized");
  byId("edit-local-project-metadata").disabled = !hasAvailableProject;
  byId("remove-active-local-project").disabled = !hasProject;
  renderMetadataEditor();
}

// Opens the editor with current metadata and moves keyboard focus into the first editable field.
function openMetadataEditor(trigger) {
  if (!activeProjectPath || metadataBusy) {
    return;
  }
  metadataOpen = true;
  metadataReturnFocus = trigger || document.activeElement;
  byId("local-project-metadata-name").value = activeProjectName;
  byId("local-project-metadata-category").value = activeProjectCategory;
  byId("local-project-metadata-status").textContent = "";
  byId("edit-local-project-metadata").setAttribute("aria-expanded", "true");
  document.querySelector(".app-shell").setAttribute("inert", "");
  renderProjectArtwork(activeProjectRecord);
  renderMetadataEditor();
  byId("local-project-metadata-name").focus();
  byId("local-project-metadata-name").select();
}

// Closes an idle editor, restores the app shell, and returns focus to the pencil that opened it.
function closeMetadataEditor() {
  if (!metadataOpen || metadataBusy) {
    return;
  }
  const returnFocus = metadataReturnFocus;
  metadataOpen = false;
  metadataReturnFocus = null;
  byId("edit-local-project-metadata").setAttribute("aria-expanded", "false");
  document.querySelector(".app-shell").removeAttribute("inert");
  renderMetadataEditor();
  if (returnFocus && returnFocus.isConnected && typeof returnFocus.focus === "function") {
    returnFocus.focus();
  }
}

// Saves changed name and category values through their existing native mutation paths in dependency order.
async function saveMetadata(event) {
  event.preventDefault();
  if (!activeProjectPath || metadataBusy) {
    return;
  }
  const nextName = byId("local-project-metadata-name").value.trim();
  const nextCategory = byId("local-project-metadata-category").value.trim();
  if (!nextName) {
    byId("local-project-metadata-status").textContent = "Project name is required.";
    byId("local-project-metadata-name").focus();
    return;
  }
  metadataBusy = true;
  byId("local-project-metadata-status").textContent = "Saving project metadata…";
  renderMetadataEditor();
  try {
    if (nextName !== activeProjectName) {
      await callbacks.onRename(activeProjectPath, nextName);
    }
    if (nextCategory !== activeProjectCategory) {
      await callbacks.onCategoryChange(activeProjectPath, nextCategory);
    }
    metadataBusy = false;
    closeMetadataEditor();
  } catch (error) {
    metadataBusy = false;
    byId("local-project-metadata-status").textContent =
      error.message || "GitDesk could not save the project metadata.";
    renderMetadataEditor();
    byId("save-local-project-metadata").focus();
  }
}

// Runs one modal artwork action while preserving the editor and showing localized failure feedback.
async function runMetadataIconAction(callback) {
  if (!activeProjectPath || metadataBusy || !callback) {
    return;
  }
  metadataBusy = true;
  byId("local-project-metadata-status").textContent = "Updating project icon…";
  renderMetadataEditor();
  try {
    await callback(activeProjectPath);
    byId("local-project-metadata-status").textContent = "";
  } catch (error) {
    byId("local-project-metadata-status").textContent =
      error.message || "GitDesk could not update the project icon.";
  } finally {
    metadataBusy = false;
    renderMetadataEditor();
  }
}

// Removes the active registry record through the existing non-destructive Local Mode action.
function handleRemoveProject() {
  if (activeProjectPath) {
    invokeCallback(callbacks.onRemove, [activeProjectPath]);
  }
}

// Supports backdrop dismissal, Escape, and a contained modal keyboard cycle.
function handleMetadataInteraction(event) {
  if (!metadataOpen || metadataBusy) {
    return;
  }
  if (event.type === "click" && event.target.id === "local-project-metadata-modal") {
    closeMetadataEditor();
    return;
  }
  if (event.type !== "keydown") {
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    closeMetadataEditor();
    return;
  }
  if (event.key !== "Tab") {
    return;
  }
  const controls = Array.from(byId("local-project-metadata-dialog").querySelectorAll(
    "button:not(:disabled), input:not(:disabled)",
  ));
  const first = controls[0];
  const last = controls[controls.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

// Binds identity controls after local-render.js injects the complete Local Mode panel.
function bind(options) {
  callbacks = options || {};
  injectMetadataEditor();
  projectPicker.bind({
    onProjectSelect: (path) => invokeCallback(callbacks.onProjectChange, [path]),
    onOpenCurrentVersion: (path) => invokeCallback(callbacks.onOpenCurrentVersion, [path]),
  });
  projectLibrary.bind({
    onProjectSelect: callbacks.onProjectChange,
    onLoadProjectIcons: callbacks.onLoadProjectIcons,
  });
  byId("edit-local-project-metadata").addEventListener("click", (event) => {
    openMetadataEditor(event.currentTarget);
  });
  byId("remove-active-local-project").addEventListener("click", handleRemoveProject);
  byId("local-project-metadata-form").addEventListener("submit", (event) => {
    saveMetadata(event).catch(() => {});
  });
  byId("choose-local-project-icon-modal").addEventListener("click", () => {
    runMetadataIconAction(callbacks.onChooseIcon).catch(() => {});
  });
  byId("clear-local-project-icon").addEventListener("click", () => {
    runMetadataIconAction(callbacks.onClearIcon).catch(() => {});
  });
  byId("cancel-local-project-metadata").addEventListener("click", closeMetadataEditor);
  byId("local-project-metadata-modal").addEventListener("click", handleMetadataInteraction);
  document.addEventListener("keydown", handleMetadataInteraction);
}

window.GitDeskLocalProjectIdentity = { bind, render, setPending: projectPicker.setPending };
})();
