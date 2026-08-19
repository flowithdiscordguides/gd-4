/*
  Stateful controller for Document Builder native actions and paste-to-file workflow.
*/

// Coordinates the isolated page while UI, rendering, and organization remain focused modules.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const documentUI = window.GitDeskDocumentBuilderUI;
const documentRender = window.GitDeskDocumentBuilderRender;
const documentOrganizer = window.GitDeskDocumentBuilderOrganizer;
const sharedResourceManager = window.GitDeskSharedResources;
const editorSettings = window.GitDeskEditorSettings;

if (!nativeBridge || !renderHelpers || !documentUI || !documentRender || !documentOrganizer
    || !sharedResourceManager || !editorSettings) {
  throw new Error("GitDesk Document Builder dependencies did not load.");
}

const { callNative } = nativeBridge;
const { appendActivity, byId, setBusy, setValue, showMessage } = renderHelpers;
const state = {
  documents: [],
  categories: [],
  active_document: "",
  active_folder: "",
  active_file: "",
};
let creatingFile = false;

// Installs the shared pencil artwork while retaining an accessible text label for assistive technology.
function installIcons() {
  const renameButton = byId("rename-document");
  renameButton.innerHTML = (window.GitDeskIcons || {}).rename || "Rename";
}

// Opens the creation modal and moves keyboard focus to its first field.
function openCreateModal() {
  byId("new-document-modal").hidden = false;
  byId("document-parent-path").focus();
}

// Closes the creation modal without clearing partially entered values.
function closeCreateModal() {
  byId("new-document-modal").hidden = true;
}

// Runs one backend action with consistent busy, error, and DevTools activity feedback.
async function runAction(action, payload, successMessage) {
  setBusy(true);
  showMessage("");
  try {
    const data = await callNative(action, payload || {});
    if (successMessage) appendActivity(successMessage);
    return data;
  } catch (error) {
    const message = error.message || "Document Builder operation failed.";
    console.error(`Native action failed: ${action}`, error);
    showMessage(message, true);
    appendActivity(message, true);
    throw error;
  } finally {
    setBusy(false);
  }
}

// Applies backend state and redraws both the hierarchy and category-organized document list.
function applyResponse(data) {
  const nextState = data && data.documents ? data.documents : data;
  Object.assign(state, nextState || {});
  documentOrganizer.render(state);
  documentRender.render(state, creatingFile);
  sharedResourceManager.renderDocumentSelection();
}

// Returns the active document path used by all root-level actions.
function activeDocumentPath() {
  return state.active_document || "";
}

// Returns the active folder path used by file creation and selection.
function activeFolderPath() {
  return state.active_folder || "";
}

// Returns the active file path used by direct external-editor opening.
function activeFilePath() {
  return state.active_file || "";
}

// Refreshes physical folders and files so external file-manager/editor changes become visible.
async function refreshState() {
  const data = await runAction("documentBuilderState", {}, "");
  applyResponse(data);
}

// Opens a native parent-folder picker without creating or registering anything yet.
async function chooseParent() {
  const data = await runAction("chooseDocumentParent", {
    initial_path: byId("document-parent-path").value,
  }, "Document parent selected");
  if (data.path) setValue("document-parent-path", data.path);
}

// Creates an empty document root and clears only the successful form fields.
async function createDocument(event) {
  event.preventDefault();
  const data = await runAction("createDocument", {
    parent_path: byId("document-parent-path").value,
    name: byId("document-name").value,
    category: byId("document-create-category").value,
  }, "Document created");
  byId("document-name").value = "";
  byId("document-create-category").value = "";
  creatingFile = false;
  applyResponse(data);
  closeCreateModal();
}

// Renames an explicitly identified document root while the backend remaps active child selections.
async function renameDocument(path, name) {
  const data = await runAction("renameDocument", {
    document_path: path,
    name,
  }, "Document renamed");
  applyResponse(data);
}

// Removes only the selected registry entry, intentionally leaving all physical content untouched.
async function removeDocument() {
  const data = await runAction("removeDocument", {
    document_path: activeDocumentPath(),
  }, "Document removed from GitDesk");
  creatingFile = false;
  applyResponse(data);
}

// Saves the category label edited in the selected-document identity card.
async function setCategory(path, category) {
  const data = await runAction("setDocumentCategory", {
    document_path: path,
    category,
  }, "Document category saved");
  applyResponse(data);
}

// Selects a registered document and its first available folder/file descendants.
async function selectDocument(path) {
  const data = await runAction("selectDocument", { document_path: path }, "Document selected");
  creatingFile = false;
  applyResponse(data);
}

// Creates the next numbered folder under the selected document root.
async function createFolder(event) {
  event.preventDefault();
  const data = await runAction("createDocumentFolder", {
    document_path: activeDocumentPath(),
    parent_folder_path: byId("document-folder-parent").value,
    name: byId("document-folder-name").value,
  }, "Document folder created");
  byId("document-folder-name").value = "";
  creatingFile = true;
  applyResponse(data);
}

// Selects a physical direct-child folder and its first available file.
async function selectFolder(path) {
  const data = await runAction("selectDocumentFolder", {
    document_path: activeDocumentPath(),
    folder_path: path,
  }, "Document folder selected");
  creatingFile = false;
  applyResponse(data);
}

// Switches from a saved file action to a clean paste editor for the next numbered file.
function beginNewFile() {
  if (!activeFolderPath()) return;
  creatingFile = true;
  byId("document-file-name").value = "";
  byId("document-file-content").value = "";
  documentRender.render(state, creatingFile);
  sharedResourceManager.renderDocumentSelection();
  byId("document-file-name").focus();
}

// Writes pasted text as the next numbered file and replaces the editor with its external-editor action.
async function createFile(event) {
  event.preventDefault();
  const data = await runAction("createDocumentFile", {
    document_path: activeDocumentPath(),
    folder_path: activeFolderPath(),
    name: byId("document-file-name").value,
    content: byId("document-file-content").value,
  }, "Document file saved");
  byId("document-file-name").value = "";
  byId("document-file-content").value = "";
  creatingFile = false;
  applyResponse(data);
}

// Selects an existing file so the paste editor is replaced with its direct editor-launch action.
async function selectFile(path) {
  const data = await runAction("selectDocumentFile", {
    document_path: activeDocumentPath(),
    folder_path: activeFolderPath(),
    file_path: path,
  }, "Document file selected");
  creatingFile = false;
  applyResponse(data);
}

// Opens the selected document root in Finder or the platform's equivalent file manager.
async function openDocumentFolder() {
  await runAction("openDocumentFolder", {
    document_path: activeDocumentPath(),
  }, "Document opened in file manager");
}

// Opens the selected document root in the preferred code editor.
async function openDocumentVSCode() {
  const message = `Document opened in ${editorSettings.name()}`;
  await runAction("openDocumentInVSCode", {
    document_path: activeDocumentPath(),
  }, message);
}

// Opens the exact active numbered file in the preferred editor after backend ownership validation.
async function openFileVSCode() {
  const message = `Document file opened in ${editorSettings.name()}`;
  await runAction("openDocumentFileInVSCode", {
    document_path: activeDocumentPath(),
    folder_path: activeFolderPath(),
    file_path: activeFilePath(),
  }, message);
}

// Delegates dynamic folder and file row clicks after each render rebuilds their markup.
function handleHierarchyClick(event) {
  const folderButton = event.target.closest("[data-document-folder-path]");
  if (folderButton) {
    selectFolder(folderButton.dataset.documentFolderPath || "").catch(() => {});
    return;
  }
  const fileButton = event.target.closest("[data-document-file-path]");
  if (fileButton) selectFile(fileButton.dataset.documentFilePath || "").catch(() => {});
}

// Closes the modal for backdrop clicks while keeping clicks inside its dialog interactive.
function handleModalClick(event) {
  if (event.target === byId("new-document-modal")) closeCreateModal();
}

// Gives keyboard users the conventional Escape route out of the creation modal.
function handleKeydown(event) {
  if (event.key === "Escape" && !byId("new-document-modal").hidden) closeCreateModal();
}

// Binds static controls after page injection; async failures are already reported by runAction.
function bindEvents() {
  byId("open-new-document-modal").addEventListener("click", openCreateModal);
  byId("close-new-document-modal").addEventListener("click", closeCreateModal);
  byId("new-document-modal").addEventListener("click", handleModalClick);
  document.addEventListener("keydown", handleKeydown);
  byId("refresh-documents").addEventListener("click", () => refreshState().catch(() => {}));
  byId("choose-document-parent").addEventListener("click", () => chooseParent().catch(() => {}));
  byId("create-document-form").addEventListener("submit", (event) => createDocument(event).catch(() => {}));
  byId("remove-document").addEventListener("click", () => removeDocument().catch(() => {}));
  byId("create-document-folder-form").addEventListener("submit", (event) => createFolder(event).catch(() => {}));
  byId("create-document-file-form").addEventListener("submit", (event) => createFile(event).catch(() => {}));
  byId("new-document-file").addEventListener("click", beginNewFile);
  byId("open-document-folder").addEventListener("click", () => openDocumentFolder().catch(() => {}));
  byId("open-document-vscode").addEventListener("click", () => openDocumentVSCode().catch(() => {}));
  byId("open-document-file-vscode").addEventListener("click", () => openFileVSCode().catch(() => {}));
  byId("panel-document-builder").addEventListener("click", handleHierarchyClick);
  documentOrganizer.bind({
    onSelect: selectDocument,
    onCategoryChange: setCategory,
    onRename: renameDocument,
  });
  sharedResourceManager.bindDocument({
    runAction,
    getSelection() {
      return {
        document_path: activeDocumentPath(),
        folder_path: activeFolderPath(),
        file_path: activeFilePath(),
      };
    },
  });
}

// Injects the page, binds its controls, and loads registry state without affecting workspace mode.
function init() {
  documentUI.injectUI();
  installIcons();
  bindEvents();
  documentOrganizer.render(state);
  documentRender.render(state, creatingFile);
  refreshState().catch(() => {});
}

// Ensures body-dependent page injection runs after static markup is available.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
})();
