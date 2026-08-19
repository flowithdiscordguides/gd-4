/*
  Full-screen categorized project library for fast visual Local Mode selection.
*/

// Keeps the grid page separate from the compact picker while reusing its canonical sorting and selection behavior.
(() => {
const renderHelpers = window.GitDeskRender;
const projectPicker = window.GitDeskLocalProjectPicker;

if (!renderHelpers || !projectPicker) {
  throw new Error("GitDesk Local project library dependencies did not load.");
}

const { byId, showPanel } = renderHelpers;

// Tile bounds keep the slider useful across compact and presentation-size layouts.
const DEFAULT_TILE_SIZE = 112;
const MIN_TILE_SIZE = 76;
const MAX_TILE_SIZE = 164;

// The packaged folder artwork remains the fallback when neither priority-resolved image can be displayed.
const FOLDER_ICON_SOURCE = "./folder-icon.svg";
let callbacks = {};
let projects = [];
let activeProjectPath = "";
let artworkSignature = "";
let loadedArtworkSignature = "";
let artworkByPath = new Map();
let selectionPending = false;
let bound = false;

// Escapes project metadata before it enters dynamic page markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Inserts the compact icon button immediately after the existing Project dropdown trigger.
function injectTrigger() {
  // Rebinding Local Mode must reuse the existing trigger instead of duplicating an action.
  if (document.getElementById("open-local-project-library")) {
    return;
  }
  byId("local-project-picker-trigger").insertAdjacentHTML("afterend", `
    <button id="open-local-project-library" class="icon-button local-project-library-trigger" type="button"
      aria-label="Open all projects" title="Open all projects" aria-controls="panel-local-project-library">
      <svg aria-hidden="true" viewBox="0 0 24 24">
        <path d="M9 4H4v5M15 4h5v5M20 15v5h-5M9 20H4v-5"></path>
      </svg>
    </button>
  `);
}

// Inserts the dedicated page beside the normal Local Projects panel so standard panel navigation still applies.
function injectPanel() {
  // Rebinding Local Mode must preserve the current panel and its slider state.
  if (document.getElementById("panel-local-project-library")) {
    return;
  }
  const panel = document.createElement("section");
  panel.id = "panel-local-project-library";
  panel.className = "panel local-project-library-panel";
  panel.setAttribute("aria-labelledby", "local-project-library-title");
  panel.innerHTML = `
    <header class="local-project-library-header">
      <div class="local-project-library-heading">
        <button id="close-local-project-library" class="icon-button" type="button"
          aria-label="Back to selected project" title="Back to selected project">
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="m14 6-6 6 6 6M8 12h11"></path>
          </svg>
        </button>
        <div>
          <h2 id="local-project-library-title">All Projects</h2>
          <p id="local-project-library-summary">0 projects</p>
        </div>
      </div>
      <div class="local-project-library-scale">
        <label for="local-project-library-size">Icon size</label>
        <input id="local-project-library-size" type="range" min="${MIN_TILE_SIZE}" max="${MAX_TILE_SIZE}"
          step="4" value="${DEFAULT_TILE_SIZE}">
        <output id="local-project-library-size-output" for="local-project-library-size">
          ${DEFAULT_TILE_SIZE}px
        </output>
      </div>
    </header>
    <div id="local-project-library-content" class="local-project-library-content" aria-live="polite"></div>
  `;
  byId("panel-local").after(panel);
}

// Reloads previews when custom ownership or the physical version supplying automatic artwork changes.
function projectArtworkSignature(records) {
  return JSON.stringify(records.map((project) => [
    project.path || "",
    project.icon_path || "",
    projectPicker.currentVersionPath(project),
  ]));
}

// Returns the validated priority-resolved preview when available, otherwise the packaged folder artwork.
function projectArtwork(project) {
  return artworkByPath.get(project.path) || project.icon_data_url || FOLDER_ICON_SOURCE;
}

// Builds one folder-first tile whose only visible content is its artwork and project name.
function projectTile(project) {
  const projectArtworkAvailable = projectArtwork(project) !== FOLDER_ICON_SOURCE;
  const selected = project.path === activeProjectPath;
  const classes = [
    "local-project-library-tile",
    selected ? "selected" : "",
    project.exists ? "" : "missing",
  ].filter(Boolean).join(" ");
  return `
    <button class="${classes}" type="button" data-library-project-path="${escapeHtml(project.path)}"
      aria-current="${selected ? "page" : "false"}">
      <span class="local-project-library-artwork">
        <img class="${projectArtworkAvailable ? "uses-project-artwork" : "uses-folder-artwork"}"
          src="${escapeHtml(projectArtwork(project))}" alt="" draggable="false"
          data-project-artwork="${String(projectArtworkAvailable)}">
      </span>
      <span class="local-project-library-name">${escapeHtml(project.name)}</span>
    </button>
  `;
}

// Replaces a failed WebView image decode with the same packaged folder fallback used by the identity pane.
function installArtworkFallbacks() {
  byId("local-project-library-content").querySelectorAll('img[data-project-artwork="true"]').forEach((image) => {
    image.addEventListener("error", () => {
      image.dataset.projectArtwork = "false";
      image.className = "uses-folder-artwork";
      image.src = FOLDER_ICON_SOURCE;
    }, { once: true });
  });
}

// Renders category sections with independent responsive grids and no list-style metadata rows.
function renderLibrary() {
  const content = byId("local-project-library-content");
  const groups = projectPicker.categorizedProjects(projects);
  const projectLabel = `${projects.length} project${projects.length === 1 ? "" : "s"}`;
  const categoryLabel = `${groups.length} categor${groups.length === 1 ? "y" : "ies"}`;
  byId("local-project-library-summary").textContent = `${projectLabel} · ${categoryLabel}`;
  // A real empty state keeps the dedicated page understandable before the first project is created.
  if (!projects.length) {
    content.innerHTML = '<div class="local-project-library-empty">No saved local projects</div>';
    return;
  }
  content.innerHTML = groups.map((group, groupIndex) => {
    const labelId = `local-project-library-category-${groupIndex}`;
    return `
      <section class="local-project-library-category" aria-labelledby="${labelId}">
        <h3 id="${labelId}">${escapeHtml(group.category)}</h3>
        <div class="local-project-library-grid">
          ${group.projects.map(projectTile).join("")}
        </div>
      </section>
    `;
  }).join("");
  installArtworkFallbacks();
}

// Marks the Local toolbar item as the parent navigation context for this child page.
function showLibraryPanel() {
  showPanel("local-project-library");
  const localTab = document.querySelector('.tab-button[data-tab="local"]');
  // The library is a child of Local Mode even though it has no duplicate sidebar destination.
  if (localTab) {
    localTab.classList.add("active");
  }
}

// Returns to the normal project workspace and optionally restores focus to the library trigger.
function closeLibrary(restoreFocus = false) {
  showPanel("local");
  // Keyboard exits return to the control that opened the child page.
  if (restoreFocus) {
    byId("open-local-project-library").focus();
  }
}

// Loads every validated project preview only for the visual library, never for routine Local state refreshes.
async function loadArtworkPreviews() {
  // Reuse the last response until a project path, saved override, or current version changes.
  if (!callbacks.onLoadProjectIcons || loadedArtworkSignature === artworkSignature) {
    return;
  }
  const requestedSignature = artworkSignature;
  const panel = byId("panel-local-project-library");
  panel.setAttribute("aria-busy", "true");
  try {
    const data = await callbacks.onLoadProjectIcons();
    const currentPaths = new Set(projects.map((project) => project.path));
    (data && Array.isArray(data.projects) ? data.projects : []).forEach((preview) => {
      // Ignore stale responses and blanks so the current folder fallback remains authoritative.
      if (currentPaths.has(preview.path) && preview.icon_data_url) {
        artworkByPath.set(preview.path, preview.icon_data_url);
      }
    });
    loadedArtworkSignature = requestedSignature;
    renderLibrary();
  } finally {
    panel.removeAttribute("aria-busy");
  }
}

// Opens immediately with folder fallbacks, then upgrades validated custom or automatic artwork.
function openLibrary() {
  showLibraryPanel();
  renderLibrary();
  byId("close-local-project-library").focus();
  loadArtworkPreviews().catch(() => {});
}

// Applies one tile through the canonical project-selection callback before returning to the project workspace.
async function chooseProject(path) {
  // One pending native selection owns navigation so repeated clicks cannot race project state.
  if (!path || selectionPending) {
    return;
  }
  // The active tile needs only to close the library because the dropdown would not reselect it either.
  if (path === activeProjectPath) {
    closeLibrary(true);
    return;
  }
  selectionPending = true;
  byId("panel-local-project-library").setAttribute("aria-busy", "true");
  try {
    await callbacks.onProjectSelect(path);
    closeLibrary(true);
  } catch (error) {
    // The shared Local controller already reports native selection errors and leaves this page available for retry.
  } finally {
    selectionPending = false;
    byId("panel-local-project-library").removeAttribute("aria-busy");
  }
}

// Routes a single tile click to selection without introducing list-style double-click behavior.
function handleLibraryClick(event) {
  const tile = event.target.closest("[data-library-project-path]");
  // Category headings and whitespace are intentionally non-selecting.
  if (tile) {
    chooseProject(tile.dataset.libraryProjectPath || "");
  }
}

// Applies the slider value to exact tile tracks so its visual density changes continuously and predictably.
function handleSizeInput(event) {
  const size = Math.min(Math.max(Number(event.target.value) || DEFAULT_TILE_SIZE, MIN_TILE_SIZE), MAX_TILE_SIZE);
  byId("panel-local-project-library").style.setProperty("--local-project-library-tile-size", `${size}px`);
  byId("local-project-library-size-output").value = `${size}px`;
  event.target.setAttribute("aria-valuetext", `${size} pixel project tiles`);
}

// Gives the child page a familiar Escape route without intercepting keys elsewhere in GitDesk.
function handleDocumentKeydown(event) {
  // Escape belongs to the library only while its panel is the visible workspace.
  if (event.key === "Escape" && byId("panel-local-project-library").classList.contains("active")) {
    event.preventDefault();
    closeLibrary(true);
  }
}

// Binds injected controls once while allowing fresh controller callbacks after Local Mode initialization.
function bind(options) {
  callbacks = options || {};
  injectTrigger();
  injectPanel();
  // Rebinding refreshes callbacks above without stacking duplicate DOM listeners.
  if (bound) {
    return;
  }
  bound = true;
  byId("open-local-project-library").addEventListener("click", openLibrary);
  byId("close-local-project-library").addEventListener("click", () => closeLibrary(true));
  byId("local-project-library-content").addEventListener("click", handleLibraryClick);
  byId("local-project-library-size").addEventListener("input", handleSizeInput);
  document.addEventListener("keydown", handleDocumentKeydown);
  handleSizeInput({ target: byId("local-project-library-size") });
}

// Synchronizes canonical project records and active state after every Local Mode response.
function render(localState) {
  const records = localState && Array.isArray(localState.projects) ? localState.projects : [];
  const nextSignature = projectArtworkSignature(records);
  // Changed icon ownership invalidates every prior page-only preview mapping.
  if (nextSignature !== artworkSignature) {
    artworkByPath = new Map();
    loadedArtworkSignature = "";
  }
  artworkSignature = nextSignature;
  projects = records;
  activeProjectPath = localState && localState.active_project ? localState.active_project : "";
  // The normal state may seed its one active preview before the page-only batch response arrives.
  projects.forEach((project) => {
    if (project.icon_data_url) {
      artworkByPath.set(project.path, project.icon_data_url);
    }
  });
  // An open library updates in place after selection, scanning, icon, or category actions.
  if (document.getElementById("panel-local-project-library")
      && byId("panel-local-project-library").classList.contains("active")) {
    renderLibrary();
  }
}

window.GitDeskLocalProjectLibrary = { bind, render };
})();
