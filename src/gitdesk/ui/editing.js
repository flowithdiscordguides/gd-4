/*
  App-owned editing support for the WebUI shell.
  Text paste crosses the native bridge because the embedded WebView does not expose a working native paste path.
*/

// Keeps form editing and document-selection behavior isolated from feature controllers.
(() => {
const EDITABLE_INPUT_TYPES = new Set([
  "email",
  "password",
  "search",
  "tel",
  "text",
  "url",
]);

let activeMenu = null;

// Accepts a DOM node and returns whether it is a user-editable text control that can receive pasted text.
function isEditableControl(node) {
  if (!node || node.disabled || node.readOnly) {
    return false;
  }

  const tagName = node.tagName ? node.tagName.toLowerCase() : "";
  if (tagName === "textarea") {
    return true;
  }
  if (tagName !== "input") {
    return false;
  }
  return EDITABLE_INPUT_TYPES.has(String(node.type || "text").toLowerCase());
}

// Returns the current document selection text outside form controls, or an empty string.
function selectedDocumentText() {
  const selection = window.getSelection ? window.getSelection() : null;
  return selection ? String(selection.toString() || "") : "";
}

// Accepts text and returns whether it was copied using the async Clipboard API.
async function writeClipboardText(text) {
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (error) {
    return false;
  }
  return false;
}

// Accepts text and returns whether the legacy copy command could place it onto the clipboard.
function runLegacyCopyCommand(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.top = "-1000px";
  textarea.style.left = "-1000px";
  document.body.appendChild(textarea);
  textarea.select();

  let copied = false;
  try {
    copied = Boolean(document.execCommand && document.execCommand("copy"));
  } catch (error) {
    copied = false;
  }
  document.body.removeChild(textarea);
  return copied;
}

// Accepts selected text and returns nothing after trying every available local copy path.
async function copyText(text) {
  const cleanedText = String(text || "");
  if (!cleanedText) {
    return;
  }
  if (await writeClipboardText(cleanedText)) {
    return;
  }
  runLegacyCopyCommand(cleanedText);
}

// Accepts a keyboard event and returns whether it represents copy on common desktop platforms.
function isCopyShortcut(event) {
  const key = String(event.key || "").toLowerCase();
  return (event.metaKey || event.ctrlKey) && !event.altKey && key === "c";
}

// Accepts a keyboard event and returns whether it represents paste on common desktop platforms.
function isPasteShortcut(event) {
  const key = String(event.key || "").toLowerCase();
  return (event.metaKey || event.ctrlKey) && !event.altKey && key === "v";
}

// Accepts an editable control and returns its current replacement range.
function controlSelection(control) {
  const valueLength = String(control.value || "").length;
  const start = Number.isInteger(control.selectionStart) ? control.selectionStart : valueLength;
  const end = Number.isInteger(control.selectionEnd) ? control.selectionEnd : start;
  return {
    start: Math.max(0, Math.min(start, valueLength)),
    end: Math.max(0, Math.min(end, valueLength)),
  };
}

// Returns clipboard text through GitDesk's OS-owned native bridge.
async function readClipboardText() {
  const bridge = window.GitDeskNativeBridge;
  if (!bridge || typeof bridge.callNative !== "function") {
    throw new Error("The native clipboard bridge is unavailable.");
  }
  const result = await bridge.callNative("readClipboardText", {});
  return typeof result.text === "string" ? result.text : "";
}

// Accepts a control, clipboard text, and replacement range, then applies a native-like input mutation.
function pasteIntoControl(control, text, range) {
  const value = String(control.value || "");
  const selected = range || controlSelection(control);
  let insertedText = String(text || "");
  if (control.maxLength >= 0) {
    const retainedLength = value.length - (selected.end - selected.start);
    const availableLength = Math.max(0, control.maxLength - retainedLength);
    insertedText = insertedText.slice(0, availableLength);
  }
  if (!insertedText) return;

  control.focus();
  control.setRangeText(insertedText, selected.start, selected.end, "end");
  let inputEvent;
  try {
    inputEvent = new InputEvent("input", {
      bubbles: true,
      data: insertedText,
      inputType: "insertFromPaste",
    });
  } catch (error) {
    inputEvent = new Event("input", { bubbles: true });
  }
  control.dispatchEvent(inputEvent);
}

// Accepts an editable control and selection, then reads and inserts the current OS clipboard text.
async function pasteClipboardIntoControl(control, range) {
  if (!isEditableControl(control)) return;
  const text = await readClipboardText();
  pasteIntoControl(control, text, range);
}

// Accepts a clipboard error and reports it through the existing user-visible message surface.
function reportPasteError(error) {
  const message = error && error.message ? error.message : "Clipboard paste failed.";
  const renderHelpers = window.GitDeskRender;
  if (renderHelpers && typeof renderHelpers.showMessage === "function") {
    renderHelpers.showMessage(message, true);
    return;
  }
  console.error(message);
}

// Accepts a keyboard event and returns nothing after applying supported edit shortcuts.
function handleEditShortcut(event) {
  const target = event.target;
  if (event.key === "Escape") {
    hideEditMenu();
    return;
  }
  if (isEditableControl(target)) {
    if (isPasteShortcut(event)) {
      const range = controlSelection(target);
      event.preventDefault();
      event.stopPropagation();
      hideEditMenu();
      pasteClipboardIntoControl(target, range).catch(reportPasteError);
    }
    return;
  }
  if (isCopyShortcut(event)) {
    const text = selectedDocumentText();
    if (text) {
      event.preventDefault();
      copyText(text);
    }
  }
}

// Removes the current custom edit menu and returns nothing.
function hideEditMenu() {
  if (!activeMenu) {
    return;
  }
  activeMenu.remove();
  activeMenu = null;
}

// Accepts a menu node and screen coordinates, then returns nothing after positioning the menu.
function positionEditMenu(menu, x, y) {
  menu.style.position = "fixed";
  menu.style.zIndex = "9999";
  menu.style.left = `${Math.max(8, Math.min(x, window.innerWidth - 180))}px`;
  menu.style.top = `${Math.max(8, Math.min(y, window.innerHeight - 92))}px`;
}

// Accepts a label and click callback, then returns a button for the custom edit menu.
function createMenuButton(label, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.style.display = "block";
  button.style.width = "100%";
  button.style.textAlign = "left";
  button.addEventListener("click", async (event) => {
    event.preventDefault();
    await onClick();
    hideEditMenu();
  });
  return button;
}

// Accepts a context-menu event and action list, then returns nothing after showing fallback actions.
function showEditMenu(event, actions) {
  hideEditMenu();
  const menu = document.createElement("div");
  menu.setAttribute("role", "menu");
  menu.style.minWidth = "132px";
  menu.style.padding = "6px";
  menu.style.border = "1px solid var(--line)";
  menu.style.borderRadius = "6px";
  menu.style.background = "var(--panel)";
  menu.style.boxShadow = "var(--shadow)";
  actions.forEach((action) => {
    menu.appendChild(createMenuButton(action.label, action.run));
  });
  positionEditMenu(menu, event.clientX, event.clientY);
  document.body.appendChild(menu);
  activeMenu = menu;
}

// Accepts a context-menu event and returns nothing after replacing missing native edit menus.
function handleContextMenu(event) {
  hideEditMenu();
  const target = event.target;
  if (isEditableControl(target)) {
    const range = controlSelection(target);
    const actions = [{
      label: "Paste",
      run: () => pasteClipboardIntoControl(target, range).catch(reportPasteError),
    }];
    if (String(target.value || "")) {
      actions.push({
        label: "Select all",
        run: () => {
          target.focus();
          target.select();
        },
      });
    }
    event.preventDefault();
    showEditMenu(event, actions);
    return;
  }

  const text = selectedDocumentText();
  if (!text) {
    return;
  }
  event.preventDefault();
  showEditMenu(event, [{ label: "Copy", run: () => copyText(text) }]);
}

// Installs document-level edit fallbacks and returns nothing.
function bindEditingSupport() {
  document.addEventListener("keydown", handleEditShortcut, true);
  document.addEventListener("contextmenu", handleContextMenu);
  document.addEventListener("input", hideEditMenu, true);
  document.addEventListener("paste", hideEditMenu, true);
  document.addEventListener("scroll", hideEditMenu, true);
  document.addEventListener("pointerdown", (event) => {
    if (activeMenu && !activeMenu.contains(event.target)) {
      hideEditMenu();
    }
  }, true);
  document.addEventListener("click", (event) => {
    if (activeMenu && !activeMenu.contains(event.target)) {
      hideEditMenu();
    }
  });
  window.addEventListener("blur", hideEditMenu);
}

// Accepts a callback and returns nothing after running it when document listeners can be installed.
function onDocumentReady(callback) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", callback);
    return;
  }
  callback();
}

onDocumentReady(bindEditingSupport);
})();
