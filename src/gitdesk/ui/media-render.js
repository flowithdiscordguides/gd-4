/*
  Media Mode markup and rendering for albums, contact sheets, and the selected-item inspector.
*/

// Keeps the visual Media workspace independent from native bridge orchestration.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk Media Mode render dependencies did not load.");
}

const { byId, setText } = renderHelpers;

// Escapes album and filesystem metadata before it enters generated markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Inserts the Media toolbar destination beside the Local Mode destination.
function injectToolbarButton() {
  if (document.querySelector('.tab-button[data-tab="media"]')) return;
  const button = document.createElement("button");
  button.className = "tab-button";
  button.type = "button";
  button.dataset.tab = "media";
  button.title = "Media Mode";
  button.setAttribute("aria-label", "Media Mode");
  button.innerHTML = `
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <rect x="3" y="5" width="18" height="14" rx="2"></rect>
      <circle cx="9" cy="10" r="1.5"></circle>
      <path d="m5 17 4-4 3 3 2-2 5 3"></path>
    </svg>
  `;
  const localButton = document.querySelector('.tab-button[data-tab="local"]');
  localButton.insertAdjacentElement("afterend", button);
}

// Inserts the three-pane album, contact-sheet, and inspector workspace.
function injectPanel() {
  if (document.getElementById("panel-media")) return;
  const panel = document.createElement("section");
  panel.id = "panel-media";
  panel.className = "panel";
  panel.setAttribute("aria-labelledby", "media-title");
  panel.innerHTML = `
    <header class="panel-header media-header">
      <div>
        <span class="media-kicker">Visual library</span>
        <h2 id="media-title">Media albums</h2>
        <p id="media-summary">Add a folder to build a non-destructive image and video library.</p>
      </div>
      <div class="button-row media-header-actions">
        <div class="media-album-picker">
          <button id="media-album-picker-trigger" class="media-album-picker-trigger" type="button"
            aria-haspopup="menu" aria-expanded="false" aria-controls="media-album-picker-menu" disabled>
            <span id="media-album-picker-label">No media albums</span>
            <span class="media-album-picker-caret" aria-hidden="true"></span>
          </button>
          <button id="open-media-album-library" class="icon-button media-album-library-trigger" type="button"
            aria-label="Open all albums" title="Open all albums" aria-controls="panel-media-album-library">
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="M9 4H4v5M15 4h5v5M20 15v5h-5M9 20H4v-5"></path>
            </svg>
          </button>
        </div>
        <button id="create-media-album" type="button">New album</button>
        <button id="add-media-album" type="button">Add existing</button>
        <button id="refresh-media-library" type="button">Refresh</button>
      </div>
    </header>
    <div class="media-layout">
      <section class="media-contact-pane" aria-label="Album contact sheet">
        <form id="media-filter-form" class="media-filter-bar" role="search">
          <input id="media-search" type="search" maxlength="120" placeholder="Search this album">
          <select id="media-kind" aria-label="Media type">
            <option value="all">All media</option>
            <option value="image">Images</option>
            <option value="video">Videos</option>
          </select>
          <select id="media-sort" aria-label="Sort media">
            <option value="name">Name</option>
            <option value="newest">Newest</option>
            <option value="size">Largest</option>
          </select>
          <button type="submit">Apply</button>
        </form>
        <div class="media-contact-heading">
          <div>
            <strong id="media-contact-title">No album selected</strong>
            <span id="media-counts">0 items</span>
          </div>
          <div class="media-pagination" aria-label="Media pages">
            <button id="media-page-previous" type="button">Previous</button>
            <span id="media-page-label">Page 0 of 0</span>
            <button id="media-page-next" type="button">Next</button>
          </div>
        </div>
        <div id="media-grid" class="media-grid" aria-live="polite"></div>
      </section>
      <aside class="media-inspector" aria-label="Selected media">
        <div id="media-inspector-empty" class="media-inspector-empty">
          <span>Lightbox</span>
          <h3>Select an item</h3>
          <p>Choose a tile to inspect metadata or open the original in its native app.</p>
        </div>
        <div id="media-inspector-content" hidden>
          <div id="media-inspector-preview" class="media-inspector-preview"></div>
          <span id="media-inspector-kind" class="status-pill"></span>
          <h3 id="media-inspector-name"></h3>
          <code id="media-inspector-path"></code>
          <dl class="media-inspector-meta">
            <div><dt>Size</dt><dd id="media-inspector-size"></dd></div>
            <div><dt>Modified</dt><dd id="media-inspector-modified"></dd></div>
          </dl>
          <button id="open-media-item" type="button">Open original</button>
        </div>
        <section id="media-album-actions" class="media-album-actions" hidden>
          <div>
            <span>Album folder</span>
            <code id="media-album-path"></code>
          </div>
          <form id="media-album-metadata-form" class="media-album-metadata-form">
            <label for="media-album-name">Album name</label>
            <input id="media-album-name" type="text" maxlength="80">
            <label for="media-album-category">Category</label>
            <input id="media-album-category" type="text" maxlength="64" list="media-album-category-options"
              placeholder="Uncategorized">
            <button id="rename-media-album" type="submit">Save album details</button>
          </form>
          <button id="open-media-album" type="button">Open folder</button>
          <div class="media-publish-block">
            <span>Shared Resource</span>
            <p id="media-resource-status">Publish this album for reuse in other projects.</p>
            <div class="media-inline-action">
              <input id="media-resource-name" type="text" maxlength="64" placeholder="Resource name">
              <button id="publish-media-album" type="button">Publish</button>
            </div>
          </div>
          <button id="remove-media-album" class="danger-button" type="button">Forget album</button>
          <small>Forgetting removes only this GitDesk reference. Original files stay untouched.</small>
        </section>
      </aside>
    </div>
  `;
  byId("panel-local").insertAdjacentElement("afterend", panel);
}

// Inserts all Media Mode surfaces before controller event binding begins.
function injectUI() {
  injectToolbarButton();
  injectPanel();
}

// Returns the semantic placeholder shown only while an active thumbnail is being generated.
function mediaPlaceholder(item) {
  const glyph = item.kind === "video" ? "▶" : "◇";
  return `<span class="media-placeholder-glyph" aria-hidden="true">${glyph}</span>
    <small>${escapeHtml(item.extension || item.kind)}</small>`;
}

// Renders one bounded page with separate preview selection and direct native-open controls.
function renderGrid(mediaState, selectedPath) {
  const items = mediaState.items || [];
  byId("media-grid").innerHTML = items.length ? items.map((item) => {
    const selected = item.path === selectedPath ? " selected" : "";
    const preview = item.preview_available
      ? " data-media-preview-capable=\"true\" data-media-preview-pending=\"true\""
      : "";
    return `
      <article class="media-tile${selected}" data-media-path="${escapeHtml(item.path)}"
        data-media-kind="${escapeHtml(item.kind)}" data-media-extension="${escapeHtml(item.extension)}"${preview}>
        <button class="media-tile-select" type="button" data-media-select-path="${escapeHtml(item.path)}"
          aria-label="Preview ${escapeHtml(item.name)}" aria-pressed="${item.path === selectedPath}">
          <span class="media-tile-preview">${mediaPlaceholder(item)}</span>
        </button>
        <button class="media-tile-open" type="button" data-media-open-path="${escapeHtml(item.path)}">
          Open
        </button>
        <span class="media-tile-copy">
          <strong>${escapeHtml(item.name)}</strong>
          <small>${escapeHtml(item.size_label)} · ${escapeHtml(item.kind)}</small>
        </span>
      </article>
    `;
  }).join("") : `
    <div class="media-empty media-grid-empty">
      <strong>${mediaState.active_album ? "No matching media" : "Choose or add an album"}</strong>
      <span>${mediaState.active_album
        ? "Adjust the search or media type filter."
        : "Only the selected album is scanned, keeping large libraries responsive."}</span>
    </div>
  `;
}

// Renders selected-album details and locks resource naming after first publication.
function renderAlbumActions(album) {
  const container = byId("media-album-actions");
  container.hidden = !album;
  if (!album) return;
  setText("media-album-path", album.path);
  byId("media-album-name").value = album.name;
  byId("media-album-category").value = album.category || "";
  byId("media-resource-name").value = album.resource_name || album.name;
  byId("media-resource-name").disabled = Boolean(album.resource_name);
  setText(
    "media-resource-status",
    album.resource_name
      ? `Linked to ${album.resource_name}. Publish again to record changed album contents.`
      : "Publish this album for reuse in other projects.",
  );
  byId("publish-media-album").textContent = album.resource_name ? "Publish update" : "Publish";
  ["open-media-album", "publish-media-album"].forEach((id) => {
    byId(id).disabled = !album.exists;
  });
}

// Renders contact-sheet counts, controls, album actions, and item tiles from one backend response.
function renderState(mediaState, selectedPath) {
  const album = mediaState.active_album;
  renderAlbumActions(album);
  renderGrid(mediaState, selectedPath);
  setText("media-contact-title", album ? album.name : "No album selected");
  setText(
    "media-counts",
    `${mediaState.filtered_count || 0} shown · ${mediaState.image_count || 0} images · `
      + `${mediaState.video_count || 0} videos`,
  );
  setText("media-summary", album
    ? `${album.name} · ${mediaState.total_count || 0} indexed items`
    : "Add a folder to build a non-destructive image and video library.");
  setText("media-page-label", `Page ${mediaState.page_count ? mediaState.page : 0} of ${mediaState.page_count}`);
  byId("media-page-previous").disabled = mediaState.page <= 1;
  byId("media-page-next").disabled = !mediaState.page_count || mediaState.page >= mediaState.page_count;
  byId("media-search").value = mediaState.query || "";
  byId("media-kind").value = mediaState.kind || "all";
  byId("media-sort").value = mediaState.sort || "name";
}

// Renders the selected item and reserves preview space without loading video bytes.
function renderInspector(item) {
  byId("media-inspector-empty").hidden = Boolean(item);
  byId("media-inspector-content").hidden = !item;
  if (!item) return;
  setText("media-inspector-kind", item.kind);
  setText("media-inspector-name", item.name);
  setText("media-inspector-path", item.path);
  setText("media-inspector-size", `${item.size_label} (${item.size} bytes)`);
  setText("media-inspector-modified", item.modified_label);
  byId("media-inspector-preview").innerHTML = mediaPlaceholder(item);
}

// Returns the rendered tile for a path without using path text in a selector.
function tileForPath(path) {
  return Array.from(document.querySelectorAll(".media-tile"))
    .find((tile) => tile.dataset.mediaPath === path) || null;
}

// Replaces a preview container with one inert image node so data URLs never enter generated markup.
function setPreviewImage(container, dataUrl) {
  if (!container || !dataUrl) return;
  const image = document.createElement("img");
  image.alt = "";
  image.draggable = false;
  image.src = dataUrl;
  container.replaceChildren(image);
}

// Applies a verified data URL to matching active surfaces without retaining it in application state.
function applyPreview(path, dataUrl, selectedPath) {
  if (!dataUrl) return;
  const tile = tileForPath(path);
  if (tile) {
    setPreviewImage(tile.querySelector(".media-tile-preview"), dataUrl);
    delete tile.dataset.mediaPreviewPending;
    tile.classList.remove("preview-unavailable");
  }
  if (selectedPath === path) {
    setPreviewImage(byId("media-inspector-preview"), dataUrl);
  }
}

// Copies an already active tile preview into the selected inspector without storing another preview value.
function showExistingPreview(path) {
  const image = tileForPath(path)?.querySelector(".media-tile-preview img");
  if (image?.src) setPreviewImage(byId("media-inspector-preview"), image.src);
  return Boolean(image?.src);
}

// Removes an inactive preview's source immediately so WebKit can release its decoded pixels.
function releasePreview(item) {
  const tile = tileForPath(item.path);
  if (!tile) return;
  const container = tile.querySelector(".media-tile-preview");
  const image = container.querySelector("img");
  if (!image) return;
  image.removeAttribute("src");
  container.innerHTML = mediaPlaceholder(item);
  tile.dataset.mediaPreviewPending = "true";
}

// Marks a requested item clearly when no safe frame could be generated.
function showPreviewUnavailable(item, selectedPath) {
  const tile = tileForPath(item.path);
  if (tile) {
    const container = tile.querySelector(".media-tile-preview");
    container.innerHTML = `${mediaPlaceholder(item)}<span class="media-preview-note">Preview unavailable</span>`;
    delete tile.dataset.mediaPreviewPending;
    tile.classList.add("preview-unavailable");
  }
  if (selectedPath === item.path) {
    byId("media-inspector-preview").innerHTML =
      `${mediaPlaceholder(item)}<span class="media-preview-note">Preview unavailable</span>`;
  }
}

window.GitDeskMediaRender = {
  applyPreview,
  injectUI,
  releasePreview,
  renderInspector,
  renderState,
  showExistingPreview,
  showPreviewUnavailable,
};
})();
