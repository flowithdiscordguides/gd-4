/*
  Safe hierarchy rendering and control-state updates for Document Builder.
*/

// Keeps filesystem-derived rendering separate from action coordination.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk Document Builder render dependencies did not load.");
}

const { byId, setText } = renderHelpers;

// Escapes backend paths and names before inserting them into dynamic markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Returns the active document record nested in the current state payload.
function activeDocument(state) {
  return (state.documents || []).find((item) => item.path === state.active_document) || null;
}

// Returns the active folder record nested under the selected document.
function activeFolder(state) {
  const documentRecord = activeDocument(state);
  return flattenFolders(documentRecord && documentRecord.folders || []).find(
    (item) => item.path === state.active_folder,
  ) || null;
}

// Flattens recursive folders so selections and parent choices can address any nesting level.
function flattenFolders(folders) {
  const flattened = [];
  (folders || []).forEach((folder) => {
    flattened.push(folder);
    flattened.push(...flattenFolders(folder.folders || []));
  });
  return flattened;
}

// Reveals a selected hierarchy row inside its own list without moving the surrounding page workspace.
function revealActiveRow(list, selector) {
  const activeRow = list.querySelector(selector);
  if (!activeRow) {
    return;
  }
  requestAnimationFrame(() => {
    if (!activeRow.isConnected) {
      return;
    }
    const listBounds = list.getBoundingClientRect();
    const rowBounds = activeRow.getBoundingClientRect();
    // Move only this list's scroll position when the selected row crosses its visible bounds.
    if (rowBounds.top < listBounds.top) {
      list.scrollTop -= listBounds.top - rowBounds.top;
    } else if (rowBounds.bottom > listBounds.bottom) {
      list.scrollTop += rowBounds.bottom - listBounds.bottom;
    }
  });
}

// Returns the active file record nested under the selected folder.
function activeFile(state) {
  const folder = activeFolder(state);
  return (folder && folder.files || []).find((item) => item.path === state.active_file) || null;
}

// Summarizes one folder's direct child folders and files without implying recursive totals.
function folderMetadata(folder) {
  const folderCount = (folder.folders || []).length;
  const fileCount = (folder.files || []).length;
  const parts = [];
  if (folderCount) {
    parts.push(`${folderCount} folder${folderCount === 1 ? "" : "s"}`);
  }
  parts.push(`${fileCount} file${fileCount === 1 ? "" : "s"}`);
  return parts.join(" · ");
}

// Renders physical folders as nested list groups while retaining canonical path selection on each row.
function folderRows(folders, state) {
  return (folders || []).map((folder) => {
    const active = folder.path === state.active_folder ? " active" : "";
    const current = active ? ' aria-current="true"' : "";
    const children = folder.folders || [];
    const branchClass = children.length ? " has-children" : "";
    const childGroup = children.length ? `
      <div class="document-folder-children" role="list">
        ${folderRows(children, state)}
      </div>` : "";
    return `
      <div class="document-folder-branch${branchClass}" role="listitem">
        <button class="document-folder-row${active}" type="button"
          data-document-folder-path="${escapeHtml(folder.path)}"${current}>
          <img class="document-folder-icon" src="./folder-icon.svg" alt="" draggable="false">
          <strong>${escapeHtml(folder.name)}</strong>
          <small>${folderMetadata(folder)}</small>
        </button>
        ${childGroup}
      </div>
    `;
  }).join("");
}

// Renders nested physical folders for the active document with numeric prefixes intact.
function renderFolders(state) {
  const documentRecord = activeDocument(state);
  const folders = documentRecord && documentRecord.folders || [];
  const allFolders = flattenFolders(folders);
  setText("document-folder-count", `${allFolders.length} folder${allFolders.length === 1 ? "" : "s"}`);
  if (!documentRecord) {
    byId("document-folder-list").innerHTML = '<div class="empty-state">No document selected</div>';
    return;
  }
  if (!folders.length) {
    byId("document-folder-list").innerHTML = '<div class="empty-state">No folders yet</div>';
    return;
  }
  const list = byId("document-folder-list");
  list.innerHTML = folderRows(folders, state);
  revealActiveRow(list, ".document-folder-row.active");
}

// Populates the folder-parent selector with the document root and every current nested folder.
function renderFolderParents(state) {
  const documentRecord = activeDocument(state);
  const folders = flattenFolders(documentRecord && documentRecord.folders || []);
  const currentValue = byId("document-folder-parent").value;
  const rootValue = documentRecord ? documentRecord.path : "";
  const options = [`<option value="${escapeHtml(rootValue)}">Document root</option>`];
  folders.forEach((folder) => {
    // Non-breaking spaces preserve hierarchy in native option menus without terminal-style tree characters.
    const indent = "&nbsp;&nbsp;".repeat((folder.depth || 0) + 1);
    options.push(`<option value="${escapeHtml(folder.path)}">${indent}${escapeHtml(folder.name)}</option>`);
  });
  byId("document-folder-parent").innerHTML = options.join("");
  const available = Array.from(byId("document-folder-parent").options).some(
    (option) => option.value === currentValue,
  );
  byId("document-folder-parent").value = available ? currentValue : rootValue;
}

// Renders regular direct-child files discovered under the active physical folder.
function renderFiles(state) {
  const folder = activeFolder(state);
  const files = folder && folder.files || [];
  if (!folder) {
    byId("document-file-list").innerHTML = "";
    return;
  }
  if (!files.length) {
    byId("document-file-list").innerHTML = '<div class="empty-state">No files yet</div>';
    return;
  }
  const list = byId("document-file-list");
  list.innerHTML = files.map((file) => {
    const active = file.path === state.active_file ? " active" : "";
    return `
      <button class="document-file-row${active}" type="button"
        data-document-file-path="${escapeHtml(file.path)}">
        <strong>${escapeHtml(file.name)}</strong>
      </button>
    `;
  }).join("");
  revealActiveRow(list, ".document-file-row.active");
}

// Updates the right-pane empty state so it always names the next hierarchy selection the user needs.
function renderFileEmptyState(documentRecord, folder) {
  const emptyState = byId("document-file-empty");
  const heading = emptyState.querySelector("h3");
  const description = emptyState.querySelector("p");
  // The first unmet hierarchy prerequisite determines the instruction shown in the file detail pane.
  if (!documentRecord) {
    heading.textContent = "Select a document";
    description.textContent = "Choose a saved document before working with folders and files.";
  } else if (!documentRecord.exists) {
    heading.textContent = "Document unavailable";
    description.textContent = "This saved document root is missing from the filesystem.";
  } else if (!folder) {
    heading.textContent = "Select a folder";
    description.textContent = "Choose or create a folder to add its first numbered file.";
  }
}

// Enables only actions whose required physical hierarchy selection currently exists.
function renderControls(state, creatingFile) {
  const documentRecord = activeDocument(state);
  const folder = activeFolder(state);
  const file = activeFile(state);
  const hasDocumentRecord = Boolean(documentRecord);
  const hasDocument = Boolean(documentRecord && documentRecord.exists);
  const hasFolder = Boolean(folder);
  renderFileEmptyState(documentRecord, folder);
  ["open-document-folder", "open-document-vscode"].forEach((id) => {
    byId(id).disabled = !hasDocument;
  });
  // Missing roots remain removable from private metadata even though filesystem actions cannot target them.
  byId("remove-document").disabled = !hasDocumentRecord;
  byId("document-folder-name").disabled = !hasDocument;
  byId("document-folder-parent").disabled = !hasDocument;
  byId("create-document-folder").disabled = !hasDocument;
  byId("new-document-file").disabled = !hasFolder;
  byId("document-file-empty").hidden = hasFolder;

  // A saved/selected file replaces the paste editor until the user explicitly starts another file.
  const showEditor = hasFolder && (!file || creatingFile);
  byId("create-document-file-form").hidden = !showEditor;
  byId("document-file-saved").hidden = !file || creatingFile;
  if (file && !creatingFile) {
    setText("document-file-saved-name", file.name);
  }
}

// Updates the page summary with the deepest active hierarchy location.
function renderSummary(state) {
  const documentRecord = activeDocument(state);
  const folder = activeFolder(state);
  const file = activeFile(state);
  if (!documentRecord) {
    setText("document-builder-summary", "No document selected");
    return;
  }
  const parts = [documentRecord.name];
  if (folder) parts.push(folder.name);
  if (file) parts.push(file.name);
  setText("document-builder-summary", parts.join(" / "));
}

// Renders all hierarchy surfaces after a backend response or local editor-mode change.
function render(state, creatingFile) {
  renderFolders(state);
  renderFolderParents(state);
  renderFiles(state);
  renderControls(state, creatingFile);
  renderSummary(state);
}

window.GitDeskDocumentBuilderRender = {
  activeDocument,
  activeFile,
  activeFolder,
  escapeHtml,
  render,
};
})();
