/*
  Existing-project metadata repair for category-folder moves completed outside the current app transaction.
*/

// Keeps category scanning separate from every create and import workflow.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const workspaceMode = window.GitDeskWorkspaceMode;

if (!nativeBridge || !renderHelpers || !workspaceMode) {
  throw new Error("GitDesk Local category scan dependencies did not load.");
}

const { appendActivity, setBusy, showMessage } = renderHelpers;
const { callNative } = nativeBridge;

// Returns the first saved parent favorite only as the native picker's starting location.
async function initialFavoritePath() {
  const current = await callNative("localProjectsState", {});
  const settings = current && current.settings ? current.settings : {};
  const favorites = Array.isArray(settings.local_parent_favorites)
    ? settings.local_parent_favorites
    : [];
  return favorites[0] || "";
}

// Repairs private metadata for uniquely matched saved projects without registering discovered folders.
async function scanCategories() {
  setBusy(true);
  showMessage("");
  try {
    const initialPath = await initialFavoritePath();
    const data = await callNative("scanLocalCategories", { initial_path: initialPath });
    if (data.cancelled) {
      return;
    }
    workspaceMode.applyLocalResponse(data);
    const scan = data.scan || {};
    const matchedCount = Number(scan.matched_project_count || 0);
    const remappedCount = Number(scan.remapped_count || 0);
    const message = `${matchedCount} saved project(s) matched; ${remappedCount} metadata path(s) repaired.`;
    showMessage(message);
    appendActivity(message);
  } catch (error) {
    const message = error.message || "Saved project metadata could not be repaired.";
    showMessage(message, true);
    appendActivity(message, true);
  } finally {
    setBusy(false);
  }
}

// Binds only the Local Projects header action after its renderer has injected the panel.
function bindCategoryScan() {
  const button = document.getElementById("scan-local-categories");
  if (button) {
    button.addEventListener("click", scanCategories);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bindCategoryScan);
} else {
  bindCategoryScan();
}
})();
