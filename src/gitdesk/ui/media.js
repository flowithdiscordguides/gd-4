/*
  Media Mode controller for folder-backed albums and Shared Resource publication.
*/

// Coordinates bounded album state, lazy previews, and explicit user actions.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const mediaRender = window.GitDeskMediaRender;
const mediaAlbumNavigation = window.GitDeskMediaAlbumNavigation;
const mediaIntake = window.GitDeskMediaIntake;
const mediaClipboard = window.GitDeskMediaClipboard;
const mediaItemMove = window.GitDeskMediaItemMove;

if (
  !nativeBridge
  || !renderHelpers
  || !mediaRender
  || !mediaAlbumNavigation
  || !mediaIntake
  || !mediaClipboard
  || !mediaItemMove
) {
  throw new Error("GitDesk Media Mode dependencies did not load.");
}

const { callNative } = nativeBridge;
const { appendActivity, byId, setBusy, showMessage } = renderHelpers;
const state = {
  media: { albums: [], items: [], page: 1, page_count: 0 },
  selectedPath: "",
  loaded: false,
  previewActive: 0,
  previewActivePaths: new Set(),
  previewFrame: 0,
  previewGeneration: 0,
  previewQueue: [],
  previewKeys: new Set(),
};

// Runs a user-initiated Media action with shared busy, error, and Activity feedback.
async function runAction(action, payload, successMessage) {
  setBusy(true);
  showMessage("");
  try {
    const data = await callNative(action, payload || {});
    if (successMessage) appendActivity(successMessage);
    return data;
  } catch (error) {
    const message = error.message || "Media Mode operation failed.";
    console.error(`Native action failed: ${action}`, error);
    showMessage(message, true);
    appendActivity(message, true);
    throw error;
  } finally {
    setBusy(false);
  }
}

// Returns current contact-sheet controls in the native paging request shape.
function queryPayload(page = state.media.page || 1) {
  return {
    query: byId("media-search").value,
    kind: byId("media-kind").value,
    sort: byId("media-sort").value,
    page,
    page_size: 48,
  };
}

// Returns the active album record, when one remains selected.
function activeAlbum() {
  return state.media.active_album || null;
}

// Returns the selected item from the current bounded page.
function selectedItem() {
  return (state.media.items || []).find((item) => item.path === state.selectedPath) || null;
}

// Re-renders state and schedules only previews that are active in the contact-sheet viewport.
function applyState(data) {
  resetPreviewSession();
  state.media = data || state.media;
  if (!selectedItem()) state.selectedPath = "";
  mediaRender.renderState(state.media, state.selectedPath);
  mediaRender.renderInspector(selectedItem());
  mediaAlbumNavigation.render(state.media);
  mediaIntake.render(state.media);
  mediaItemMove.render(state.media);
  scheduleActivePreviews();
}

// Loads the current album page without touching repository or Local Mode state.
async function refresh(page = state.media.page || 1) {
  const data = await runAction("mediaLibraryState", queryPayload(page), "");
  state.loaded = true;
  applyState(data);
}

// Activates Media Mode once and resumes transient previews after later mode switches.
function activate() {
  if (!state.loaded) {
    refresh(1).catch(() => {});
  } else {
    scheduleActivePreviews();
  }
}

// Returns the current item for a path in the bounded rendered page.
function itemForPath(path) {
  return (state.media.items || []).find((item) => item.path === path) || null;
}

// Clears pending work and actively releases every rendered preview when its Media session ends.
function resetPreviewSession(releaseRendered = false) {
  state.previewGeneration += 1;
  state.previewQueue = [];
  state.previewKeys = new Set();
  state.previewActivePaths = new Set();
  if (state.previewFrame) {
    window.cancelAnimationFrame(state.previewFrame);
    state.previewFrame = 0;
  }
  if (releaseRendered) {
    (state.media.items || []).forEach((item) => mediaRender.releasePreview(item));
    mediaRender.renderInspector(selectedItem());
  }
}

// Stops all preview retention as soon as the user leaves Media Mode.
function deactivate() {
  resetPreviewSession(true);
}

// Decodes one thumbnail at a time and discards responses whose tile is no longer active.
function drainPreviewQueue() {
  while (state.previewActive < 1 && state.previewQueue.length) {
    const request = state.previewQueue.shift();
    state.previewActive += 1;
    callNative("mediaPreview", request.payload)
      .then((data) => {
        const album = activeAlbum();
        const isCurrent = request.generation === state.previewGeneration
          && album?.id === request.payload.album_id
          && state.previewActivePaths.has(request.payload.path);
        if (!isCurrent) return;
        const item = itemForPath(data.path);
        if (item && data.preview_available && data.data_url) {
          mediaRender.applyPreview(data.path, data.data_url, state.selectedPath);
        } else if (item) {
          mediaRender.showPreviewUnavailable(item, state.selectedPath);
        }
      })
      .catch((error) => {
        if (request.generation !== state.previewGeneration) return;
        const item = itemForPath(request.payload.path);
        if (item && state.previewActivePaths.has(item.path)) {
          mediaRender.showPreviewUnavailable(item, state.selectedPath);
          console.error("Media preview generation failed", error);
        }
      })
      .finally(() => {
        state.previewActive -= 1;
        drainPreviewQueue();
      });
  }
}

// Queues one preview at most once per album path during the current rendered page.
function queuePreview(path) {
  const album = activeAlbum();
  if (!album) return;
  const key = `${album.id}:${path}`;
  if (state.previewKeys.has(key)) return;
  state.previewKeys.add(key);
  state.previewQueue.push({
    generation: state.previewGeneration,
    payload: { album_id: album.id, path },
  });
  drainPreviewQueue();
}

// Returns whether a tile occupies the current scrollport, with a small prefetch margin.
function tileIsActive(tile, gridBounds) {
  const bounds = tile.getBoundingClientRect();
  const margin = 80;
  return bounds.bottom >= gridBounds.top - margin
    && bounds.top <= gridBounds.bottom + margin
    && bounds.right >= gridBounds.left
    && bounds.left <= gridBounds.right;
}

// Reconciles transient preview sources against the actual visible tiles and selected inspector item.
function syncActivePreviews() {
  state.previewFrame = 0;
  const panel = byId("panel-media");
  const grid = byId("media-grid");
  if (!panel.classList.contains("active") || !activeAlbum()) return;
  const gridBounds = grid.getBoundingClientRect();
  const tiles = Array.from(grid.querySelectorAll(".media-tile[data-media-preview-capable]"));
  const activePaths = new Set();
  tiles.forEach((tile) => {
    if (tileIsActive(tile, gridBounds)) activePaths.add(tile.dataset.mediaPath);
  });
  const selected = selectedItem();
  if (selected?.preview_available) activePaths.add(selected.path);
  state.previewActivePaths.forEach((path) => {
    if (activePaths.has(path)) return;
    const item = itemForPath(path);
    if (item) mediaRender.releasePreview(item);
    const album = activeAlbum();
    if (album) state.previewKeys.delete(`${album.id}:${path}`);
  });
  state.previewQueue = state.previewQueue.filter((request) => activePaths.has(request.payload.path));
  state.previewActivePaths = activePaths;
  activePaths.forEach(queuePreview);
}

// Coalesces render, scroll, and resize changes into one deterministic active-viewport scan.
function scheduleActivePreviews() {
  if (state.previewFrame) return;
  state.previewFrame = window.requestAnimationFrame(syncActivePreviews);
}

// Registers a selected album folder through the native picker.
async function addAlbum() {
  const data = await runAction("chooseMediaAlbum", queryPayload(1), "");
  if (!data.cancelled) {
    state.selectedPath = "";
    applyState(data);
    appendActivity("Media album added");
  }
}

// Selects one saved album and resets the contact sheet to its first page.
async function selectAlbum(albumId) {
  const data = await runAction("selectMediaAlbum", { ...queryPayload(1), album_id: albumId }, "");
  state.selectedPath = "";
  applyState(data);
}

// Selects one tile locally and requests its preview if supported.
function selectItem(path) {
  state.selectedPath = path;
  document.querySelectorAll(".media-tile").forEach((tile) => {
    const selected = tile.dataset.mediaPath === path;
    tile.classList.toggle("selected", selected);
    tile.querySelector(".media-tile-select").setAttribute("aria-pressed", String(selected));
  });
  const item = selectedItem();
  mediaRender.renderInspector(item);
  if (item && item.preview_available && !mediaRender.showExistingPreview(item.path)) {
    state.previewActivePaths.add(item.path);
    queuePreview(item.path);
  }
  scheduleActivePreviews();
}

// Saves a display-label change without renaming the physical album folder.
async function renameAlbum(event) {
  event.preventDefault();
  const album = activeAlbum();
  if (!album) return;
  const data = await runAction("renameMediaAlbum", {
    ...queryPayload(),
    album_id: album.id,
    name: byId("media-album-name").value,
    category: byId("media-album-category").value,
  }, "Media album details saved");
  applyState(data);
}

// Forgets a private album reference after plainly confirming original files remain untouched.
async function removeAlbum() {
  const album = activeAlbum();
  if (!album) return;
  const confirmed = window.confirm(
    `Forget “${album.name}” in GitDesk? The folder and every original file will remain untouched.`,
  );
  if (!confirmed) return;
  const data = await runAction("removeMediaAlbum", {
    ...queryPayload(1),
    album_id: album.id,
  }, "Media album forgotten");
  state.selectedPath = "";
  applyState(data);
}

// Opens the selected album folder with the operating system file manager.
async function openAlbumFolder() {
  const album = activeAlbum();
  if (album) await runAction("openMediaAlbum", { album_id: album.id }, "Media album opened");
}

// Opens one item through the user's platform-default image or video application.
async function openItem(path = state.selectedPath) {
  const album = activeAlbum();
  if (!album || !path) return;
  await runAction("openMediaItem", {
    album_id: album.id,
    path,
  }, "Media item opened");
}

// Publishes a first release or records the linked album's changed contents as its next version.
async function publishAlbum() {
  const album = activeAlbum();
  if (!album) return;
  const data = await runAction("publishMediaAlbum", {
    ...queryPayload(),
    album_id: album.id,
    resource_name: byId("media-resource-name").value,
  }, album.resource_name ? "Media Shared Resource updated" : "Media Shared Resource published");
  applyState(data);
  if (data.published_release && window.GitDeskAISkills) {
    window.GitDeskAISkills.refresh().catch((error) => {
      console.warn("Shared Resources settings refresh failed", error);
    });
  }
}

// Applies filters as a fresh first page.
function submitFilters(event) {
  event.preventDefault();
  state.selectedPath = "";
  refresh(1).catch(() => {});
}

// Routes delegated tile selection without attaching handlers to rebuilt rows.
function handleWorkspaceClick(event) {
  const openButton = event.target.closest("[data-media-open-path]");
  if (openButton) {
    openItem(openButton.dataset.mediaOpenPath).catch(() => {});
    return;
  }
  const selectButton = event.target.closest("[data-media-select-path]");
  if (selectButton) selectItem(selectButton.dataset.mediaSelectPath);
}

// Binds stable Media controls after the dynamic panel has been inserted.
function bindEvents() {
  byId("add-media-album").addEventListener("click", () => addAlbum().catch(() => {}));
  byId("refresh-media-library").addEventListener("click", () => refresh().catch(() => {}));
  byId("media-filter-form").addEventListener("submit", submitFilters);
  byId("media-grid").addEventListener("scroll", scheduleActivePreviews, { passive: true });
  window.addEventListener("resize", scheduleActivePreviews, { passive: true });
  byId("media-page-previous").addEventListener("click", () => refresh(state.media.page - 1).catch(() => {}));
  byId("media-page-next").addEventListener("click", () => refresh(state.media.page + 1).catch(() => {}));
  byId("panel-media").addEventListener("click", handleWorkspaceClick);
  byId("media-album-metadata-form").addEventListener("submit", (event) => {
    renameAlbum(event).catch(() => {});
  });
  byId("remove-media-album").addEventListener("click", () => removeAlbum().catch(() => {}));
  byId("open-media-album").addEventListener("click", () => openAlbumFolder().catch(() => {}));
  byId("open-media-item").addEventListener("click", () => openItem().catch(() => {}));
  byId("publish-media-album").addEventListener("click", () => publishAlbum().catch(() => {}));
}

// Initializes Media markup while deferring all album scans until Media Mode is activated.
function init() {
  mediaRender.injectUI();
  mediaAlbumNavigation.bind({
    onAlbumSelect: selectAlbum,
    onPausePreviews: deactivate,
    onResumePreviews: scheduleActivePreviews,
  });
  mediaIntake.bind({
    activeAlbum,
    applyState,
    currentMedia: () => state.media,
    queryPayload,
    refresh,
    runAction,
  });
  mediaClipboard.bind({
    activeAlbum,
    applyState,
    queryPayload,
    renderIntake: () => mediaIntake.render(state.media),
    runAction,
  });
  mediaItemMove.bind({
    activeAlbum,
    applyState,
    queryPayload,
    runAction,
  });
  bindEvents();
}

window.GitDeskMediaMode = { activate, deactivate, refresh };

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
})();
