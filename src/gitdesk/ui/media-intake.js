/*
  Media album creation, parent favorites, and album-scoped image intake.
*/

// Keeps high-volume file handling separate from contact-sheet rendering and controller orchestration.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk Media intake dependencies did not load.");
}

const { appendActivity, byId, showMessage } = renderHelpers;
const MAX_IMPORT_BYTES = 32 * 1024 * 1024;
const DEFAULT_INTAKE_STATUS = "PNG, JPEG, GIF, WebP, BMP, ICO, or safe SVG · 32 MB each";
const IMAGE_MIME_TYPES = {
  bmp: "image/bmp",
  gif: "image/gif",
  ico: "image/x-icon",
  jpeg: "image/jpeg",
  jpg: "image/jpeg",
  png: "image/png",
  svg: "image/svg+xml",
  webp: "image/webp",
};
const intakeState = {
  callbacks: null,
  albumId: "",
  favorites: [],
  importing: false,
  opener: null,
};

// Inserts the new-album action, open-album intake tray, and one reusable creation dialog.
function injectUI() {
  if (document.getElementById("media-intake-tray")) return;

  byId("media-filter-form").insertAdjacentHTML("afterend", `
    <section id="media-intake-tray" class="media-intake-tray" tabindex="0" hidden
      aria-label="Drop images here or paste images from the clipboard" aria-keyshortcuts="Meta+V Control+V">
      <div class="media-intake-copy">
        <span class="media-intake-kicker">Drop zone</span>
        <strong id="media-intake-title">Drop images here or paste from clipboard</strong>
        <small id="media-intake-status">PNG, JPEG, GIF, WebP, BMP, ICO, or safe SVG · 32 MB each</small>
      </div>
      <button id="choose-media-images" type="button">Choose images</button>
      <input id="media-image-files" class="media-intake-file-input" type="file" multiple
        accept=".png,.jpg,.jpeg,.gif,.webp,.bmp,.ico,.svg,image/png,image/jpeg,image/gif,image/webp,image/bmp">
    </section>
  `);

  document.body.insertAdjacentHTML("beforeend", `
    <div id="media-album-modal" class="media-album-modal" role="dialog" aria-modal="true" hidden>
      <form id="media-album-create-form" class="media-album-dialog" aria-labelledby="media-album-dialog-title"
        aria-describedby="media-album-dialog-description">
        <header>
          <div>
            <span>New collection</span>
            <h2 id="media-album-dialog-title">Create media album</h2>
          </div>
          <button id="close-media-album-modal" class="media-album-modal-close" type="button"
            aria-label="Close new album dialog">×</button>
        </header>
        <p id="media-album-dialog-description">
          Create one physical folder, register it in Media Mode, and open it for image intake.
        </p>
        <label for="media-new-album-name">Album name</label>
        <input id="media-new-album-name" type="text" maxlength="80" autocomplete="off"
          placeholder="Campaign selects" required>
        <label for="media-new-album-category">Category</label>
        <input id="media-new-album-category" type="text" maxlength="64" autocomplete="off"
          list="media-album-category-options" placeholder="Uncategorized">
        <datalist id="media-album-category-options"></datalist>
        <label for="media-new-album-parent">Parent folder</label>
        <div class="media-parent-row">
          <input id="media-new-album-parent" type="text" spellcheck="false"
            placeholder="/absolute/path/to/parent" required>
          <button id="choose-media-parent" class="media-parent-icon" type="button"
            aria-label="Choose album parent folder" title="Choose album parent folder">
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v1H3z"></path>
              <path d="M3 9h18l-2 9a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z"></path>
            </svg>
          </button>
          <button id="favorite-media-parent" class="media-parent-icon" type="button"
            aria-label="Save parent as favorite" title="Save parent as favorite" aria-pressed="false">
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1L12 16.9l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"></path>
            </svg>
          </button>
        </div>
        <label for="media-parent-favorites">Favorite parents</label>
        <select id="media-parent-favorites">
          <option value="">No saved Media parents</option>
        </select>
        <footer>
          <button id="cancel-media-album" type="button">Cancel</button>
          <button id="confirm-media-album" type="submit">Create album</button>
        </footer>
      </form>
    </div>
  `);
}

// Rebuilds the favorite selector with textContent so saved filesystem paths never become markup.
function renderFavorites() {
  const select = byId("media-parent-favorites");
  select.replaceChildren();
  const placeholder = document.createElement("option");
  placeholder.value = "";
  placeholder.textContent = intakeState.favorites.length ? "Choose a favorite parent" : "No saved Media parents";
  select.appendChild(placeholder);
  intakeState.favorites.forEach((path) => {
    const option = document.createElement("option");
    option.value = path;
    option.textContent = path;
    select.appendChild(option);
  });
}

// Shows whether the typed parent is already in the saved Media favorite list.
function renderFavoriteState() {
  const path = byId("media-new-album-parent").value.trim();
  const saved = intakeState.favorites.some(
    (favorite) => favorite.toLocaleLowerCase() === path.toLocaleLowerCase(),
  );
  byId("favorite-media-parent").classList.toggle("saved", saved);
  byId("favorite-media-parent").setAttribute("aria-pressed", String(saved));
}

// Synchronizes the creation dialog and makes intake available only for a connected active album.
function render(mediaState) {
  const media = mediaState || {};
  intakeState.favorites = Array.isArray(media.parent_favorites) ? media.parent_favorites : [];
  const categories = Array.from(new Set(
    (media.albums || []).map((album) => String(album.category || "").trim()).filter(Boolean),
  )).sort((left, right) => left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" }));
  const categoryOptions = byId("media-album-category-options");
  categoryOptions.replaceChildren(...categories.map((category) => {
    const option = document.createElement("option");
    option.value = category;
    return option;
  }));
  renderFavorites();
  renderFavoriteState();
  const album = media.active_album;
  const available = Boolean(album && album.exists);
  const albumId = album ? album.id : "";
  if (albumId !== intakeState.albumId) {
    byId("media-intake-status").textContent = DEFAULT_INTAKE_STATUS;
    intakeState.albumId = albumId;
  }
  byId("media-intake-tray").hidden = !available;
  byId("choose-media-images").disabled = !available || intakeState.importing;
  if (available && !intakeState.importing) {
    byId("media-intake-title").textContent = `Drop images into ${album.name} or paste from clipboard`;
  }
}

// Opens the modal with the newest favorite preselected while preserving explicit user edits after it opens.
function openCreateDialog(event) {
  intakeState.opener = event.currentTarget;
  const parent = byId("media-new-album-parent");
  byId("media-new-album-name").value = "";
  byId("media-new-album-category").value = "";
  parent.value = intakeState.favorites[0] || "";
  byId("media-parent-favorites").value = parent.value;
  renderFavoriteState();
  byId("media-album-modal").hidden = false;
  byId("media-new-album-name").focus();
}

// Closes the modal and returns keyboard focus to the control that opened it.
function closeCreateDialog() {
  byId("media-album-modal").hidden = true;
  if (intakeState.opener) intakeState.opener.focus();
}

// Keeps keyboard navigation inside the active modal and closes it through the standard Escape action.
function handleModalKeydown(event) {
  const modal = byId("media-album-modal");
  if (modal.hidden) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closeCreateDialog();
    return;
  }
  if (event.key !== "Tab") return;
  const controls = Array.from(modal.querySelectorAll("button:not(:disabled), input:not(:disabled), select"));
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

// Uses the platform picker to select a parent without creating anything.
async function chooseParent() {
  const data = await intakeState.callbacks.runAction("chooseMediaParent", {
    initial_path: byId("media-new-album-parent").value,
  }, "");
  if (!data.cancelled) {
    byId("media-new-album-parent").value = data.path;
    byId("media-parent-favorites").value = intakeState.favorites.includes(data.path) ? data.path : "";
    renderFavoriteState();
  }
}

// Saves a Media-specific parent favorite and keeps central state synchronized with the response.
async function saveParentFavorite() {
  const path = byId("media-new-album-parent").value;
  const data = await intakeState.callbacks.runAction(
    "saveMediaParentFavorite",
    { ...intakeState.callbacks.queryPayload(), path },
    "Media album parent saved as a favorite",
  );
  intakeState.callbacks.applyState(data);
  byId("media-parent-favorites").value = data.parent_favorites[0] || "";
  renderFavoriteState();
}

// Creates and selects the physical album through the backend's direct-child validation boundary.
async function createAlbum(event) {
  event.preventDefault();
  const submit = byId("confirm-media-album");
  submit.disabled = true;
  try {
    const data = await intakeState.callbacks.runAction("createMediaAlbum", {
      ...intakeState.callbacks.queryPayload(1),
      name: byId("media-new-album-name").value,
      category: byId("media-new-album-category").value,
      parent_path: byId("media-new-album-parent").value,
    }, "Media album created");
    intakeState.callbacks.applyState(data);
    closeCreateDialog();
  } finally {
    submit.disabled = false;
  }
}

// Reads one browser File as a data URL and repairs only a missing MIME declaration from its verified extension.
function readImage(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
    reader.onload = () => {
      const extension = file.name.split(".").pop().toLowerCase();
      const dataUrl = String(reader.result || "");
      if (dataUrl.startsWith("data:;base64,")) {
        resolve(dataUrl.replace("data:;base64,", `data:${IMAGE_MIME_TYPES[extension]};base64,`));
      } else {
        resolve(dataUrl);
      }
    };
    reader.readAsDataURL(file);
  });
}

// Rejects unsupported and oversized browser files before allocating their base64 bridge payloads.
function validateFile(file) {
  const extension = String(file.name || "").split(".").pop().toLowerCase();
  if (!IMAGE_MIME_TYPES[extension]) {
    throw new Error(`${file.name} is not a supported import image.`);
  }
  if (!file.size || file.size > MAX_IMPORT_BYTES) {
    throw new Error(`${file.name} must be between 1 byte and 32 MB.`);
  }
}

// Imports files sequentially so large batches never hold multiple encoded images in memory at once.
async function importFiles(fileValues) {
  const album = intakeState.callbacks.activeAlbum();
  const files = Array.from(fileValues || []).filter((file) => file && file.name);
  if (
    !album
    || !album.exists
    || !files.length
    || intakeState.importing
    || byId("media-intake-tray").classList.contains("importing")
  ) return;
  intakeState.importing = true;
  let imported = 0;
  let failed = 0;
  byId("choose-media-images").disabled = true;
  byId("media-intake-tray").classList.add("importing");
  for (const file of files) {
    byId("media-intake-title").textContent = `Importing ${imported + failed + 1} of ${files.length}`;
    try {
      validateFile(file);
      const dataUrl = await readImage(file);
      await intakeState.callbacks.runAction("importMediaImage", {
        album_id: album.id,
        name: file.name,
        data_url: dataUrl,
      }, "");
      imported += 1;
    } catch (error) {
      failed += 1;
      console.error("Media image import failed", error);
    }
  }
  intakeState.importing = false;
  byId("media-intake-tray").classList.remove("importing", "drag-active");
  if (imported) {
    try {
      await intakeState.callbacks.refresh(1);
    } catch (error) {
      console.error("Media library refresh after import failed", error);
    }
  }
  byId("media-intake-status").textContent =
    `${imported} imported${failed ? ` · ${failed} failed` : ""} · no existing files replaced`;
  const summary = `${imported} image${imported === 1 ? "" : "s"} imported into ${album.name}`;
  appendActivity(summary, failed > 0);
  if (failed) showMessage(`${failed} image${failed === 1 ? "" : "s"} could not be imported.`, true);
  render(intakeState.callbacks.currentMedia());
}

// Binds stable controls once after both the Media panel and intake markup exist.
function bind(callbacks) {
  intakeState.callbacks = callbacks;
  injectUI();
  byId("create-media-album").addEventListener("click", openCreateDialog);
  byId("close-media-album-modal").addEventListener("click", closeCreateDialog);
  byId("cancel-media-album").addEventListener("click", closeCreateDialog);
  byId("choose-media-parent").addEventListener("click", () => chooseParent().catch(() => {}));
  byId("favorite-media-parent").addEventListener("click", () => saveParentFavorite().catch(() => {}));
  byId("media-album-create-form").addEventListener("submit", (event) => createAlbum(event).catch(() => {}));
  byId("media-parent-favorites").addEventListener("change", (event) => {
    if (event.target.value) byId("media-new-album-parent").value = event.target.value;
    renderFavoriteState();
  });
  byId("media-new-album-parent").addEventListener("input", renderFavoriteState);
  byId("choose-media-images").addEventListener("click", () => byId("media-image-files").click());
  byId("media-image-files").addEventListener("change", (event) => {
    importFiles(event.target.files).catch(() => {});
    event.target.value = "";
  });
  const tray = byId("media-intake-tray");
  tray.addEventListener("dragenter", (event) => {
    event.preventDefault();
    tray.classList.add("drag-active");
  });
  tray.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
  });
  tray.addEventListener("dragleave", (event) => {
    if (!tray.contains(event.relatedTarget)) tray.classList.remove("drag-active");
  });
  tray.addEventListener("drop", (event) => {
    event.preventDefault();
    tray.classList.remove("drag-active");
    importFiles(event.dataTransfer.files).catch(() => {});
  });
  byId("media-album-modal").addEventListener("click", (event) => {
    if (event.target === byId("media-album-modal")) closeCreateDialog();
  });
  document.addEventListener("keydown", handleModalKeydown);
}

window.GitDeskMediaIntake = { bind, render };
})();
