/*
  Categorized compact and full-screen navigation for saved Media albums.
*/

// Keeps album selection surfaces synchronized through one canonical controller callback.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk Media album navigation dependencies did not load.");
}

const { byId, showPanel } = renderHelpers;
const MENU_ID = "media-album-picker-menu";
const TILE_SIZE_DEFAULT = 112;
const TILE_SIZE_MIN = 76;
const TILE_SIZE_MAX = 164;
const VIEWPORT_MARGIN = 12;
const MENU_GAP = 6;
const FOLDER_ICON_SOURCE = "./folder-icon.svg";
let callbacks = {};
let albums = [];
let activeAlbumId = "";
let pendingSelection = false;
let bound = false;

function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function compareLabels(left, right) {
  return String(left || "").localeCompare(String(right || ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

// Returns naturally sorted album groups shared by the picker, library, and photo move menu.
function categorizedAlbums(records) {
  const groups = new Map();
  (records || []).forEach((album) => {
    const category = String(album.category || "").trim() || "Uncategorized";
    if (!groups.has(category)) groups.set(category, []);
    groups.get(category).push(album);
  });
  return Array.from(groups, ([category, groupedAlbums]) => ({
    category,
    albums: groupedAlbums.slice().sort((left, right) => compareLabels(left.name, right.name)),
  })).sort((left, right) => compareLabels(left.category, right.category));
}

function injectSurfaces() {
  if (!document.getElementById(MENU_ID)) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="${MENU_ID}" class="media-album-picker-menu" role="menu"
        aria-label="Saved media albums" hidden></div>
    `);
  }
  if (document.getElementById("panel-media-album-library")) return;
  const panel = document.createElement("section");
  panel.id = "panel-media-album-library";
  panel.className = "panel media-album-library-panel";
  panel.setAttribute("aria-labelledby", "media-album-library-title");
  panel.innerHTML = `
    <header class="media-album-library-header">
      <div class="media-album-library-heading">
        <button id="close-media-album-library" class="icon-button" type="button"
          aria-label="Back to selected album" title="Back to selected album">
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="m14 6-6 6 6 6M8 12h11"></path>
          </svg>
        </button>
        <div>
          <h2 id="media-album-library-title">All Albums</h2>
          <p id="media-album-library-summary">0 albums</p>
        </div>
      </div>
      <div class="media-album-library-scale">
        <label for="media-album-library-size">Icon size</label>
        <input id="media-album-library-size" type="range" min="${TILE_SIZE_MIN}" max="${TILE_SIZE_MAX}"
          step="4" value="${TILE_SIZE_DEFAULT}">
        <output id="media-album-library-size-output" for="media-album-library-size">
          ${TILE_SIZE_DEFAULT}px
        </output>
      </div>
    </header>
    <div id="media-album-library-content" class="media-album-library-content" aria-live="polite"></div>
  `;
  byId("panel-media").after(panel);
}

function optionButtons() {
  return Array.from(byId(MENU_ID).querySelectorAll("[data-media-picker-album-id]"));
}

function closeMenu(restoreFocus = false) {
  byId(MENU_ID).hidden = true;
  byId("media-album-picker-trigger").setAttribute("aria-expanded", "false");
  if (restoreFocus) byId("media-album-picker-trigger").focus();
}

function positionMenu() {
  const trigger = byId("media-album-picker-trigger");
  const menu = byId(MENU_ID);
  const rect = trigger.getBoundingClientRect();
  const width = Math.min(Math.max(rect.width + 48, 248), window.innerWidth - (VIEWPORT_MARGIN * 2));
  const left = Math.min(
    Math.max(rect.left, VIEWPORT_MARGIN),
    Math.max(VIEWPORT_MARGIN, window.innerWidth - width - VIEWPORT_MARGIN),
  );
  const top = Math.max(rect.bottom + MENU_GAP, VIEWPORT_MARGIN);
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  menu.style.width = `${width}px`;
  menu.style.maxHeight = `${Math.max(120, window.innerHeight - top - VIEWPORT_MARGIN)}px`;
}

function openMenu() {
  if (byId("media-album-picker-trigger").disabled) return;
  positionMenu();
  byId(MENU_ID).hidden = false;
  byId("media-album-picker-trigger").setAttribute("aria-expanded", "true");
  const target = optionButtons().find((option) => option.dataset.mediaPickerAlbumId === activeAlbumId)
    || optionButtons()[0];
  if (target) target.focus();
}

async function chooseAlbum(albumId, closeLibraryAfter = false) {
  if (!albumId || pendingSelection) return;
  closeMenu(false);
  if (albumId === activeAlbumId) {
    if (closeLibraryAfter) closeLibrary(true);
    return;
  }
  pendingSelection = true;
  try {
    await callbacks.onAlbumSelect(albumId);
    if (closeLibraryAfter) closeLibrary(true);
  } catch (error) {
    // The shared Media controller owns native error reporting and leaves the selection surface available.
  } finally {
    pendingSelection = false;
  }
}

function handleMenuKeydown(event) {
  const options = optionButtons();
  const index = options.indexOf(document.activeElement);
  let nextIndex = index;
  if (event.key === "ArrowDown") nextIndex = Math.min(index + 1, options.length - 1);
  if (event.key === "ArrowUp") nextIndex = Math.max(index - 1, 0);
  if (event.key === "Home") nextIndex = 0;
  if (event.key === "End") nextIndex = options.length - 1;
  if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    if (options[nextIndex]) options[nextIndex].focus();
  } else if (["Enter", " "].includes(event.key)) {
    event.preventDefault();
    chooseAlbum(document.activeElement.dataset.mediaPickerAlbumId || "");
  } else if (event.key === "Escape") {
    event.preventDefault();
    closeMenu(true);
  }
}

function albumTile(album) {
  const classes = [
    "media-album-library-tile",
    album.id === activeAlbumId ? "selected" : "",
    album.exists ? "" : "missing",
  ].filter(Boolean).join(" ");
  return `
    <button class="${classes}" type="button" data-media-library-album-id="${escapeHtml(album.id)}"
      aria-current="${album.id === activeAlbumId ? "page" : "false"}">
      <span class="media-album-library-artwork">
        <img src="${FOLDER_ICON_SOURCE}" alt="" draggable="false">
      </span>
      <span class="media-album-library-name">${escapeHtml(album.name)}</span>
      ${album.exists ? "" : '<small>Folder missing</small>'}
    </button>
  `;
}

function renderLibrary() {
  const groups = categorizedAlbums(albums);
  const albumLabel = `${albums.length} album${albums.length === 1 ? "" : "s"}`;
  const categoryLabel = `${groups.length} categor${groups.length === 1 ? "y" : "ies"}`;
  byId("media-album-library-summary").textContent = `${albumLabel} · ${categoryLabel}`;
  byId("media-album-library-content").innerHTML = albums.length ? groups.map((group, index) => `
    <section class="media-album-library-category" aria-labelledby="media-album-library-category-${index}">
      <h3 id="media-album-library-category-${index}">${escapeHtml(group.category)}</h3>
      <div class="media-album-library-grid">${group.albums.map(albumTile).join("")}</div>
    </section>
  `).join("") : '<div class="media-album-library-empty">No saved media albums</div>';
}

function openLibrary() {
  callbacks.onPausePreviews();
  showPanel("media-album-library");
  document.querySelector('.tab-button[data-tab="media"]')?.classList.add("active");
  renderLibrary();
  byId("close-media-album-library").focus();
}

function closeLibrary(restoreFocus = false) {
  showPanel("media");
  callbacks.onResumePreviews();
  if (restoreFocus) byId("open-media-album-library").focus();
}

function handleSizeInput(event) {
  const size = Math.min(
    Math.max(Number(event.target.value) || TILE_SIZE_DEFAULT, TILE_SIZE_MIN),
    TILE_SIZE_MAX,
  );
  byId("panel-media-album-library").style.setProperty("--media-album-library-tile-size", `${size}px`);
  byId("media-album-library-size-output").value = `${size}px`;
  event.target.setAttribute("aria-valuetext", `${size} pixel album tiles`);
}

function render(mediaState) {
  closeMenu(false);
  albums = mediaState && Array.isArray(mediaState.albums) ? mediaState.albums : [];
  activeAlbumId = mediaState?.active_album?.id || "";
  const active = albums.find((album) => album.id === activeAlbumId);
  byId("media-album-picker-label").textContent = active
    ? `${active.name}${active.exists ? "" : " — missing"}`
    : albums.length ? "Select an album" : "No media albums";
  byId("media-album-picker-trigger").disabled = !albums.length;
  byId("open-media-album-library").disabled = !albums.length;
  byId(MENU_ID).innerHTML = categorizedAlbums(albums).map((group, index) => `
    <div class="media-album-picker-category" role="group"
      aria-labelledby="media-album-picker-category-${index}">
      <div id="media-album-picker-category-${index}" class="media-album-picker-category-label">
        ${escapeHtml(group.category)}
      </div>
      ${group.albums.map((album) => `
        <button type="button" role="menuitemradio" tabindex="-1"
          data-media-picker-album-id="${escapeHtml(album.id)}" aria-checked="${album.id === activeAlbumId}"
          class="${album.id === activeAlbumId ? "selected" : ""}">
          <span>${escapeHtml(album.name)}</span>${album.exists ? "" : "<small>Missing</small>"}
        </button>
      `).join("")}
    </div>
  `).join("");
  if (byId("panel-media-album-library").classList.contains("active")) renderLibrary();
}

function bind(options) {
  callbacks = options || {};
  injectSurfaces();
  if (bound) return;
  bound = true;
  byId("media-album-picker-trigger").addEventListener("click", () => {
    if (byId(MENU_ID).hidden) openMenu();
    else closeMenu(true);
  });
  byId("media-album-picker-trigger").addEventListener("keydown", (event) => {
    if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
      event.preventDefault();
      openMenu();
    } else if (event.key === "Escape") closeMenu(true);
  });
  byId(MENU_ID).addEventListener("click", (event) => {
    const option = event.target.closest("[data-media-picker-album-id]");
    if (option) chooseAlbum(option.dataset.mediaPickerAlbumId || "");
  });
  byId(MENU_ID).addEventListener("keydown", handleMenuKeydown);
  byId("open-media-album-library").addEventListener("click", openLibrary);
  byId("close-media-album-library").addEventListener("click", () => closeLibrary(true));
  byId("media-album-library-content").addEventListener("click", (event) => {
    const tile = event.target.closest("[data-media-library-album-id]");
    if (tile) chooseAlbum(tile.dataset.mediaLibraryAlbumId || "", true);
  });
  byId("media-album-library-size").addEventListener("input", handleSizeInput);
  document.addEventListener("pointerdown", (event) => {
    if (!event.target.closest(`#${MENU_ID}, #media-album-picker-trigger`)) closeMenu(false);
  });
  document.addEventListener("scroll", (event) => {
    if (event.target !== byId(MENU_ID)) closeMenu(false);
  }, true);
  window.addEventListener("resize", () => closeMenu(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && byId("panel-media-album-library").classList.contains("active")) {
      event.preventDefault();
      closeLibrary(true);
    }
  });
  handleSizeInput({ target: byId("media-album-library-size") });
}

window.GitDeskMediaAlbumNavigation = { bind, categorizedAlbums, render };
})();
