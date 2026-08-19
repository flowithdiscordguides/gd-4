/* User settings controller and shared display names for external editor actions. */

(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
if (!nativeBridge || !renderHelpers) throw new Error("GitDesk editor settings dependencies did not load.");

const { callNative } = nativeBridge;
const { byId, setTooltipText, showMessage } = renderHelpers;
const EDITOR_NAMES = { vscode: "VS Code", vscodium: "VSCodium" };
let preferences = { editor: "vscode", vscodium_path: "" };
let editorState = {
  platform: "",
  editors: {
    vscode: { name: "VS Code", available: false, path: "" },
    vscodium: { name: "VSCodium", available: false, path: "" },
  },
};
let busy = false;
let feedback = "";
let feedbackError = false;
let bound = false;
let bindAttempts = 0;

function cleanPreferences(value) {
  const source = value && typeof value === "object" ? value : {};
  return {
    editor: ["vscode", "vscodium"].includes(source.editor) ? source.editor : "vscode",
    vscodium_path: String(source.vscodium_path || ""),
  };
}

function name() {
  return EDITOR_NAMES[preferences.editor];
}

function fillTemplate(template) {
  return String(template || "").replaceAll("{editor}", name());
}

function refreshLabels(root = document) {
  root.querySelectorAll("[data-editor-label-template]").forEach((element) => {
    element.textContent = fillTemplate(element.dataset.editorLabelTemplate);
  });
  root.querySelectorAll("[data-editor-aria-template]").forEach((element) => {
    element.setAttribute("aria-label", fillTemplate(element.dataset.editorAriaTemplate));
  });
  root.querySelectorAll("[data-editor-tooltip-template]").forEach((element) => {
    setTooltipText(element, fillTemplate(element.dataset.editorTooltipTemplate));
  });
}

function injectCard() {
  if (document.getElementById("editor-settings-card")) return true;
  const mount = document.getElementById("settings-user-content");
  if (!mount) return false;
  const categoryCard = document.getElementById("category-folders-card");
  const insertionTarget = categoryCard || mount;
  const insertionPosition = categoryCard ? "afterend" : "afterbegin";
  insertionTarget.insertAdjacentHTML(insertionPosition, `
    <section id="editor-settings-card" class="settings-block editor-settings-card"
      aria-labelledby="editor-settings-title">
      <header><div><strong id="editor-settings-title">External code editor</strong>
        <p>Choose which editor opens repositories, versions, and Document Builder files.</p></div>
        <span id="editor-settings-badge"></span></header>
      <fieldset><legend>Open with</legend>
        <div class="editor-choice-switch" role="group" aria-label="Preferred external editor">
          <button type="button" data-editor-choice="vscode">VS Code</button>
          <button type="button" data-editor-choice="vscodium">VSCodium</button>
        </div>
      </fieldset>
      <div id="editor-discovery" class="editor-discovery"></div>
      <div id="vscodium-path-control" class="editor-path-control" hidden>
        <div><span>VSCodium executable</span><output id="vscodium-path"></output></div>
        <button id="choose-vscodium-path" type="button">Browse</button>
      </div>
      <footer><p id="editor-settings-status" role="status" aria-live="polite"></p>
        <button id="save-editor-settings" class="primary" type="button">Save editor</button></footer>
    </section>`);
  return true;
}

function availabilityText(editor) {
  const info = editorState.editors[editor];
  if (info.available) return `Found ${info.name}${info.path ? ` at ${info.path}` : ""}.`;
  if (editor === "vscodium" && editorState.platform !== "Darwin") {
    return "Choose the VSCodium executable to make it available.";
  }
  return `${info.name} was not found in the expected installation locations.`;
}

function render() {
  if (!document.getElementById("editor-settings-card")) return;
  document.querySelectorAll("[data-editor-choice]").forEach((button) => {
    const editor = button.dataset.editorChoice;
    const active = preferences.editor === editor;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.classList.toggle("unavailable", !editorState.editors[editor].available);
  });
  const selected = editorState.editors[preferences.editor];
  byId("editor-settings-badge").textContent = name();
  byId("editor-discovery").textContent = availabilityText(preferences.editor);
  const showPath = Boolean(editorState.platform) && editorState.platform !== "Darwin";
  byId("vscodium-path-control").hidden = !showPath;
  byId("vscodium-path").textContent = preferences.vscodium_path || "No executable selected";
  byId("choose-vscodium-path").disabled = busy;
  byId("save-editor-settings").disabled = busy || !selected.available;
  const status = byId("editor-settings-status");
  status.textContent = feedback;
  status.classList.toggle("danger", feedbackError);
  refreshLabels();
}

function adoptState(value) {
  if (!value || typeof value !== "object") return;
  editorState = value;
  preferences = cleanPreferences(value.preferences || preferences);
  render();
}

async function loadState() {
  try {
    adoptState(await callNative("editorSettingsState", {}));
  } catch (error) {
    feedback = error.message || "Editor installations could not be checked.";
    feedbackError = true;
    render();
  }
}

async function chooseVSCodium() {
  if (busy) return;
  busy = true;
  feedback = "Opening the executable picker…";
  feedbackError = false;
  render();
  try {
    const state = await callNative("chooseVSCodiumExecutable", {
      initial_path: preferences.vscodium_path,
    });
    adoptState(state);
    preferences.editor = "vscodium";
    feedback = state.editors.vscodium.available ? "VSCodium is ready to save." : "No executable selected.";
  } catch (error) {
    feedback = error.message || "VSCodium could not be selected.";
    feedbackError = true;
  } finally {
    busy = false;
    render();
  }
}

async function save() {
  if (busy || !editorState.editors[preferences.editor].available) return;
  busy = true;
  feedback = `Saving ${name()}…`;
  feedbackError = false;
  render();
  try {
    const data = await callNative("saveEditorPreferences", { editor_preferences: preferences });
    adoptState(data.editor_state);
    feedback = `${name()} will open repositories, versions, and documents.`;
  } catch (error) {
    feedback = error.message || "The editor preference could not be saved.";
    feedbackError = true;
    showMessage(feedback, true);
  } finally {
    busy = false;
    render();
  }
}

function handleClick(event) {
  const choice = event.target.closest("[data-editor-choice]");
  if (choice) {
    preferences.editor = choice.dataset.editorChoice;
    feedback = editorState.editors[preferences.editor].available
      ? `${name()} is ready to save.`
      : availabilityText(preferences.editor);
    feedbackError = false;
    render();
  }
  if (event.target.closest("#choose-vscodium-path")) chooseVSCodium();
  if (event.target.closest("#save-editor-settings")) save();
}

function applySettings(settings) {
  preferences = cleanPreferences(settings && settings.editor_preferences);
  if (editorState.preferences) editorState.preferences = preferences;
  render();
}

function bind() {
  if (bound) return;
  if (!injectCard()) {
    bindAttempts += 1;
    if (bindAttempts < 5) window.setTimeout(bind, 0);
    return;
  }
  const card = document.getElementById("editor-settings-card");
  bound = true;
  card.addEventListener("click", handleClick);
  render();
  loadState();
}

window.GitDeskEditorSettings = { applySettings, fillTemplate, name, refreshLabels };
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
else bind();
})();
