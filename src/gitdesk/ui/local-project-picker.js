/*
  Categorized downward-opening menu for selecting or opening saved Local Mode projects.
*/

// Owns popup geometry and row actions while the identity module supplies controller callbacks.
(() => {
const renderHelpers = window.GitDeskRender;
const editorSettings = window.GitDeskEditorSettings;

if (!renderHelpers || !editorSettings) {
  throw new Error("GitDesk Local project picker dependencies did not load.");
}

const { byId } = renderHelpers;

// Stable dimensions keep the portal menu usable without allowing it to dominate compact Local Mode controls.
const MENU_ID = "local-project-picker-menu";
const VIEWPORT_MARGIN = 12;
const MENU_TRIGGER_GAP = 6;
const MENU_MIN_WIDTH = 220;
const MENU_BASE_MAX_WIDTH = 360;
const MENU_EXTRA_WIDTH = 48;
const MENU_BASE_MAX_HEIGHT = 320;
const ADDITIONAL_OPTION_COUNT = 5;
let onProjectSelect = null;
let onOpenCurrentVersion = null;
let activeProjectPath = "";
let bound = false;

// Escapes backend-owned labels and paths before rendering menu markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Compares category and project labels case-insensitively while keeping numbered names naturally ordered.
function compareLabels(left, right) {
  return String(left || "").localeCompare(String(right || ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

// Returns alphabetized categories whose projects are independently alphabetized for stable scanning.
function categorizedProjects(projects) {
  const groups = new Map();
  projects.forEach((project) => {
    const category = String(project.category || "").trim() || "Uncategorized";
    if (!groups.has(category)) {
      groups.set(category, []);
    }
    groups.get(category).push(project);
  });
  return Array.from(groups, ([category, groupedProjects]) => ({
    category,
    projects: groupedProjects.slice().sort((left, right) => compareLabels(left.name, right.name)),
  })).sort((left, right) => compareLabels(left.category, right.category));
}

// Returns the latest version in the latest project feature that contains physical versions.
function currentVersionPath(project) {
  const features = project && Array.isArray(project.features) ? project.features : [];
  // Feature and version payloads are already ordered, so reverse traversal finds current work without guessing.
  for (let featureIndex = features.length - 1; featureIndex >= 0; featureIndex -= 1) {
    const versions = Array.isArray(features[featureIndex].versions) ? features[featureIndex].versions : [];
    if (versions.length) {
      return versions[versions.length - 1].path || "";
    }
  }
  return "";
}

// Creates the portal once so ancestor card overflow cannot clip the project menu.
function injectMenu() {
  if (!document.getElementById(MENU_ID)) {
    document.body.insertAdjacentHTML("beforeend", `
      <div id="${MENU_ID}" class="local-project-picker-menu" role="menu"
        aria-label="Saved local projects" hidden></div>
    `);
  }
}

// Returns all selectable project options in their current alphabetical visual order.
function optionButtons() {
  return Array.from(byId(MENU_ID).querySelectorAll("[data-project-path]"));
}

// Resolves one rendered project option without relying on a selector-escaped filesystem path.
function optionForPath(path) {
  return optionButtons().find((option) => option.dataset.projectPath === path) || null;
}

// Constrains portal coordinates and scrolling to a safe numeric interval.
function clamp(value, minimum, maximum) {
  return Math.min(Math.max(value, minimum), Math.max(minimum, maximum));
}

// Preserves the baseline top and left anchors, then expands only toward the right and bottom.
function positionMenu(target) {
  const trigger = byId("local-project-picker-trigger");
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
  // Avoid `slice(-0)`, which would incorrectly include every earlier project when five lower rows already exist.
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

// Closes the portal and optionally returns keyboard focus to its trigger.
function closeMenu(restoreFocus = false) {
  const menu = document.getElementById(MENU_ID);
  const trigger = document.getElementById("local-project-picker-trigger");
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

// Prevents overlapping selection writes while the native bridge acknowledges the chosen project.
function setPending(isPending) {
  const trigger = byId("local-project-picker-trigger");
  trigger.disabled = Boolean(isPending) || !optionButtons().length;
  trigger.setAttribute("aria-busy", String(Boolean(isPending)));
}

// Opens below the trigger and focuses the current project, or the first project when none is active.
function openMenu() {
  const trigger = byId("local-project-picker-trigger");
  if (trigger.disabled) {
    return;
  }
  trigger.setAttribute("aria-expanded", "true");
  const options = optionButtons();
  const target = optionForPath(activeProjectPath) || options[0];
  positionMenu(target);
  if (target) {
    target.focus({ preventScroll: true });
  }
}

// Commits one option through the existing controller callback without changing state optimistically.
function chooseOption(option) {
  const path = option ? option.dataset.projectPath || "" : "";
  if (path && path !== activeProjectPath && onProjectSelect) {
    onProjectSelect(path);
  }
}

// Opens one listing's resolved current version without changing the active project selection.
function openCurrentVersion(button) {
  const versionPath = button ? button.dataset.versionPath || "" : "";
  if (!versionPath || !onOpenCurrentVersion) {
    return;
  }
  onOpenCurrentVersion(versionPath);
}

// Toggles the portal only for a real mouse click, never a synthesized keyboard click.
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

// Opens from standard popup-menu keys and leaves Tab available for natural focus navigation.
function handleTriggerKeydown(event) {
  if (["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) {
    event.preventDefault();
    openMenu();
  }
}

// Moves through project rows and exposes each row's editor action without mixing the two commands.
function handleMenuKeydown(event) {
  const options = optionButtons();
  const activeElement = document.activeElement;
  const currentRow = activeElement.closest(".local-project-picker-option-row");
  const currentOption = currentRow ? currentRow.querySelector("[data-project-path]") : null;
  const currentAction = activeElement.closest("[data-version-path]");
  const currentIndex = options.indexOf(currentOption);
  let nextIndex = currentIndex;
  if (event.key === "ArrowDown") nextIndex = Math.min(currentIndex + 1, options.length - 1);
  if (event.key === "ArrowUp") nextIndex = Math.max(currentIndex - 1, 0);
  if (event.key === "Home") nextIndex = 0;
  if (event.key === "End") nextIndex = options.length - 1;
  if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    if (options[nextIndex]) options[nextIndex].focus();
  } else if (event.key === "ArrowRight" && currentOption) {
    const action = currentRow.querySelector("[data-version-path]:not(:disabled)");
    if (action) {
      event.preventDefault();
      action.focus();
    }
  } else if (event.key === "ArrowLeft" && currentAction) {
    event.preventDefault();
    currentOption.focus();
  } else if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    if (currentAction) {
      openCurrentVersion(currentAction);
    } else {
      chooseOption(currentOption);
    }
  }
}

// Routes a real mouse click to its row command, then dismisses the completed interaction.
function handleMenuClick(event) {
  if (event.detail < 1) {
    return;
  }
  const action = event.target.closest("[data-version-path]");
  if (action) {
    closeMenu(true);
    openCurrentVersion(action);
    return;
  }
  const option = event.target.closest("[data-project-path]");
  if (option) {
    closeMenu(true);
    chooseOption(option);
  }
}

// Dismisses the portal only after a real mouse click lands outside the menu and trigger.
function handleDocumentClick(event) {
  if (event.detail > 0 && !event.target.closest(`#${MENU_ID}, #local-project-picker-trigger`)) {
    closeMenu(false);
  }
}

// Renders sorted groups and synchronizes the trigger label with canonical Local Mode state.
function render(projects, selectedPath) {
  const menu = byId(MENU_ID);
  const wasOpen = !menu.hidden;
  const menuScrollTop = wasOpen ? menu.scrollTop : 0;
  const focusWasInMenu = menu.contains(document.activeElement);
  const focusedRow = focusWasInMenu
    ? document.activeElement.closest(".local-project-picker-option-row")
    : null;
  const focusedOption = focusedRow ? focusedRow.querySelector("[data-project-path]") : null;
  const focusedProjectPath = focusedOption ? focusedOption.dataset.projectPath || "" : "";
  const editorActionWasFocused = Boolean(
    focusWasInMenu && document.activeElement.closest("[data-version-path]"),
  );
  const records = Array.isArray(projects) ? projects : [];
  activeProjectPath = selectedPath || "";
  const activeProject = records.find((project) => project.path === activeProjectPath) || null;
  const trigger = byId("local-project-picker-trigger");
  const triggerLabel = activeProject
    ? `${activeProject.name}${activeProject.exists ? "" : " — missing"}`
    : records.length ? "Select a project" : "No local projects";
  byId("local-project-picker-label").textContent = triggerLabel;
  trigger.disabled = !records.length;

  byId(MENU_ID).innerHTML = categorizedProjects(records).map((group, groupIndex) => {
    const labelId = `local-project-picker-category-${groupIndex}`;
    const options = group.projects.map((project) => {
      const selected = project.path === activeProjectPath;
      const missing = project.exists ? "" : '<small class="local-project-picker-missing">Missing</small>';
      const versionPath = currentVersionPath(project);
      const disabled = versionPath ? "" : "disabled";
      const projectName = escapeHtml(project.name);
      return `
        <div class="local-project-picker-option-row" role="none">
          <button type="button" role="menuitemradio" tabindex="-1"
            data-project-path="${escapeHtml(project.path)}" aria-checked="${selected}"
            class="${selected ? "selected" : ""}"><span>${projectName}</span>${missing}</button>
          <button class="local-project-picker-vscode" type="button" role="menuitem" tabindex="-1"
            data-version-path="${escapeHtml(versionPath)}"
            data-editor-aria-template="Open current version of ${projectName} in {editor}"
            data-editor-tooltip-template="Open current version in {editor}" ${disabled}>
            ${editorSettings.name()}</button>
        </div>
      `;
    }).join("");
    return `
      <div class="local-project-picker-category" role="group" aria-labelledby="${labelId}">
        <div id="${labelId}" class="local-project-picker-category-label">${escapeHtml(group.category)}</div>
        ${options}
      </div>
    `;
  }).join("");
  editorSettings.refreshLabels(byId(MENU_ID));
  if (wasOpen) {
    const target = optionForPath(focusedProjectPath) || optionForPath(activeProjectPath) || optionButtons()[0];
    // An open menu belongs to the user: data refresh may rebuild it but must not recenter or reposition it.
    menu.scrollTop = menuScrollTop;
    if (focusWasInMenu && target) {
      const editorAction = editorActionWasFocused
        ? target.parentElement.querySelector("[data-version-path]:not(:disabled)")
        : null;
      (editorAction || target).focus({ preventScroll: true });
    }
  }
}

// Binds the injected trigger and portal once while allowing controller callbacks to refresh.
function bind(options) {
  onProjectSelect = options && options.onProjectSelect;
  onOpenCurrentVersion = options && options.onOpenCurrentVersion;
  injectMenu();
  if (bound) {
    return;
  }
  bound = true;
  byId("local-project-picker-trigger").addEventListener("click", handleTriggerClick);
  byId("local-project-picker-trigger").addEventListener("keydown", handleTriggerKeydown);
  byId(MENU_ID).addEventListener("click", handleMenuClick);
  byId(MENU_ID).addEventListener("keydown", handleMenuKeydown);
  document.addEventListener("click", handleDocumentClick);
}

window.GitDeskLocalProjectPicker = { bind, categorizedProjects, currentVersionPath, render, setPending };
})();
