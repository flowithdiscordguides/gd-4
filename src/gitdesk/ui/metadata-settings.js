/*
  System Settings viewer for GitDesk's allowlisted non-secret metadata JSON files.
*/

// Keeps diagnostics read-only in the WebView while Python owns the fixed file allowlist.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;

if (!nativeBridge || !renderHelpers) {
  throw new Error("GitDesk metadata settings dependencies did not load.");
}

const { callNative } = nativeBridge;
const { appendActivity, byId, escapeHtml, setBusy, showMessage } = renderHelpers;

// Adds one System Settings card and a bounded JSON viewer modal.
function injectUI() {
  if (document.getElementById("metadata-settings-card")) return;
  const mount = document.getElementById("settings-system-content");
  if (!mount) return;
  mount.insertAdjacentHTML("afterbegin", `
    <section id="metadata-settings-card" class="settings-block metadata-settings-card">
      <div>
        <strong>Project metadata files</strong>
        <p>Open GitDesk's private metadata folder or inspect a non-secret JSON file here.</p>
      </div>
      <div class="button-row">
        <button id="refresh-metadata-files" type="button">Refresh files</button>
        <button id="open-metadata-folder" type="button">Open metadata folder</button>
      </div>
      <div id="metadata-file-list" class="metadata-file-list" aria-live="polite"></div>
    </section>
  `);
  document.body.insertAdjacentHTML("beforeend", `
    <div id="metadata-viewer-dialog" class="metadata-viewer-dialog" hidden>
      <section class="metadata-viewer-panel" role="dialog" aria-modal="true"
        aria-labelledby="metadata-viewer-title">
        <header>
          <div>
            <h2 id="metadata-viewer-title">Metadata JSON</h2>
            <code id="metadata-viewer-path"></code>
          </div>
          <button id="close-metadata-viewer" type="button">Close</button>
        </header>
        <pre id="metadata-viewer-content" tabindex="0"></pre>
      </section>
    </div>
  `);
}

// Renders file rows with View disabled until the corresponding artifact exists.
function renderFiles(data) {
  const files = data && Array.isArray(data.files) ? data.files : [];
  byId("metadata-file-list").innerHTML = files.map((file) => `
    <div class="metadata-file-row">
      <span><strong>${escapeHtml(file.name)}</strong><code>${escapeHtml(file.path)}</code></span>
      <button type="button" data-view-metadata="${escapeHtml(file.name)}"
        ${file.exists ? "" : "disabled"}>${file.exists ? "View" : "Not created"}</button>
    </div>
  `).join("");
}

// Refreshes existence state without opening or parsing every metadata file.
async function refreshFiles() {
  const data = await callNative("metadataFiles", {});
  renderFiles(data);
}

// Opens one backend-formatted JSON document as text rather than executable markup.
async function viewFile(name) {
  setBusy(true);
  try {
    const data = await callNative("viewMetadataFile", { name });
    byId("metadata-viewer-title").textContent = data.name;
    byId("metadata-viewer-path").textContent = data.path;
    byId("metadata-viewer-content").textContent = data.content;
    byId("metadata-viewer-dialog").hidden = false;
    byId("close-metadata-viewer").focus();
  } catch (error) {
    const message = error.message || "Metadata could not be displayed.";
    showMessage(message, true);
    appendActivity(message, true);
  } finally {
    setBusy(false);
  }
}

// Closes the read-only viewer without changing any metadata file.
function closeViewer() {
  byId("metadata-viewer-dialog").hidden = true;
}

// Opens the fixed GitDesk metadata directory through the operating-system file manager.
async function openFolder() {
  try {
    await callNative("openMetadataFolder", {});
    appendActivity("Metadata folder opened");
  } catch (error) {
    const message = error.message || "Metadata folder could not be opened.";
    showMessage(message, true);
    appendActivity(message, true);
  }
}

// Binds the dynamic card after Settings tabs have injected their System mount.
function init() {
  injectUI();
  if (!document.getElementById("metadata-settings-card")) return;
  byId("refresh-metadata-files").addEventListener("click", () => refreshFiles().catch(() => {}));
  byId("open-metadata-folder").addEventListener("click", () => openFolder().catch(() => {}));
  byId("metadata-file-list").addEventListener("click", (event) => {
    const button = event.target.closest("[data-view-metadata]");
    if (button) viewFile(button.dataset.viewMetadata || "").catch(() => {});
  });
  byId("close-metadata-viewer").addEventListener("click", closeViewer);
  byId("metadata-viewer-dialog").addEventListener("click", (event) => {
    if (event.target.id === "metadata-viewer-dialog") closeViewer();
  });
  refreshFiles().catch(() => {});
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
})();
