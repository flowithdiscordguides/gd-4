/*
  Fixed-form dropdown for creating and selecting feature folders in the Local Mode project ribbon.
*/

// Keeps feature menu focus, scrolling, and pending creation state separate from project and version controllers.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk Local feature picker dependencies did not load.");
}

const { byId } = renderHelpers;
const MENU_ID = "local-feature-picker-menu";
const TRIGGER_ID = "local-feature-picker-trigger";
const VIEWPORT_MARGIN = 12;
const MENU_TRIGGER_GAP = 6;
const MENU_MIN_WIDTH = 300;
const MENU_MAX_WIDTH = 440;
const MENU_MAX_HEIGHT = 430;
let onFeatureCreate = null;
let onFeatureSelect = null;
let activeFeaturePath = "";
let projectAvailable = false;
let creating = false;
let bound = false;

// Escapes filesystem-derived feature labels and paths before building option markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Creates one body-level popover so the ribbon's overflow boundary never clips the form or feature list.
function injectMenu() {
  if (document.getElementById(MENU_ID)) {
    return;
  }
  document.body.insertAdjacentHTML("beforeend", `
    <section id="${MENU_ID}" class="local-feature-picker-menu" role="dialog"
      aria-label="Choose or create a project feature" hidden>
      <form id="local-feature-form" class="local-feature-picker-form">
        <label for="local-feature-name">Create new feature</label>
        <div class="local-feature-picker-create-row">
          <input id="local-feature-name" type="text" maxlength="80" required spellcheck="true"
            autocomplete="off" placeholder="Feature name" disabled>
          <button id="create-local-feature" type="submit" disabled>Create</button>
        </div>
      </form>
      <div id="local-feature-picker-list" class="local-feature-picker-list" role="menu"
        aria-label="Project features" aria-live="polite"></div>
    </section>
  `);
}

// Returns the active project without assuming that a saved selection still exists in the refreshed payload.
function activeProject(localState) {
  return (localState.projects || []).find((project) => project.path === localState.active_project) || null;
}

// Returns feature options in backend order because their numeric folder prefixes define workflow order.
function optionButtons() {
  return Array.from(byId("local-feature-picker-list").querySelectorAll("[data-feature-path]"));
}

// Resolves a feature option without embedding a filesystem path in a CSS selector.
function optionForPath(path) {
  return optionButtons().find((option) => option.dataset.featurePath === path) || null;
}

// Constrains portal geometry without attaching resize or scroll listeners that could move an open menu.
function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), Math.max(minimum, maximum));
}

// Positions the popover exactly once per opening; subsequent rendering preserves user-owned coordinates and scroll.
function positionMenu() {
  const trigger = byId(TRIGGER_ID);
  const menu = byId(MENU_ID);
  const triggerRect = trigger.getBoundingClientRect();
  const availableWidth = Math.max(1, window.innerWidth - (VIEWPORT_MARGIN * 2));
  const width = Math.min(Math.max(triggerRect.width, MENU_MIN_WIDTH), MENU_MAX_WIDTH, availableWidth);
  const left = clamp(
    triggerRect.left,
    VIEWPORT_MARGIN,
    window.innerWidth - width - VIEWPORT_MARGIN,
  );
  const top = Math.max(triggerRect.bottom + MENU_TRIGGER_GAP, VIEWPORT_MARGIN);
  const availableHeight = Math.max(1, window.innerHeight - top - VIEWPORT_MARGIN);
  const maxHeight = Math.min(MENU_MAX_HEIGHT, availableHeight);
  menu.style.width = `${width}px`;
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  menu.style.maxHeight = `${maxHeight}px`;
  menu.style.setProperty("--local-feature-list-max-height", `${Math.max(72, maxHeight - 92)}px`);
}

// Synchronizes creation availability while preserving a typed value through state refreshes and failures.
function renderCreationState() {
  const input = byId("local-feature-name");
  const button = byId("create-local-feature");
  input.disabled = !projectAvailable || creating;
  button.disabled = !projectAvailable || creating;
  button.textContent = creating ? "Creating…" : "Create";
}

// Closes the popover and optionally restores focus to the control that owns it.
function closeMenu(restoreFocus = false) {
  const menu = document.getElementById(MENU_ID);
  const trigger = document.getElementById(TRIGGER_ID);
  if (menu) {
    menu.hidden = true;
  }
  if (trigger) {
    trigger.setAttribute("aria-expanded", "false");
    if (restoreFocus) {
      trigger.focus();
    }
  }
}

// Opens below the trigger and reveals the current feature once without later overriding manual list movement.
function openMenu() {
  const trigger = byId(TRIGGER_ID);
  if (trigger.disabled) {
    return;
  }
  const menu = byId(MENU_ID);
  const list = byId("local-feature-picker-list");
  trigger.setAttribute("aria-expanded", "true");
  menu.hidden = false;
  positionMenu();
  const target = optionForPath(activeFeaturePath) || optionButtons()[0];
  list.scrollTop = target
    ? clamp(target.offsetTop - (list.clientHeight / 2), 0, list.scrollHeight - list.clientHeight)
    : 0;
  if (target) {
    target.focus({ preventScroll: true });
  } else {
    byId("local-feature-name").focus({ preventScroll: true });
  }
}

// Sends selection through the canonical controller action without changing visible state optimistically.
function chooseOption(option) {
  const path = option ? option.dataset.featurePath || "" : "";
  if (path && path !== activeFeaturePath && onFeatureSelect) {
    Promise.resolve(onFeatureSelect(path)).catch(() => {});
  }
}

// Toggles only for real mouse clicks so synthesized keyboard clicks cannot unexpectedly dismiss the popover.
function handleTriggerClick(event) {
  if (event.detail < 1) {
    return;
  }
  if (byId(MENU_ID).hidden) {
    openMenu();
  } else {
    closeMenu(true);
  }
}

// Opens through standard popup keys while leaving Tab available for the form and natural focus order.
function handleTriggerKeydown(event) {
  if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
    event.preventDefault();
    openMenu();
  }
}

// Moves only between feature options; form fields retain their native editing and submission keys.
function handleMenuKeydown(event) {
  const currentOption = event.target.closest("[data-feature-path]");
  if (!currentOption) {
    return;
  }
  const options = optionButtons();
  const currentIndex = options.indexOf(currentOption);
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
    chooseOption(currentOption);
  }
}

// Commits a real mouse selection, then dismisses the completed interaction like the Project picker.
function handleMenuClick(event) {
  if (event.detail < 1) {
    return;
  }
  const option = event.target.closest("[data-feature-path]");
  if (option) {
    closeMenu(true);
    chooseOption(option);
  }
}

// Dismisses only when an actual mouse click lands outside both the trigger and body-level popover.
function handleDocumentClick(event) {
  if (event.detail > 0 && !event.target.closest(`#${MENU_ID}, #${TRIGGER_ID}`)) {
    closeMenu(false);
  }
}

// Prevents repeated creation, preserves failed input, and clears it only after canonical state succeeds.
async function handleFeatureCreate(event) {
  event.preventDefault();
  const input = byId("local-feature-name");
  const name = input.value.trim();
  if (!name || !projectAvailable || creating || !onFeatureCreate) {
    input.focus();
    return;
  }
  creating = true;
  let failed = false;
  renderCreationState();
  try {
    await onFeatureCreate(name);
    input.value = "";
    closeMenu(true);
  } catch {
    failed = true;
  } finally {
    creating = false;
    renderCreationState();
    if (failed) {
      input.focus();
    }
  }
}

// Rebuilds only the option list so the menu-top form and its draft input remain stable across Local state renders.
function render(localState) {
  const project = activeProject(localState);
  const features = project && Array.isArray(project.features) ? project.features : [];
  const menu = byId(MENU_ID);
  const list = byId("local-feature-picker-list");
  const wasOpen = !menu.hidden;
  const listScrollTop = wasOpen ? list.scrollTop : 0;
  const focusWasInList = list.contains(document.activeElement);
  const focusedOption = focusWasInList ? document.activeElement.closest("[data-feature-path]") : null;
  const focusedFeaturePath = focusedOption ? focusedOption.dataset.featurePath || "" : "";
  activeFeaturePath = localState.active_feature || "";
  projectAvailable = Boolean(project && project.exists);
  const activeFeature = features.find((feature) => feature.path === activeFeaturePath) || null;
  const label = activeFeature
    ? activeFeature.name
    : project ? (features.length ? "Select a feature" : "Create a feature") : "No project selected";
  byId("local-feature-picker-label").textContent = label;
  byId(TRIGGER_ID).disabled = !projectAvailable;
  renderCreationState();

  list.innerHTML = features.length ? features.map((feature) => {
    const selected = feature.path === activeFeaturePath;
    const versions = Array.isArray(feature.versions) ? feature.versions : [];
    const legacy = feature.legacy ? '<span class="status-pill warning">legacy</span>' : "";
    return `
      <button class="local-feature-picker-option${selected ? " selected" : ""}" type="button"
        role="menuitemradio" tabindex="-1" data-feature-path="${escapeHtml(feature.path)}"
        aria-checked="${selected}">
        <span><strong>${escapeHtml(feature.name)}</strong>
          <small>${versions.length} version${versions.length === 1 ? "" : "s"}</small></span>
        ${legacy}
      </button>
    `;
  }).join("") : `<div class="local-feature-picker-empty">${
    project ? "No features yet. Create the first feature above." : "Select an available project first."
  }</div>`;
  if (wasOpen) {
    const target = optionForPath(focusedFeaturePath) || optionForPath(activeFeaturePath) || optionButtons()[0];
    list.scrollTop = listScrollTop;
    if (focusWasInList && target) {
      target.focus({ preventScroll: true });
    }
  }
}

// Binds the injected popover once while allowing controller callbacks to refresh safely.
function bind(options) {
  onFeatureCreate = options && options.onFeatureCreate;
  onFeatureSelect = options && options.onFeatureSelect;
  injectMenu();
  if (bound) {
    return;
  }
  bound = true;
  byId(TRIGGER_ID).addEventListener("click", handleTriggerClick);
  byId(TRIGGER_ID).addEventListener("keydown", handleTriggerKeydown);
  byId("local-feature-form").addEventListener("submit", (event) => {
    handleFeatureCreate(event).catch(() => {});
  });
  byId(MENU_ID).addEventListener("click", handleMenuClick);
  byId(MENU_ID).addEventListener("keydown", handleMenuKeydown);
  document.addEventListener("click", handleDocumentClick);
}

window.GitDeskLocalFeaturePicker = { bind, render };
})();
