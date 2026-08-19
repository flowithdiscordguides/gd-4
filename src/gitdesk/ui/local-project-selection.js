/*
  Fast acknowledged Local project selection with a guarded read-only hierarchy refresh.
*/

// Keeps project-switch request ownership outside the main Local Mode controller.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const localProjectIdentity = window.GitDeskLocalProjectIdentity;

if (!nativeBridge || !renderHelpers || !localProjectIdentity) {
  throw new Error("GitDesk Local project selection dependencies did not load.");
}

const { appendActivity, showMessage } = renderHelpers;
const { callNative } = nativeBridge;

// Creates one controller whose pending and generation state cannot leak into other Local actions.
function create(options) {
  const state = options.state;
  let pending = false;
  let generation = 0;

  // Derives the normal initial selection from the already-rendered authoritative project snapshot.
  function cachedSelection(path) {
    const project = (state.local.projects || []).find((item) => item.path === path);
    const features = project && Array.isArray(project.features) ? project.features : [];
    const feature = features.find((item) => item.name === "01 init") || features[0] || null;
    const versions = feature && Array.isArray(feature.versions) ? feature.versions : [];
    return {
      project_path: path,
      feature_path: feature ? feature.path || "" : "",
      version_path: versions.length ? versions[versions.length - 1].path || "" : "",
    };
  }

  // Merges one project response while preserving cached trees for every unrelated saved project.
  function applyResponse(data) {
    const selection = data.local_selection || {};
    const selectedProject = selection.project || (state.local.projects || []).find(
      (project) => project.path === selection.active_project,
    );
    if (!selectedProject || !selectedProject.path) {
      throw new Error("Local project selection response is incomplete.");
    }
    let selectedProjectFound = false;
    const projects = (state.local.projects || []).map((project) => {
      if (project.path === selectedProject.path) {
        selectedProjectFound = true;
        return selectedProject;
      }
      return { ...project, icon_name: "", icon_data_url: "", icon_source: "" };
    });
    if (!selectedProjectFound) {
      projects.push(selectedProject);
    }
    state.settings = data.settings || {};
    state.local = {
      ...state.local,
      mode: selection.mode,
      projects,
      active_project: selection.active_project || "",
      active_feature: selection.active_feature || "",
      active_version: selection.active_version || "",
      cleanup_paths: selection.cleanup_paths || [],
    };
    options.render();
  }

  // Applies a refreshed hierarchy only while it still belongs to the latest acknowledged selection.
  async function refresh(path, requestGeneration) {
    try {
      const data = await callNative("localProjectSelectionState", { project_path: path });
      if (data.stale || requestGeneration !== generation || state.local.active_project !== path) {
        return;
      }
      applyResponse(data);
    } catch (error) {
      if (requestGeneration !== generation || state.local.active_project !== path) {
        return;
      }
      const message = error.message || "The selected Local project could not be refreshed.";
      console.error("Selected Local project refresh failed", error);
      showMessage(message, true);
      appendActivity(message, true);
    }
  }

  // Acknowledges cached exact paths before the complete selected hierarchy is refreshed.
  async function select(path) {
    if (pending || !path || path === state.local.active_project) {
      return;
    }
    pending = true;
    generation += 1;
    const requestGeneration = generation;
    localProjectIdentity.setPending(true);
    try {
      const data = await options.runAction(
        "selectLocalProject",
        cachedSelection(path),
        "Local project selected",
      );
      applyResponse(data);
    } finally {
      pending = false;
      localProjectIdentity.setPending(false);
    }
    refresh(path, requestGeneration).catch(() => {});
  }

  return { applyResponse, select };
}

window.GitDeskLocalProjectSelection = { create };
})();
