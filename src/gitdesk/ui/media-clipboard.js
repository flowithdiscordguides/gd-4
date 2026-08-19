/*
  Backend-owned clipboard paste for WebViews that do not dispatch copied files through browser paste events.
*/

// Keeps the one Media Paste action independent from drag-and-drop and browser clipboard permissions.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk Media clipboard dependencies did not load.");
}

const { appendActivity, byId, showMessage } = renderHelpers;
let callbacks = null;
let menu = null;
let pasting = false;

// Removes the single contextual Paste menu.
function hideMenu() {
  if (!menu) return;
  menu.remove();
  menu = null;
}

// Positions the menu within the visible window.
function positionMenu(node, x, y) {
  const left = Math.max(8, Math.min(x, window.innerWidth - 156));
  const top = Math.max(8, Math.min(y, window.innerHeight - 64));
  node.style.left = `${left}px`;
  node.style.top = `${top}px`;
}

// Returns whether a key event is the platform paste shortcut.
function isPasteShortcut(event) {
  const key = String(event.key || "").toLowerCase();
  return (event.metaKey || event.ctrlKey) && !event.altKey && key === "v";
}

// Shows exactly one app-owned Paste action and suppresses the unavailable WebView context menu.
function showPasteMenu(event) {
  event.preventDefault();
  event.stopPropagation();
  hideMenu();
  const tray = byId("media-intake-tray");
  tray.focus();
  const popup = document.createElement("div");
  popup.className = "media-paste-menu";
  popup.setAttribute("role", "menu");
  const button = document.createElement("button");
  button.type = "button";
  button.setAttribute("role", "menuitem");
  button.textContent = "Paste";
  button.addEventListener("click", () => {
    hideMenu();
    pasteClipboard().catch(() => {});
  });
  popup.appendChild(button);
  positionMenu(popup, event.clientX, event.clientY);
  document.body.appendChild(popup);
  menu = popup;
  button.focus();
}

// Updates the visible intake result without exposing copied source paths to the WebView.
function renderResult(result, albumName) {
  const imported = Array.isArray(result.imported) ? result.imported.length : 0;
  const failed = Array.isArray(result.failed) ? result.failed.length : 0;
  byId("media-intake-status").textContent =
    `${imported} pasted${failed ? ` · ${failed} skipped` : ""} · no existing files replaced`;
  const summary = `${imported} image${imported === 1 ? "" : "s"} pasted into ${albumName}`;
  appendActivity(summary, failed > 0);
  if (failed) {
    showMessage(`${failed} copied item${failed === 1 ? "" : "s"} could not be imported.`, true);
  }
}

// Returns whether paste may target the visible connected album rather than a hidden or modal workflow.
function clipboardIsAvailable() {
  const panel = document.getElementById("panel-media");
  const modal = document.getElementById("media-album-modal");
  const tray = byId("media-intake-tray");
  return Boolean(
    panel
    && panel.classList.contains("active")
    && tray.hidden === false
    && (!modal || modal.hidden),
  );
}

// Invokes the native clipboard reader used by both the keyboard and right-click paths.
async function pasteClipboard() {
  const album = callbacks.activeAlbum();
  const tray = byId("media-intake-tray");
  if (
    !clipboardIsAvailable()
    || !album
    || !album.exists
    || pasting
    || tray.classList.contains("importing")
  ) return;
  pasting = true;
  tray.classList.add("importing");
  byId("media-intake-title").textContent = `Pasting into ${album.name}`;
  let pasteError = "";
  try {
    const data = await callbacks.runAction("pasteMediaClipboard", {
      ...callbacks.queryPayload(1),
      album_id: album.id,
    }, "");
    callbacks.applyState(data);
    renderResult(data.clipboard_import || {}, album.name);
  } catch (error) {
    pasteError = error.message || "Clipboard paste failed.";
    showMessage(pasteError, true);
    appendActivity(pasteError, true);
  } finally {
    pasting = false;
    tray.classList.remove("importing");
    callbacks.renderIntake();
    if (pasteError) {
      byId("media-intake-status").textContent = pasteError;
    }
  }
}

// Routes Command/Ctrl+V from the focused field directly to the native clipboard reader.
function handleKeydown(event) {
  if (isPasteShortcut(event)) {
    event.preventDefault();
    event.stopPropagation();
    hideMenu();
    pasteClipboard().catch(() => {});
    return;
  }
  if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
    const rect = byId("media-intake-tray").getBoundingClientRect();
    showPasteMenu({
      preventDefault: () => event.preventDefault(),
      stopPropagation: () => event.stopPropagation(),
      clientX: rect.left + 24,
      clientY: rect.top + 24,
    });
  } else if (event.key === "Escape") {
    hideMenu();
  }
}

// Installs stable clipboard controls after Media intake has created the tray.
function bind(newCallbacks) {
  callbacks = newCallbacks;
  const tray = byId("media-intake-tray");
  tray.addEventListener("contextmenu", showPasteMenu);
  tray.addEventListener("keydown", handleKeydown);
  tray.addEventListener("pointerdown", (event) => {
    if (!event.target.closest("button, input")) tray.focus();
  });
  document.addEventListener("pointerdown", (event) => {
    if (menu && !menu.contains(event.target)) hideMenu();
  }, true);
  document.addEventListener("scroll", hideMenu, true);
  window.addEventListener("blur", hideMenu);
}

window.GitDeskMediaClipboard = { bind };
})();
