/*
  Static control adapters for the Local Mode create form and toolbar actions.
*/

// Keeps control-specific DOM work outside the Local Mode workflow controller.
(() => {
const renderHelpers = window.GitDeskRender;
const editorSettings = window.GitDeskEditorSettings;

if (!renderHelpers || !editorSettings) {
  throw new Error("GitDesk Local Mode control dependencies did not load.");
}

const { byId } = renderHelpers;

// Returns the selected Shared Resources from the Local Mode create form.
function selectedSharedResources() {
  return Array.from(document.querySelectorAll(".local-ai-check"))
    .filter((check) => check.checked && !check.disabled)
    .map((check) => check.value);
}

// Installs shared icons and accessible labels after Local Mode injects its controls.
function installIcons() {
  const icons = window.GitDeskIcons || {};
  const versionDetail = window.GitDeskLocalVersionDetail;
  document.querySelectorAll(".local-rename-icon").forEach((button) => {
    const label = button.id === "name-local-v1" ? "Rename v1 folder" : "Edit project details";
    button.setAttribute("aria-label", label);
    button.title = label;
    button.innerHTML = icons.rename || label;
  });

  const controls = [
    ["choose-local-project-icon-modal", "Choose project icon", "image", false],
    ["clear-local-project-icon", "Use automatic icon", "folder", false],
    ["duplicate-local-version", "Create new version", "newVersion", true],
    ["open-local-folder", "Open version folder", "folder", false],
    ["open-local-vscode", `Open version in ${editorSettings.name()}`, "vscode", false],
    ["open-local-notes", "Project Markdown notes", "note", false],
    ["sync-local-private-beta", "Sync selected version to Private Beta", "sync", false],
    ["open-sync-ignore", "Edit Sync Ignore", "ignore", false],
    ["open-local-compare", "Compare project versions", "compare", false],
    ["manage-local-shared-resources", "Manage Shared Resources", "resources", false],
  ];
  controls.forEach(([id, label, iconName, primary]) => {
    const button = byId(id);
    if (!button || !icons[iconName]) {
      throw new Error(`GitDesk icon dependency missing for ${id}.`);
    }
    button.classList.add("local-icon-button");
    if (primary) button.classList.add("local-icon-primary");
    button.setAttribute("aria-label", label);
    button.title = label;
    button.innerHTML = primary
      ? `${icons[iconName]}<span>${label}</span>`
      : icons[iconName];
  });
  const editorButton = byId("open-local-vscode");
  editorButton.dataset.editorAriaTemplate = "Open version in {editor}";
  editorButton.dataset.editorTooltipTemplate = "Open version in {editor}";
  editorSettings.refreshLabels(editorButton.parentElement);

  if (!versionDetail || !versionDetail.trashIcon) {
    throw new Error("GitDesk version-list trash icon dependency missing.");
  }
  const removeButton = byId("remove-active-local-project");
  removeButton.classList.add("local-icon-button", "local-icon-destructive", "local-version-delete");
  removeButton.setAttribute("aria-label", "Remove from GitDesk");
  removeButton.title = "Remove from GitDesk";
  removeButton.innerHTML = versionDetail.trashIcon();
}

window.GitDeskLocalControls = { installIcons, selectedSharedResources };
})();
