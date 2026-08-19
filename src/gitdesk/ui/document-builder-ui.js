/*
  Dynamic toolbar and workspace markup for GitDesk Document Builder.
*/

// Publishes page injection before the controller binds events and app.js binds generic tab navigation.
(() => {
const editorSettings = window.GitDeskEditorSettings;
if (!editorSettings) throw new Error("GitDesk editor settings dependency did not load.");

// Inserts an independent toolbar button that remains available in Repo and Local workspace modes.
function injectToolbarButton() {
  if (document.querySelector('.tab-button[data-tab="document-builder"]')) return;
  const button = document.createElement("button");
  button.className = "tab-button";
  button.type = "button";
  button.dataset.tab = "document-builder";
  button.title = "Document Builder";
  button.setAttribute("aria-label", "Document Builder");
  button.innerHTML = `
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M6 3h9l4 4v14H6z"></path>
      <path d="M15 3v5h4M9 12h7M9 16h7"></path>
    </svg>
  `;
  const settingsButton = document.querySelector('.tab-button[data-tab="settings"]');
  settingsButton.parentNode.insertBefore(button, settingsButton);
}

// Inserts the three-level hierarchy as a Local Projects-aligned two-pane master-detail workspace.
function injectPanel() {
  if (document.getElementById("panel-document-builder")) return;
  document.getElementById("panel-settings").insertAdjacentHTML("beforebegin", `
    <section id="panel-document-builder" class="panel document-builder-panel"
      aria-labelledby="document-builder-title">
      <div class="panel-header document-builder-panel-header">
        <div class="document-builder-panel-heading">
          <h2 id="document-builder-title">Document Builder</h2>
          <p id="document-builder-summary">No document selected</p>
        </div>
        <div class="button-row document-builder-panel-actions">
          <button id="open-new-document-modal" type="button">New Document</button>
          <button id="refresh-documents" type="button">Refresh</button>
        </div>
      </div>
      <div class="document-builder-layout">
        <div class="document-builder-left-pane">
          <section class="settings-block document-builder-card document-identity-card">
            <div class="document-picker">
              <label for="document-picker-trigger">Document</label>
              <button id="document-picker-trigger" class="document-picker-trigger" type="button"
                role="combobox" aria-haspopup="listbox" aria-expanded="false"
                aria-controls="document-picker-menu" disabled>
                <span id="document-picker-label" class="document-picker-trigger-label">No documents</span>
                <span class="document-picker-caret" aria-hidden="true"></span>
              </button>
            </div>
            <datalist id="document-category-options"></datalist>
            <div class="document-identity-body">
              <div class="document-identity-artwork">
                <div class="document-icon-frame" aria-hidden="true">
                  <svg viewBox="0 0 24 24">
                    <path d="M6 3h9l4 4v14H6z"></path>
                    <path d="M15 3v5h4M9 12h7M9 16h7"></path>
                  </svg>
                </div>
                <div class="button-row document-root-open-actions">
                  <button id="open-document-folder" type="button" disabled>Open folder</button>
                  <button id="open-document-vscode" type="button" disabled
                    data-editor-label-template="{editor}"
                    data-editor-aria-template="Open document in {editor}"
                    data-editor-tooltip-template="Open document in {editor}">${editorSettings.name()}</button>
                </div>
                <p>Document root</p>
              </div>
              <div class="document-selected-controls">
                <div class="document-selected-heading">
                  <span>Current document</span>
                  <div class="document-title-row">
                    <h3 id="document-active-name">No document selected</h3>
                    <input id="document-rename-name" type="text" spellcheck="true"
                      aria-label="New document folder name" placeholder="Document folder name" hidden disabled>
                    <button id="rename-document" class="icon-button document-rename-button" type="button"
                      aria-label="Rename document" title="Rename document" aria-pressed="false" disabled></button>
                  </div>
                </div>
                <label class="document-category-field" for="document-active-category">
                  <span>Category</span>
                  <input id="document-active-category" type="text" spellcheck="true"
                    list="document-category-options" placeholder="Uncategorized" disabled>
                </label>
                <button id="remove-document" class="document-danger" type="button" disabled>
                  Remove from GitDesk
                </button>
              </div>
            </div>
          </section>
          <section class="settings-block document-builder-card document-folder-card">
            <div class="document-builder-card-header">
              <label for="document-folder-name">Folders</label>
              <span id="document-folder-count" class="document-builder-muted">0 folders</span>
            </div>
            <form id="create-document-folder-form" class="document-folder-form">
              <select id="document-folder-parent" aria-label="Parent folder" disabled>
                <option value="">Document root</option>
              </select>
              <div class="document-folder-command">
                <input id="document-folder-name" type="text" spellcheck="true"
                  placeholder="Add new folder" disabled>
                <button id="create-document-folder" type="submit" disabled>Create folder</button>
              </div>
            </form>
            <div id="document-folder-list" class="document-folder-list" role="list"
              aria-label="Document folders" aria-live="polite"></div>
          </section>
        </div>
        <section class="settings-block document-builder-card document-file-card">
          <div class="document-builder-card-header">
            <label for="document-file-name">Files</label>
            <button id="new-document-file" type="button" disabled>New file</button>
          </div>
          <div class="document-file-workspace">
            <div id="document-file-list" class="document-file-list" aria-live="polite"></div>
            <aside class="document-file-detail" aria-live="polite">
              <div id="document-file-empty" class="document-file-detail-empty">
                <span>File workspace</span>
                <h3>Select a folder</h3>
                <p>Choose or create a folder to add its first numbered file.</p>
              </div>
              <form id="create-document-file-form" class="document-file-form" hidden>
                <div class="document-file-detail-heading">
                  <span>New file</span>
                </div>
                <h3>Create a numbered file</h3>
                <label for="document-file-name">File name</label>
                <input id="document-file-name" type="text" spellcheck="true" placeholder="notes.md">
                <label for="document-file-content">Paste text</label>
                <textarea id="document-file-content" rows="12" spellcheck="true"
                  placeholder="Paste the file contents here"></textarea>
                <button id="save-document-file" type="submit">Save file</button>
              </form>
              <div id="document-file-saved" class="document-file-saved" hidden>
                <div class="document-file-detail-heading">
                  <span>Selected file</span>
                </div>
                <h3 id="document-file-saved-name"></h3>
                <p data-editor-label-template="The file is saved. Continue editing it in {editor}.">
                  The file is saved. Continue editing it in ${editorSettings.name()}.</p>
                <div class="button-row document-shared-resource-actions">
                  <button id="open-document-file-vscode" type="button"
                    data-editor-label-template="Open in {editor}"
                    data-editor-aria-template="Open selected file in {editor}"
                    data-editor-tooltip-template="Open selected file in {editor}">
                    Open in ${editorSettings.name()}</button>
                  <button id="add-document-shared-resource" type="button">Add to Shared Resources</button>
                  <button id="update-document-shared-resource" type="button" hidden>
                    Update Shared Resource
                  </button>
                </div>
                <p id="document-shared-resource-link" class="row-meta" hidden></p>
              </div>
            </aside>
          </div>
        </section>
      </div>
    </section>
  `);
}

// Inserts the document-creation modal so creation controls do not occupy the hierarchy column.
function injectCreateModal() {
  if (document.getElementById("new-document-modal")) return;
  document.body.insertAdjacentHTML("beforeend", `
    <section id="new-document-modal" class="new-document-modal" hidden>
      <div class="new-document-dialog" role="dialog" aria-modal="true"
        aria-labelledby="new-document-title">
        <div class="panel-header">
          <div>
            <h2 id="new-document-title">New Document</h2>
            <p>Create a physical document workspace.</p>
          </div>
          <div class="button-row">
            <button id="create-document" type="submit" form="create-document-form">Create document</button>
            <button id="close-new-document-modal" type="button">Close</button>
          </div>
        </div>
        <form id="create-document-form" class="document-create-form">
          <label for="document-parent-path">Parent folder</label>
          <div class="input-action-row">
            <input id="document-parent-path" type="text" spellcheck="false"
              placeholder="/absolute/path/to/documents">
            <button id="choose-document-parent" class="icon-button" type="button"
              aria-label="Choose document parent folder" title="Choose parent folder">
              <svg aria-hidden="true" viewBox="0 0 24 24">
                <path d="M3 6a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v1H3z"></path>
                <path d="M3 9h18l-2 9a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z"></path>
              </svg>
            </button>
          </div>
          <label for="document-name">Document name</label>
          <input id="document-name" type="text" spellcheck="true" placeholder="Product Research">
          <label for="document-create-category">Category</label>
          <input id="document-create-category" type="text" spellcheck="true"
            list="document-category-options" placeholder="Research">
        </form>
      </div>
    </section>
  `);
}

// Creates all Document Builder surfaces before dependent scripts query their controls.
function injectUI() {
  injectToolbarButton();
  injectPanel();
  injectCreateModal();
  editorSettings.refreshLabels();
}

window.GitDeskDocumentBuilderUI = { injectUI };
})();
