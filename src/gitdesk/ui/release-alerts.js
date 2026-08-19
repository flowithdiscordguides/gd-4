/*
  Release and build notification dots for tag-triggered packaging workflows.
*/

// Keeps tab notification state isolated from Actions, Pages, and Releases workflow modules.
(() => {
const WATCH_WINDOW_MS = 5 * 60 * 1000;
const state = {
  watching: false,
  startedAt: 0,
  tag: "",
  releaseReady: false,
};

// Returns one sidebar tab button by its data-tab value.
function tabButton(tabName) {
  if (tabName === "history") {
    return document.getElementById("history-button");
  }
  return document.querySelector(`.tab-button[data-tab="${tabName}"]`);
}

// Ensures a tab has one reusable notification dot without changing its icon markup.
function tabDot(tabName) {
  const button = tabButton(tabName);
  if (!button) {
    return null;
  }
  if (!button.dataset.baseTitle) {
    button.dataset.baseTitle = button.title || button.getAttribute("aria-label")
      || button.textContent.trim() || tabName;
  }
  let dot = button.querySelector(".tab-alert-dot");
  if (!dot) {
    dot = document.createElement("span");
    dot.className = "tab-alert-dot";
    dot.setAttribute("aria-hidden", "true");
    button.append(dot);
  }
  return dot;
}

// Applies or clears one tab dot state and preserves the original tooltip as the base label.
function setTabAlert(tabName, status, message) {
  const button = tabButton(tabName);
  const dot = tabDot(tabName);
  if (!button || !dot) {
    return;
  }
  if (!status) {
    dot.hidden = true;
    dot.className = "tab-alert-dot";
    button.classList.remove("has-success-notification");
    button.title = button.dataset.baseTitle;
    return;
  }
  dot.hidden = false;
  dot.className = `tab-alert-dot ${status}`;
  button.classList.toggle("has-success-notification", status === "success");
  button.title = message || button.dataset.baseTitle;
}

// Reads a GitHub timestamp as milliseconds so tag-triggered watches can ignore stale runs.
function timestamp(value) {
  const parsed = Date.parse(value || "");
  return Number.isNaN(parsed) ? 0 : parsed;
}

// Returns true while GitHub still reports a workflow run as queued or in progress.
function isActiveRun(run) {
  return run && run.status && run.status !== "completed";
}

// Returns true when a completed workflow run finished successfully.
function isSuccessfulRun(run) {
  return run && run.status === "completed" && run.conclusion === "success";
}

// Returns true when a completed workflow run reached a non-success conclusion.
function isFailedRun(run) {
  return run && run.status === "completed" && run.conclusion && run.conclusion !== "success";
}

// Selects runs that plausibly belong to the latest tag push watch window.
function watchedRuns(runs) {
  const cutoff = state.startedAt - WATCH_WINDOW_MS;
  return runs.filter((run) => {
    const started = timestamp(run.run_started_at) || timestamp(run.created_at);
    return started >= cutoff;
  });
}

// Starts the tag-push watch with a build-starting dot over Actions.
function noteTagPushed(tag) {
  state.watching = true;
  state.startedAt = Date.now();
  state.tag = String(tag || "");
  state.releaseReady = false;
  setTabAlert("actions", "building", `Build starting for ${state.tag || "release tag"}`);
  setTabAlert("releases", "", "");
}

// Uses live Actions data to promote the tab dots through building, success, release-ready, or failed.
function syncWorkflowRuns(runList) {
  const runs = Array.isArray(runList) ? runList : [];
  const relevantRuns = state.watching ? watchedRuns(runs) : runs;
  const activeRuns = relevantRuns.filter(isActiveRun);
  if (activeRuns.length) {
    setTabAlert("actions", "building", `${activeRuns.length} build${activeRuns.length === 1 ? "" : "s"} running`);
    return;
  }
  if (!state.watching || !relevantRuns.length) {
    return;
  }
  if (relevantRuns.every(isSuccessfulRun)) {
    state.watching = false;
    state.releaseReady = true;
    setTabAlert("actions", "success", "Build completed successfully");
    setTabAlert("releases", "release-ready", "Build succeeded; review the draft release");
    return;
  }
  if (relevantRuns.some(isFailedRun)) {
    state.watching = false;
    state.releaseReady = false;
    setTabAlert("actions", "danger", "Build failed");
    setTabAlert("releases", "", "");
  }
}

// Clears the release-ready hint after the Releases page has been opened or refreshed.
function clearReleaseReady() {
  state.releaseReady = false;
  setTabAlert("releases", "", "");
}

// Marks the History button when a push should make fresh commits available there.
function noteHistoryReady() {
  setTabAlert("history", "success", "New pushed commit available in History");
}

// Clears the History hint after a successful refresh has shown the pushed commit data.
function clearHistoryReady() {
  setTabAlert("history", "", "");
}

// Lets the Actions poller keep checking while GitHub creates the run record for a fresh tag.
function isWatchingBuild() {
  return state.watching;
}

window.GitDeskReleaseAlerts = {
  clearHistoryReady,
  clearReleaseReady,
  isWatchingBuild,
  noteHistoryReady,
  noteTagPushed,
  syncWorkflowRuns,
};
})();
