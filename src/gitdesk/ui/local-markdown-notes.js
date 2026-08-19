/*
  Obsidian-style Markdown notes for the exact selected Local Mode version.
*/

// Owns note catalog, editing, autosave, sanitized preview, and modal accessibility.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const markdownSanitizer = window.GitDeskMarkdownSanitizer;
const noteUI = window.GitDeskLocalMarkdownNoteUI;

if (!nativeBridge || !renderHelpers || !markdownSanitizer || !noteUI) {
  throw new Error("GitDesk project-note dependencies did not load.");
}

const { callNative } = nativeBridge;
const { appendActivity, byId } = renderHelpers;
const state = {
  context: {},
  notes: [],
  activeName: "",
  content: "",
  revision: "",
  dirty: false,
  busy: false,
  saving: false,
  savePromise: null,
  mode: "split",
  error: "",
  saveTimer: 0,
  returnFocus: null,
  bound: false,
};

// Escapes physical filenames before inserting them into the note catalog.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Returns the exact native ownership fields attached to every note request.
function requestContext() {
  return {
    project_path: state.context.project_path || "",
    feature_path: state.context.feature_path || "",
    version_path: state.context.version_path || "",
  };
}

// Renders only DOMPurify output into the preview HTML sink.
function renderPreview() {
  const sanitizedHtml = markdownSanitizer.render(state.content);
  byId("local-note-preview").innerHTML = sanitizedHtml;
}

// Renders the project-note catalog with the current file highlighted.
function renderNoteList() {
  const list = byId("local-note-list");
  if (!state.notes.length) {
    list.innerHTML = '<div class="empty-state">No Markdown notes in this version</div>';
    return;
  }
  list.innerHTML = state.notes.map((note) => {
    const active = note.name === state.activeName ? " active" : "";
    return `
      <button class="local-note-row${active}" type="button" data-note-name="${escapeHtml(note.name)}"
        ${state.busy ? "disabled" : ""}>
        <span aria-hidden="true">#</span>
        <strong>${escapeHtml(note.name)}</strong>
      </button>
    `;
  }).join("");
}

// Synchronizes busy, dirty, error, mode, and document-selection states.
function renderState() {
  const hasNote = Boolean(state.activeName);
  const workingStatus = state.busy || state.saving ? "Working…" : state.dirty ? "Waiting to save" : "";
  const status = state.error || workingStatus || (hasNote ? "Saved" : "Ready");
  const statusNode = byId("local-note-status");
  statusNode.textContent = status;
  statusNode.classList.toggle("error", Boolean(state.error));
  byId("local-note-active-name").textContent = state.activeName || "Choose or create a note";
  const source = byId("local-note-source");
  source.disabled = !hasNote || state.busy;
  if (source.value !== state.content) {
    source.value = state.content;
  }
  byId("local-note-name").disabled = state.busy;
  byId("create-local-note").disabled = state.busy;
  byId("close-local-notes").disabled = state.busy;
  byId("local-note-editor-shell").dataset.noteMode = state.mode;
  byId("local-notes-dialog").setAttribute("aria-busy", String(state.busy));
  document.querySelectorAll("[data-note-mode]").forEach((button) => {
    const active = button.dataset.noteMode === state.mode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  renderNoteList();
  renderPreview();
}

// Applies a native note catalog while retaining only a still-existing active note.
function applyNotesState(notesState) {
  state.notes = notesState && notesState.notes ? notesState.notes : [];
  if (!state.notes.some((note) => note.name === state.activeName)) {
    state.activeName = "";
  }
  byId("local-notes-context").textContent = notesState && notesState.version_name
    ? `${notesState.version_name} · Markdown files are saved in this version`
    : "Selected Local Mode version";
}

// Runs one modal-local native request without losing unsaved source on failure.
async function runNoteAction(action, payload) {
  state.busy = true;
  state.error = "";
  renderState();
  try {
    return await callNative(action, { ...requestContext(), ...(payload || {}) });
  } catch (error) {
    state.error = error.message || "Project note operation failed.";
    appendActivity(state.error, true);
    throw error;
  } finally {
    state.busy = false;
    renderState();
  }
}

// Opens one note after flushing any dirty source for the prior note.
async function loadNote(name) {
  if (state.busy || name === state.activeName) {
    return;
  }
  await flushSave();
  const data = await runNoteAction("readProjectNote", { name });
  state.activeName = data.note.name;
  state.content = data.note.content;
  state.revision = data.note.revision;
  state.dirty = false;
  state.error = "";
  renderState();
  byId("local-note-source").focus();
}

// Saves one dirty note immediately and updates its external-edit revision.
async function flushSave() {
  window.clearTimeout(state.saveTimer);
  state.saveTimer = 0;
  if (state.savePromise) {
    await state.savePromise;
    return;
  }
  if (!state.dirty || !state.activeName) {
    return;
  }
  const savingName = state.activeName;
  const savingContent = state.content;
  const savingRevision = state.revision;
  state.saving = true;
  state.error = "";
  renderState();
  state.savePromise = callNative("saveProjectNote", {
    ...requestContext(),
    name: savingName,
    content: savingContent,
    expected_revision: savingRevision,
  });
  try {
    const data = await state.savePromise;
    if (state.activeName === savingName) {
      state.revision = data.note.revision;
      state.dirty = state.content !== savingContent;
    }
    applyNotesState(data.notes);
    appendActivity(`Project note saved: ${savingName}`);
  } catch (error) {
    state.error = error.message || "Project note could not be saved.";
    appendActivity(state.error, true);
    throw error;
  } finally {
    state.saving = false;
    state.savePromise = null;
    renderState();
  }
  if (state.dirty) {
    scheduleSave();
  }
}

// Debounces Obsidian-style automatic persistence while rendering remains immediate.
function scheduleSave() {
  window.clearTimeout(state.saveTimer);
  state.saveTimer = window.setTimeout(() => {
    flushSave().catch(() => {});
  }, 650);
}

// Creates one direct-child Markdown file and selects its empty source.
async function createNote(event) {
  event.preventDefault();
  await flushSave();
  const input = byId("local-note-name");
  const data = await runNoteAction("createProjectNote", {
    name: input.value,
    content: "",
  });
  input.value = "";
  applyNotesState(data.notes);
  state.activeName = data.note.name;
  state.content = data.note.content;
  state.revision = data.note.revision;
  state.dirty = false;
  appendActivity(`Project note created: ${state.activeName}`);
  renderState();
  byId("local-note-source").focus();
}

// Opens the exact selected-version workspace and loads its first note when available.
async function open(context, trigger) {
  state.context = { ...(context || {}) };
  state.activeName = "";
  state.content = "";
  state.revision = "";
  state.dirty = false;
  state.error = "";
  state.returnFocus = trigger || document.activeElement;
  byId("local-notes-modal").hidden = false;
  byId("open-local-notes").setAttribute("aria-expanded", "true");
  document.querySelector(".app-shell").setAttribute("inert", "");
  renderState();
  try {
    const data = await runNoteAction("projectNotesState", {});
    applyNotesState(data.notes);
    renderState();
    if (state.notes.length) {
      await loadNote(state.notes[0].name);
    } else {
      byId("local-note-name").focus();
    }
  } catch (error) {
    byId("close-local-notes").focus();
    throw error;
  }
}

// Flushes dirty source before closing and restores the action-dock focus.
async function close() {
  if (state.busy) {
    return;
  }
  try {
    await flushSave();
  } catch (error) {
    byId("local-note-source").focus();
    return;
  }
  const returnFocus = state.returnFocus;
  state.returnFocus = null;
  byId("local-notes-modal").hidden = true;
  byId("open-local-notes").setAttribute("aria-expanded", "false");
  document.querySelector(".app-shell").removeAttribute("inert");
  if (returnFocus && returnFocus.isConnected) {
    returnFocus.focus();
  }
}

// Updates source, preview, dirty state, and automatic persistence after each edit.
function handleSourceInput(event) {
  state.content = event.target.value;
  state.dirty = true;
  state.error = "";
  renderPreview();
  renderState();
  scheduleSave();
}

// Keeps Markdown links inside the desktop security boundary.
function handlePreviewClick(event) {
  const link = event.target.closest("a[href]");
  if (!link) {
    return;
  }
  event.preventDefault();
  const href = link.getAttribute("href") || "";
  if (/^https?:\/\//i.test(href)) {
    callNative("openExternalUrl", { url: href }).catch((error) => {
      state.error = error.message || "The external link could not be opened.";
      renderState();
    });
  } else {
    state.error = "Only complete HTTP or HTTPS links can open from note preview.";
    renderState();
  }
}

// Handles note selection and Write/Split/Preview mode changes.
function handleClick(event) {
  const noteButton = event.target.closest("[data-note-name]");
  if (noteButton) {
    loadNote(noteButton.dataset.noteName || "").catch(() => {});
    return;
  }
  const modeButton = event.target.closest("[data-note-mode]");
  if (modeButton) {
    state.mode = modeButton.dataset.noteMode || "split";
    renderState();
  }
}

// Inserts two spaces for Markdown indentation instead of moving focus out of the editor.
function insertIndent(event) {
  const source = event.currentTarget;
  const start = source.selectionStart;
  const end = source.selectionEnd;
  source.setRangeText("  ", start, end, "end");
  source.dispatchEvent(new Event("input", { bubbles: true }));
}

// Supports Escape, explicit save, editor indentation, and contained modal focus.
function handleKeydown(event) {
  if (byId("local-notes-modal").hidden) {
    return;
  }
  if (event.target.id === "local-note-source" && event.key === "Tab") {
    event.preventDefault();
    insertIndent(event);
    return;
  }
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    flushSave().catch(() => {});
    return;
  }
  if (event.key === "Escape") {
    event.preventDefault();
    close().catch(() => {});
    return;
  }
  if (event.key !== "Tab") {
    return;
  }
  const controls = Array.from(byId("local-notes-dialog").querySelectorAll(
    'button:not(:disabled), input:not(:disabled), textarea:not(:disabled), [tabindex="0"]',
  ));
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

// Installs stable modal listeners once after Local Mode has injected its trigger.
function bind() {
  noteUI.inject();
  if (state.bound) {
    return;
  }
  state.bound = true;
  byId("create-local-note-form").addEventListener("submit", (event) => {
    createNote(event).catch(() => {});
  });
  byId("close-local-notes").addEventListener("click", () => close().catch(() => {}));
  byId("local-note-source").addEventListener("input", handleSourceInput);
  byId("local-note-list").addEventListener("click", handleClick);
  byId("local-notes-header").addEventListener("click", handleClick);
  byId("local-note-preview").addEventListener("click", handlePreviewClick);
  byId("local-notes-modal").addEventListener("click", (event) => {
    if (event.target === byId("local-notes-modal")) close().catch(() => {});
  });
  document.addEventListener("keydown", handleKeydown);
}

window.GitDeskLocalMarkdownNotes = { bind, open };
})();
