/*
  App-owned Media context menu for copying originals and moving photos between registered albums.
*/

// Keeps file clipboard writes and deliberate photo movement behind one focused thumbnail action menu.
(() => {
const renderHelpers = window.GitDeskRender;
const albumNavigation = window.GitDeskMediaAlbumNavigation;

if (!renderHelpers || !albumNavigation) {
  throw new Error("GitDesk Media item action dependencies did not load.");
}

const { byId } = renderHelpers;
const MENU_ID = "media-photo-move-menu";
const VIEWPORT_MARGIN = 10;
let callbacks = {};
let albums = [];
let sourcePath = "";
let sourceTile = null;
let actionPending = false;
let bound = false;

// Escapes album metadata before the move destinations enter contextual-menu markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Dismisses the item menu and optionally restores keyboard focus to the originating thumbnail.
function closeMenu(restoreFocus = false) {
  const menu = document.getElementById(MENU_ID);
  if (menu) menu.hidden = true;
  if (restoreFocus && sourceTile) sourceTile.querySelector(".media-tile-select")?.focus();
  sourcePath = "";
  sourceTile = null;
}

// Keeps the contextual action surface fully visible beside edge-positioned thumbnails.
function positionMenu(x, y) {
  const menu = byId(MENU_ID);
  menu.hidden = false;
  menu.style.visibility = "hidden";
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
  const rect = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(VIEWPORT_MARGIN, Math.min(x, window.innerWidth - rect.width - VIEWPORT_MARGIN))}px`;
  menu.style.top = `${Math.max(VIEWPORT_MARGIN, Math.min(y, window.innerHeight - rect.height - VIEWPORT_MARGIN))}px`;
  menu.style.visibility = "";
}

// Builds Copy for every media tile and retains move destinations only for image originals.
function openMenu(event, tile) {
  const active = callbacks.activeAlbum();
  const canMove = tile.dataset.mediaKind === "image";
  const destinations = canMove
    ? albums.filter((album) => album.id !== active?.id && album.exists)
    : [];
  if (!active || !active.exists || actionPending) return;
  event.preventDefault();
  event.stopPropagation();
  sourcePath = tile.dataset.mediaPath || "";
  sourceTile = tile;
  const groups = albumNavigation.categorizedAlbums(destinations);
  byId(MENU_ID).innerHTML = `
    <button class="media-photo-copy-button" type="button" role="menuitem" data-media-copy-item>Copy</button>
    ${canMove ? `
      <div class="media-photo-move-heading">Move photo to</div>
      ${groups.length ? groups.map((group) => `
        <div class="media-photo-move-category" role="group">
          <span>${escapeHtml(group.category)}</span>
          ${group.albums.map((album) => `
            <button type="button" role="menuitem" data-media-move-album-id="${escapeHtml(album.id)}">
              ${escapeHtml(album.name)}
            </button>
          `).join("")}
        </div>
      `).join("") : '<div class="media-photo-move-empty">No other available albums</div>'}
    ` : ""}
  `;
  const tileBounds = tile.getBoundingClientRect();
  const x = event.clientX || tileBounds.left + 12;
  const y = event.clientY || tileBounds.top + 12;
  positionMenu(x, y);
  const firstOption = byId(MENU_ID).querySelector("[role=menuitem]");
  (firstOption || byId(MENU_ID)).focus();
}

// Copies the resolved original as a native file reference while keeping its absolute path outside the WebView.
async function copyItem() {
  const active = callbacks.activeAlbum();
  if (!active || !sourcePath || actionPending) return;
  const path = sourcePath;
  closeMenu(true);
  actionPending = true;
  try {
    await callbacks.runAction("copyMediaItem", {
      album_id: active.id,
      path,
    }, "Media file copied");
  } finally {
    actionPending = false;
  }
}

// Moves one photo only after an explicit destination selection from the current contextual menu.
async function movePhoto(albumId) {
  const active = callbacks.activeAlbum();
  if (!active || !albumId || !sourcePath || actionPending) return;
  const destination = albums.find((album) => album.id === albumId);
  const path = sourcePath;
  closeMenu();
  actionPending = true;
  try {
    const data = await callbacks.runAction("moveMediaItem", {
      ...callbacks.queryPayload(),
      album_id: active.id,
      destination_album_id: albumId,
      path,
    }, `Photo moved to ${destination?.name || "album"}`);
    callbacks.applyState(data);
  } finally {
    actionPending = false;
  }
}

// Clears stale context state whenever a refreshed Media response rebuilds the contact sheet.
function render(mediaState) {
  closeMenu();
  albums = mediaState && Array.isArray(mediaState.albums) ? mediaState.albums : [];
}

// Installs one delegated thumbnail menu and its pointer, keyboard, dismissal, and action handlers.
function bind(options) {
  callbacks = options || {};
  if (!document.getElementById(MENU_ID)) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="${MENU_ID}" class="media-photo-move-menu" role="menu"
        aria-label="Media item actions" tabindex="-1" hidden></div>
    `);
  }
  if (bound) return;
  bound = true;
  byId("panel-media").addEventListener("contextmenu", (event) => {
    const tile = event.target.closest(".media-tile");
    if (tile) openMenu(event, tile);
  });
  byId(MENU_ID).addEventListener("click", (event) => {
    const copyOption = event.target.closest("[data-media-copy-item]");
    if (copyOption) {
      copyItem().catch(() => {});
      return;
    }
    const option = event.target.closest("[data-media-move-album-id]");
    if (option) movePhoto(option.dataset.mediaMoveAlbumId || "").catch(() => {});
  });
  byId(MENU_ID).addEventListener("keydown", (event) => {
    const options = Array.from(byId(MENU_ID).querySelectorAll("[role=menuitem]"));
    const currentIndex = options.indexOf(document.activeElement);
    let nextIndex = currentIndex;
    if (event.key === "ArrowDown") nextIndex = Math.min(currentIndex + 1, options.length - 1);
    if (event.key === "ArrowUp") nextIndex = Math.max(currentIndex - 1, 0);
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = options.length - 1;
    if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      if (options[nextIndex]) options[nextIndex].focus();
    }
  });
  document.addEventListener("pointerdown", (event) => {
    if (!event.target.closest(`#${MENU_ID}`)) closeMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenu(true);
  });
  document.addEventListener("scroll", closeMenu, true);
  window.addEventListener("resize", closeMenu);
}

window.GitDeskMediaItemMove = { bind, render };
})();
