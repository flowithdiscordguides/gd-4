/*
  Shared Resources management for Local Mode versions and Document Builder publishing.
*/

// Keeps revision-management dialogs independent from the Local Mode and Document Builder controllers.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk Shared Resources dependencies did not load.");
}

const { byId, showMessage } = renderHelpers;
let localConfig = null;
let documentConfig = null;
let localState = { version_path: "", resources: [] };
let localTrigger = null;
let documentState = { resources: [], link: null };
let documentRequestToken = 0;

// Escapes filesystem-derived resource names and paths before they enter dynamic dialog markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Inserts the version-management modal once Local Mode has created its selected-version inspector.
function injectLocalModal() {
  if (document.getElementById("local-shared-resources-dialog")) return;
  document.body.insertAdjacentHTML("beforeend", `
    <section id="local-shared-resources-dialog" class="shared-resources-dialog" hidden>
      <div class="shared-resources-panel" role="dialog" aria-modal="true"
        aria-labelledby="local-shared-resources-title">
        <div class="panel-header shared-resources-header">
          <div>
            <h2 id="local-shared-resources-title">Manage Shared Resources</h2>
            <p id="local-shared-resources-summary">Choose reusable files for this version.</p>
          </div>
          <div class="button-row">
            <button id="apply-local-shared-resources" type="button">Apply changes</button>
            <button id="close-local-shared-resources" type="button">Close</button>
          </div>
        </div>
        <p class="shared-resources-merge-note">
          Numbered resources merge like Finder: matching resource paths update, while every other project file stays
          untouched. Legacy means no numbered version was detected; merge a vN release to enable version tracking.
        </p>
        <div id="local-shared-resources-list" class="shared-resources-list" aria-live="polite"></div>
      </div>
    </section>
  `);
}

// Maps backend status values to concise labels that do not rely on color alone.
function statusLabel(resource) {
  if (resource.status === "missing") return "Missing files";
  if (resource.status === "legacy") return "Legacy";
  if (resource.status === "outdated") return "Update available";
  if (resource.status === "current") return "Current";
  if (resource.status === "unavailable") return "Source unavailable";
  return "Available";
}

// Renders compact resource rows with explicit install selection and row-local update actions.
function renderLocalState(data) {
  localState = data || localState;
  const resources = localState.resources || [];
  const list = byId("local-shared-resources-list");
  const versionName = String(localState.version_path || "active version").replace(/\\/g, "/").split("/").pop();
  byId("local-shared-resources-summary").textContent = resources.length
    ? `${resources.length} resource${resources.length === 1 ? "" : "s"} listed for ${versionName}.`
    : "No Shared Resources are available yet.";
  if (!resources.length) {
    list.innerHTML = '<div class="empty-state">Create a Shared Resource in Settings first.</div>';
    updateApplyState();
    return;
  }
  list.innerHTML = resources.map((resource) => {
    const checked = resource.installed ? "checked" : "";
    const disabled = resource.recorded || resource.installed ? "" : "disabled";
    const latestLabel = resource.recorded ? `latest ${resource.version_label}` : resource.version_label;
    const updateLabel = resource.merge_available ? `Merge ${resource.version_label}` : "Update";
    const updateButton = resource.update_available ? `
      <button class="update-local-shared-resource" type="button"
        data-resource-name="${escapeHtml(resource.name)}">${escapeHtml(updateLabel)}</button>` : "";
    const trackingMessage = resource.tracking_message ? `
      <small class="shared-resource-tracking-note">${escapeHtml(resource.tracking_message)}</small>` : "";
    return `
      <div class="shared-resource-row" data-resource-status="${escapeHtml(resource.status)}">
        <label class="shared-resource-choice">
          <input class="local-shared-resource-check" type="checkbox"
            value="${escapeHtml(resource.name)}" data-was-installed="${resource.installed}"
            ${checked} ${disabled}>
          <span>
            <strong>${escapeHtml(resource.name)}</strong>
            <small>${escapeHtml(resource.file_count)} files ·
              ${resource.installed ? `installed ${escapeHtml(resource.installed_version_label)} · ` : ""}
              ${escapeHtml(latestLabel)}</small>
            ${trackingMessage}
          </span>
        </label>
        <div class="shared-resource-row-actions">
          <span class="status-pill">${escapeHtml(statusLabel(resource))}</span>
          ${updateButton}
        </div>
      </div>
    `;
  }).join("");
  updateApplyState();
}

// Marks the apply command as destructive whenever the current selection will remove installed resource paths.
function updateApplyState() {
  const removals = Array.from(document.querySelectorAll(".local-shared-resource-check"))
    .filter((checkbox) => checkbox.dataset.wasInstalled === "true" && !checkbox.checked)
    .length;
  const button = byId("apply-local-shared-resources");
  button.disabled = !document.querySelector(".local-shared-resource-check:not(:disabled)");
  button.classList.toggle("shared-resources-destructive", removals > 0);
  button.textContent = removals ? `Apply changes · ${removals} removal${removals === 1 ? "" : "s"}` : "Apply changes";
}

// Opens management for the selected Local version and compares installs only with explicitly recorded releases.
async function openLocalModal(versionPath, trigger) {
  localTrigger = trigger || null;
  const data = await localConfig.runAction("localSharedResourceState", { version_path: versionPath }, "");
  byId("local-shared-resources-dialog").hidden = false;
  renderLocalState(data);
  byId("close-local-shared-resources").focus();
}

// Closes Local Mode management without applying any unchecked or newly checked rows.
function closeLocalModal() {
  byId("local-shared-resources-dialog").hidden = true;
  const refreshedTrigger = byId("manage-local-shared-resources");
  const focusTarget = localTrigger && localTrigger.isConnected ? localTrigger : refreshedTrigger;
  if (focusTarget) focusTarget.focus();
}

// Returns the names currently selected in the version-management checklist.
function selectedLocalResources() {
  return Array.from(document.querySelectorAll(".local-shared-resource-check"))
    .filter((checkbox) => checkbox.checked && !checkbox.disabled)
    .map((checkbox) => checkbox.value);
}

// Applies explicit add/remove selection while leaving outdated checked rows unchanged until Update is chosen.
async function applyLocalSelection() {
  const data = await localConfig.runAction("applyLocalSharedResources", {
    version_path: localState.version_path,
    resources: selectedLocalResources(),
  }, "Shared Resources updated for version");
  renderLocalState(data);
  if (window.GitDeskWorkspaceMode) {
    window.GitDeskWorkspaceMode.refreshLocalState().catch(() => {});
  }
}

// Merges one resource's latest recorded snapshot and redraws every resulting install status.
async function updateLocalResource(name) {
  const resource = (localState.resources || []).find((item) => item.name === name);
  const successMessage = resource && resource.merge_available
    ? `${name} numbered Shared Resource merged` : `${name} Shared Resource updated`;
  const data = await localConfig.runAction("updateLocalSharedResource", {
    version_path: localState.version_path,
    name,
  }, successMessage);
  renderLocalState(data);
  if (window.GitDeskWorkspaceMode) {
    window.GitDeskWorkspaceMode.refreshLocalState().catch(() => {});
  }
}

// Handles Local Mode modal buttons through one stable listener despite resource rows being rebuilt.
function handleLocalClick(event) {
  if (event.target.id === "close-local-shared-resources"
      || event.target.id === "local-shared-resources-dialog") {
    closeLocalModal();
    return;
  }
  if (event.target.id === "apply-local-shared-resources") {
    applyLocalSelection().catch(() => {});
    return;
  }
  const updateButton = event.target.closest(".update-local-shared-resource");
  if (updateButton) {
    updateLocalResource(updateButton.dataset.resourceName || "").catch(() => {});
  }
}

// Binds management to the selected-version inspector and resolves its current path only when opened.
function bindLocal(config) {
  localConfig = config;
  injectLocalModal();
  const trigger = byId("manage-local-shared-resources");
  trigger.addEventListener("click", () => {
    const versionPath = localConfig.getVersionPath();
    if (!versionPath) return;
    openLocalModal(versionPath, trigger).catch(() => {});
  });
  byId("local-shared-resources-dialog").addEventListener("click", handleLocalClick);
  byId("local-shared-resources-list").addEventListener("change", updateApplyState);
}

// Inserts the Document Builder publishing modal with an editable resource-relative destination.
function injectDocumentModal() {
  if (document.getElementById("document-shared-resource-dialog")) return;
  document.body.insertAdjacentHTML("beforeend", `
    <section id="document-shared-resource-dialog" class="shared-resources-dialog" hidden>
      <div class="shared-resources-panel document-shared-resource-panel" role="dialog" aria-modal="true"
        aria-labelledby="document-shared-resource-title">
        <div class="panel-header shared-resources-header">
          <div>
            <h2 id="document-shared-resource-title">Add to Shared Resources</h2>
            <p>Choose a resource and the relative project path this file should use.</p>
          </div>
          <button id="close-document-shared-resource" type="button">Close</button>
        </div>
        <form id="document-shared-resource-form" class="document-shared-resource-form">
          <label for="document-shared-resource-name">Shared Resource</label>
          <select id="document-shared-resource-name"></select>
          <label for="document-shared-resource-path">Project-relative path</label>
          <input id="document-shared-resource-path" type="text" spellcheck="false"
            placeholder=".codex/skills/example.md">
          <p class="row-meta">The path is merged into projects that include this resource.</p>
          <button id="save-document-shared-resource" type="submit">Add to Shared Resources</button>
        </form>
      </div>
    </section>
  `);
}

// Returns the selected numbered file's basename without Document Builder's sequence prefix.
function defaultDocumentTarget(filePath) {
  const normalized = String(filePath || "").replace(/\\/g, "/");
  const basename = normalized.split("/").pop() || "resource.md";
  return basename.replace(/^0*[1-9][0-9]*\s+/, "") || basename;
}

// Applies resource-link state to the selected-file actions without hiding the option to publish elsewhere.
function renderDocumentLink(data) {
  documentState = data || documentState;
  const link = documentState.link || null;
  byId("update-document-shared-resource").hidden = !link;
  byId("document-shared-resource-link").hidden = !link;
  byId("document-shared-resource-link").textContent = link
    ? `Linked to ${link.resource} / ${link.target_path}`
      + (documentState.has_unrecorded_changes ? " · update to record this change" : "")
    : "";
}

// Refreshes the selected file's saved link and ignores responses that arrive after selection changes.
async function renderDocumentSelection() {
  if (!documentConfig) return;
  const selection = documentConfig.getSelection();
  const hasFile = Boolean(selection.file_path);
  byId("add-document-shared-resource").disabled = !hasFile;
  if (!hasFile) {
    renderDocumentLink({ resources: [], link: null });
    return;
  }
  const requestToken = ++documentRequestToken;
  const data = await documentConfig.runAction("documentSharedResourceState", selection, "");
  if (requestToken === documentRequestToken
      && documentConfig.getSelection().file_path === selection.file_path) {
    renderDocumentLink(data);
  }
}

// Opens the publish form with current resource choices and a useful unnumbered default destination filename.
async function openDocumentModal() {
  const selection = documentConfig.getSelection();
  if (!selection.file_path) return;
  const data = await documentConfig.runAction("documentSharedResourceState", selection, "");
  documentState = data;
  const select = byId("document-shared-resource-name");
  select.innerHTML = (data.resources || []).map((resource) => `
    <option value="${escapeHtml(resource.name)}">${escapeHtml(resource.name)}</option>
  `).join("");
  byId("document-shared-resource-path").value = defaultDocumentTarget(selection.file_path);
  byId("save-document-shared-resource").disabled = !(data.resources || []).length;
  byId("document-shared-resource-dialog").hidden = false;
  select.focus();
}

// Closes the Document Builder publishing form without modifying the selected file or resource catalog.
function closeDocumentModal() {
  byId("document-shared-resource-dialog").hidden = true;
  byId("add-document-shared-resource").focus();
}

// Publishes one selected file and immediately exposes its linked update action.
async function addDocumentResource(event) {
  event.preventDefault();
  const data = await documentConfig.runAction("addDocumentToSharedResource", {
    ...documentConfig.getSelection(),
    resource: byId("document-shared-resource-name").value,
    target_path: byId("document-shared-resource-path").value,
  }, "Document file added to Shared Resources");
  renderDocumentLink(data);
  closeDocumentModal();
}

// Republishes the linked file and records the resource's next numbered release when working bytes changed.
async function updateDocumentResource() {
  const data = await documentConfig.runAction(
    "updateDocumentSharedResource",
    documentConfig.getSelection(),
    "Shared Resource updated from Document Builder",
  );
  renderDocumentLink(data);
  if (window.GitDeskWorkspaceMode) {
    window.GitDeskWorkspaceMode.refreshLocalState().catch(() => {});
  }
  showMessage(`Updated ${data.link.resource} / ${data.link.target_path}`);
}

// Handles publishing-modal backdrop and close actions while keeping dialog content interactive.
function handleDocumentModalClick(event) {
  if (event.target.id === "close-document-shared-resource"
      || event.target.id === "document-shared-resource-dialog") {
    closeDocumentModal();
  }
}

// Binds selected-file publishing after Document Builder creates all required controls.
function bindDocument(config) {
  documentConfig = config;
  injectDocumentModal();
  byId("add-document-shared-resource").addEventListener("click", () => openDocumentModal().catch(() => {}));
  byId("update-document-shared-resource").addEventListener("click", () => {
    updateDocumentResource().catch(() => {});
  });
  byId("document-shared-resource-form").addEventListener("submit", (event) => {
    addDocumentResource(event).catch(() => {});
  });
  byId("document-shared-resource-dialog").addEventListener("click", handleDocumentModalClick);
  renderDocumentSelection().catch(() => {});
}

// Gives keyboard users a consistent Escape route out of either Shared Resources modal.
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const localDialog = document.getElementById("local-shared-resources-dialog");
  const documentDialog = document.getElementById("document-shared-resource-dialog");
  if (localDialog && !localDialog.hidden) closeLocalModal();
  if (documentDialog && !documentDialog.hidden) {
    closeDocumentModal();
  }
});

window.GitDeskSharedResources = { bindDocument, bindLocal, renderDocumentSelection };
})();
