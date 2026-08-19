/*
  Categorized document picker and selected-document identity controls for Document Builder.
*/

// Keeps document switching and metadata editing outside the hierarchy renderer and native-action controller.
(() => {
const renderHelpers = window.GitDeskRender;
const documentRender = window.GitDeskDocumentBuilderRender;

if (!renderHelpers || !documentRender) {
  throw new Error("GitDesk Document Builder organizer dependencies did not load.");
}

const { byId, setText } = renderHelpers;
const { escapeHtml } = documentRender;

// Stable portal dimensions match Local Projects while preserving room for Document Builder's working columns.
const MENU_ID = "document-picker-menu";
const VIEWPORT_MARGIN = 12;
const MENU_TRIGGER_GAP = 6;
const MENU_MIN_WIDTH = 220;
const MENU_BASE_MAX_WIDTH = 360;
const MENU_EXTRA_WIDTH = 48;
const MENU_BASE_MAX_HEIGHT = 320;
const ADDITIONAL_OPTION_COUNT = 5;
let callbacks = {};
let activeDocumentPath = "";
let activeDocumentName = "";
let activeDocumentCategory = "";
let renameEditing = false;
let bound = false;
// Compares categories and documents case-insensitively while keeping numbered labels naturally ordered.
function compareLabels(left, right) {
  return String(left || "").localeCompare(String(right || ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}
// Returns alphabetized categories whose documents are independently alphabetized for predictable scanning.
function categorizedDocuments(documents) {
  const groups = new Map();
  documents.forEach((documentRecord) => {
    const category = String(documentRecord.category || "").trim() || "Uncategorized";
    if (!groups.has(category)) {
      groups.set(category, []);
    }
    groups.get(category).push(documentRecord);
  });
  return Array.from(groups, ([category, groupedDocuments]) => ({
    category,
    documents: groupedDocuments.slice().sort((left, right) => compareLabels(left.name, right.name)),
  })).sort((left, right) => compareLabels(left.category, right.category));
}
// Returns every saved category in alphabetical order for both creation and active-document editing.
function categoryOptions(state) {
  const values = new Set();
  (state.categories || []).concat(state.documents || []).forEach((item) => {
    const category = String(item && item.category ? item.category : item || "").trim();
    if (category) {
      values.add(category);
    }
  });
  return Array.from(values).sort(compareLabels);
}
// Creates a body-level listbox so card and panel overflow cannot clip document choices.
function injectMenu() {
  if (!document.getElementById(MENU_ID)) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="${MENU_ID}" class="document-picker-menu" role="listbox"
        aria-label="Saved documents" hidden></div>
    `);
  }
}
// Returns all selectable document options in their current alphabetical visual order.
function optionButtons() {
  return Array.from(byId(MENU_ID).querySelectorAll("[data-document-path]"));
}
// Constrains portal coordinates and scrolling to a safe numeric interval.
function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), Math.max(minimum, maximum));
}
// Anchors below the trigger, then expands only rightward and downward through five more measured documents.
function positionMenu(target) {
  const trigger = byId("document-picker-trigger");
  const menu = byId(MENU_ID);
  const triggerRect = trigger.getBoundingClientRect();
  const availableWidth = Math.max(1, window.innerWidth - (VIEWPORT_MARGIN * 2));
  const baseWidth = Math.min(
    Math.max(triggerRect.width, MENU_MIN_WIDTH),
    MENU_BASE_MAX_WIDTH,
    availableWidth,
  );
  const centeredLeft = triggerRect.left + (triggerRect.width / 2) - (baseWidth / 2);
  const baseLeft = clamp(
    centeredLeft,
    VIEWPORT_MARGIN,
    window.innerWidth - baseWidth - VIEWPORT_MARGIN,
  );
  const width = Math.min(baseWidth + MENU_EXTRA_WIDTH, window.innerWidth - VIEWPORT_MARGIN - baseLeft);
  const top = Math.max(triggerRect.bottom + MENU_TRIGGER_GAP, VIEWPORT_MARGIN);
  const availableHeight = Math.max(1, window.innerHeight - top - VIEWPORT_MARGIN);
  menu.style.width = `${width}px`;
  menu.style.left = `${baseLeft}px`;
  menu.style.top = `${top}px`;
  menu.style.maxHeight = `${Math.min(MENU_BASE_MAX_HEIGHT, availableHeight)}px`;
  menu.style.visibility = "hidden";
  menu.hidden = false;
  menu.scrollTop = 0;

  const targetCenter = target ? target.offsetTop + (target.offsetHeight / 2) : menu.offsetHeight / 2;
  const baselineMenuHeight = menu.offsetHeight;
  const baselineScrollTop = clamp(
    targetCenter - (menu.clientHeight / 2),
    0,
    menu.scrollHeight - menu.clientHeight,
  );
  menu.scrollTop = baselineScrollTop;

  const baselineContentBottom = baselineScrollTop + menu.clientHeight;
  const options = optionButtons();
  const additionalOptionsBelow = options.filter((option) => (
    option.offsetTop >= baselineContentBottom - 1
  )).slice(0, ADDITIONAL_OPTION_COUNT);
  const remainingOptionCount = ADDITIONAL_OPTION_COUNT - additionalOptionsBelow.length;
  // Avoid `slice(-0)`, which would include every preceding document when five lower choices already exist.
  const additionalOptionsAbove = remainingOptionCount
    ? options.filter((option) => (
      option.offsetTop + option.offsetHeight <= baselineScrollTop + 1
    )).slice(-remainingOptionCount)
    : [];
  const firstAdditionalOption = additionalOptionsAbove[0];
  const lastAdditionalOption = additionalOptionsBelow[additionalOptionsBelow.length - 1];
  const desiredContentTop = firstAdditionalOption ? firstAdditionalOption.offsetTop : baselineScrollTop;
  const desiredContentBottom = lastAdditionalOption
    ? lastAdditionalOption.offsetTop + lastAdditionalOption.offsetHeight
    : baselineContentBottom;
  const desiredContentSpan = desiredContentBottom - desiredContentTop;
  const desiredHeight = baselineMenuHeight + Math.max(0, desiredContentSpan - menu.clientHeight);

  menu.style.maxHeight = `${Math.min(desiredHeight, availableHeight)}px`;
  menu.style.visibility = "";
  menu.scrollTop = desiredContentTop;
}
// Closes the portal and optionally returns keyboard focus to the compact trigger.
function closeMenu(restoreFocus = false) {
  const menu = document.getElementById(MENU_ID);
  const trigger = document.getElementById("document-picker-trigger");
  if (menu) {
    menu.hidden = true;
    menu.style.visibility = "";
  }
  if (trigger) {
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) {
      trigger.focus();
    }
  }
}
// Opens below the trigger and focuses the current document, or the first record when none is active.
function openMenu() {
  const trigger = byId("document-picker-trigger");
  if (trigger.disabled) {
    return;
  }
  trigger.setAttribute("aria-expanded", "true");
  const options = optionButtons();
  const target = options.find((option) => option.dataset.documentPath === activeDocumentPath) || options[0];
  positionMenu(target);
  if (target) {
    target.focus({ preventScroll: true });
  }
}
// Settles controller promises locally because native actions already render their own user-facing errors.
function invokeCallback(callback, args, onFailure) {
  if (!callback) {
    return;
  }
  try {
    Promise.resolve(callback(...args)).catch(onFailure || (() => {}));
  } catch (error) {
    if (onFailure) {
      onFailure(error);
    } else {
      console.error("Document Builder identity action failed", error);
    }
  }
}
// Commits one option through the canonical controller callback without changing state optimistically.
function chooseOption(option) {
  const path = option ? option.dataset.documentPath || "" : "";
  closeMenu(true);
  if (path && path !== activeDocumentPath) {
    invokeCallback(callbacks.onSelect, [path]);
  }
}
// Toggles the portal from the compact combobox trigger.
function handleTriggerClick() {
  if (byId(MENU_ID).hidden) {
    openMenu();
  } else {
    closeMenu(true);
  }
}
// Opens from standard combobox keys while leaving Tab available for natural focus navigation.
function handleTriggerKeydown(event) {
  if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
    event.preventDefault();
    openMenu();
  } else if (event.key === "Escape") {
    closeMenu(true);
  }
}
// Moves through choices and commits or dismisses the listbox with conventional keyboard commands.
function handleMenuKeydown(event) {
  const options = optionButtons();
  const currentIndex = options.indexOf(document.activeElement);
  let nextIndex = currentIndex;
  if (event.key === "ArrowDown") nextIndex = Math.min(currentIndex + 1, options.length - 1);
  if (event.key === "ArrowUp") nextIndex = Math.max(currentIndex - 1, 0);
  if (event.key === "Home") nextIndex = 0;
  if (event.key === "End") nextIndex = options.length - 1;
  if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    if (options[nextIndex]) options[nextIndex].focus();
  } else if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    chooseOption(document.activeElement.closest("[data-document-path]"));
  } else if (event.key === "Escape") {
    event.preventDefault();
    closeMenu(true);
  } else if (event.key === "Tab") {
    closeMenu(true);
  }
}
// Selects pointer-activated options while category headings and menu padding remain inert.
function handleMenuClick(event) {
  const option = event.target.closest("[data-document-path]");
  if (option) {
    chooseOption(option);
  }
}
// Dismisses the portal when the pointer moves to another app control.
function handleDocumentPointerDown(event) {
  const target = event.target instanceof Element ? event.target : null;
  if (!target || !target.closest(`#${MENU_ID}, #document-picker-trigger`)) {
    closeMenu(false);
  }
}
// Closes the menu when an outside scroll or resize invalidates its measured viewport coordinates.
function handleViewportChange(event) {
  if (event.type === "resize" || event.target !== byId(MENU_ID)) {
    closeMenu(false);
  }
}
// Swaps only the selected label for its rename field while preserving the adjacent pencil action.
function setRenameEditing(enabled, focusInput = false) {
  const name = byId("document-active-name");
  const input = byId("document-rename-name");
  const button = byId("rename-document");
  renameEditing = Boolean(enabled && activeDocumentPath);
  name.hidden = renameEditing;
  input.hidden = !renameEditing;
  button.title = renameEditing ? "Save document name" : "Rename document";
  button.setAttribute("aria-label", button.title);
  button.setAttribute("aria-pressed", String(renameEditing));
  if (renameEditing && focusInput) {
    input.focus();
    input.select();
  }
}
// Enters rename mode on the first pencil press and commits the edited label on the second press.
function handleRenameToggle() {
  if (!activeDocumentPath) {
    return;
  }
  if (!renameEditing) {
    byId("document-rename-name").value = activeDocumentName;
    setRenameEditing(true, true);
    return;
  }
  const nextName = byId("document-rename-name").value.trim();
  if (!nextName || nextName === activeDocumentName) {
    setRenameEditing(false);
    return;
  }
  setRenameEditing(false);
  invokeCallback(callbacks.onRename, [activeDocumentPath, nextName], () => {
    setRenameEditing(true, true);
  });
}
// Supports keyboard save and cancellation without leaving a permanent rename field in the card.
function handleRenameKeydown(event) {
  if (event.key === "Enter") {
    event.preventDefault();
    handleRenameToggle();
  } else if (event.key === "Escape") {
    event.preventDefault();
    byId("document-rename-name").value = activeDocumentName;
    setRenameEditing(false);
    byId("rename-document").focus();
  }
}
// Saves the active document's category and restores canonical state if the native action fails.
function handleCategoryChange(event) {
  if (activeDocumentPath) {
    invokeCallback(callbacks.onCategoryChange, [activeDocumentPath, event.target.value], () => {
      event.target.value = activeDocumentCategory;
    });
  }
}
// Commits keyboard category editing through the normal change and blur path.
function handleCategoryKeydown(event) {
  if (event.key === "Enter") {
    event.preventDefault();
    event.target.blur();
  }
}
// Renders sorted picker groups and selected-document identity from canonical backend state.
function render(state) {
  closeMenu(false);
  const records = Array.isArray(state.documents) ? state.documents : [];
  const activeDocument = records.find((item) => item.path === state.active_document) || null;
  const nextPath = activeDocument ? activeDocument.path : "";
  const nextName = activeDocument ? activeDocument.name : "";
  if (nextPath !== activeDocumentPath || nextName !== activeDocumentName) {
    renameEditing = false;
  }
  activeDocumentPath = nextPath;
  activeDocumentName = nextName;
  activeDocumentCategory = activeDocument ? activeDocument.category || "" : "";

  const trigger = byId("document-picker-trigger");
  const triggerLabel = activeDocument
    ? `${activeDocument.name}${activeDocument.exists ? "" : " — missing"}`
    : records.length ? "Select a document" : "No documents";
  setText("document-picker-label", triggerLabel);
  trigger.disabled = !records.length;

  byId(MENU_ID).innerHTML = categorizedDocuments(records).map((group, groupIndex) => {
    const labelId = `document-picker-category-${groupIndex}`;
    const options = group.documents.map((documentRecord) => {
      const selected = documentRecord.path === activeDocumentPath;
      const missing = documentRecord.exists ? "" : '<small class="document-picker-missing">Missing</small>';
      return `
        <button type="button" role="option" tabindex="-1"
          data-document-path="${escapeHtml(documentRecord.path)}" aria-selected="${selected}"
          class="${selected ? "selected" : ""}">
          <span>${escapeHtml(documentRecord.name)}</span>${missing}
        </button>
      `;
    }).join("");
    return `
      <div class="document-picker-category" role="group" aria-labelledby="${labelId}">
        <div id="${labelId}" class="document-picker-category-label">${escapeHtml(group.category)}</div>
        ${options}
      </div>
    `;
  }).join("");

  byId("document-category-options").innerHTML = categoryOptions(state).map((category) => (
    `<option value="${escapeHtml(category)}"></option>`
  )).join("");
  setText("document-active-name", activeDocument ? activeDocument.name : "No document selected");
  const renameInput = byId("document-rename-name");
  if (!renameEditing) {
    renameInput.value = activeDocumentName;
  }
  const hasAvailableDocument = Boolean(activeDocument && activeDocument.exists);
  renameInput.disabled = !hasAvailableDocument;
  byId("rename-document").disabled = !hasAvailableDocument;
  setRenameEditing(renameEditing && hasAvailableDocument);
  const categoryInput = byId("document-active-category");
  categoryInput.value = activeDocumentCategory;
  categoryInput.disabled = !activeDocument;
}
// Binds picker and identity controls once while allowing controller callbacks to refresh.
function bind(options) {
  callbacks = options || {};
  injectMenu();
  if (bound) {
    return;
  }
  bound = true;
  byId("document-picker-trigger").addEventListener("click", handleTriggerClick);
  byId("document-picker-trigger").addEventListener("keydown", handleTriggerKeydown);
  byId(MENU_ID).addEventListener("click", handleMenuClick);
  byId(MENU_ID).addEventListener("keydown", handleMenuKeydown);
  byId("rename-document").addEventListener("click", handleRenameToggle);
  byId("document-rename-name").addEventListener("keydown", handleRenameKeydown);
  byId("document-active-category").addEventListener("change", handleCategoryChange);
  byId("document-active-category").addEventListener("keydown", handleCategoryKeydown);
  document.addEventListener("pointerdown", handleDocumentPointerDown);
  document.addEventListener("scroll", handleViewportChange, true);
  window.addEventListener("resize", handleViewportChange);
}
window.GitDeskDocumentBuilderOrganizer = { bind, render };
})();
