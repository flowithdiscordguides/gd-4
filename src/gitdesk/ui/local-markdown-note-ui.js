/*
  Static modal markup for selected-version Markdown notes.
*/

// Keeps the large editor surface outside the notes workflow controller.
(() => {
// Injects one focus-contained editor outside the inert application shell.
function inject() {
  if (document.getElementById("local-notes-modal")) {
    return;
  }
  document.body.insertAdjacentHTML("beforeend", `
    <section id="local-notes-modal" class="local-notes-modal" hidden>
      <div id="local-notes-dialog" class="local-notes-dialog" role="dialog" aria-modal="true"
        aria-labelledby="local-notes-title" aria-describedby="local-notes-context">
        <header id="local-notes-header" class="local-notes-header">
          <div>
            <span>Selected-version workspace</span>
            <h2 id="local-notes-title">Project Markdown Notes</h2>
            <p id="local-notes-context">No version selected</p>
          </div>
          <div class="local-notes-header-actions">
            <div class="local-notes-mode" role="group" aria-label="Markdown view">
              <button type="button" data-note-mode="write">Write</button>
              <button type="button" data-note-mode="split">Split</button>
              <button type="button" data-note-mode="preview">Preview</button>
            </div>
            <button id="close-local-notes" type="button">Close</button>
          </div>
        </header>
        <div class="local-notes-body">
          <aside class="local-notes-sidebar" aria-label="Project notes">
            <form id="create-local-note-form" class="local-note-create-form">
              <label for="local-note-name">New Markdown note</label>
              <div>
                <input id="local-note-name" type="text" spellcheck="true" placeholder="Todo">
                <button id="create-local-note" type="submit">Create</button>
              </div>
            </form>
            <div id="local-note-list" class="local-note-list"></div>
          </aside>
          <section id="local-note-editor-shell" class="local-note-editor-shell" data-note-mode="split">
            <div class="local-note-document-bar">
              <strong id="local-note-active-name">Choose or create a note</strong>
              <span id="local-note-status" role="status" aria-live="polite">Ready</span>
            </div>
            <div class="local-note-document">
              <label class="local-note-write-pane" for="local-note-source">
                <span>Markdown source</span>
                <textarea id="local-note-source" spellcheck="true"
                  placeholder="# Todo&#10;&#10;- [ ] First task" disabled></textarea>
              </label>
              <article id="local-note-preview" class="local-note-preview" aria-label="Sanitized Markdown preview">
                <p class="local-note-empty">Markdown preview appears here.</p>
              </article>
            </div>
          </section>
        </div>
      </div>
    </section>
  `);
}

window.GitDeskLocalMarkdownNoteUI = { inject };
})();
