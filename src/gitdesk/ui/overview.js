(() => {
const renderHelpers = window.GitDeskRender;
const treeHelpers = window.GitDeskChangedFileTree;
const editorSettings = window.GitDeskEditorSettings;
if (!renderHelpers || !treeHelpers || !editorSettings) {
  throw new Error("GitDesk overview dependencies did not load.");
}
const { folderPaths, renderChangedFileTree, withoutIgnoredPath } = treeHelpers;
const { appendActivity, byId, renderRepository, setText, showMessage, showPanel } = renderHelpers;
let runActionRef = null; let repositoryPayloadRef = null; let renderBranchesRef = null;
const state = {
  status: null, selectedFiles: new Set(), selectedDiffPath: "", ignoreMode: false,
  selectionTouched: false, collapsedFolders: new Set(), pendingPush: false,
  fetchRequired: false, fetchAcknowledged: false, syncBehind: null, commitRunning: false, pullAvailable: false,
};
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
function payload(extraFields) {
  const basePayload = repositoryPayloadRef();
  Object.keys(extraFields || {}).forEach((key) => {
    basePayload[key] = extraFields[key];
  });
  return basePayload;
}
function selectedFilePaths() {
  const files = state.status && state.status.files ? state.status.files : [];
  return files.map((file) => file.path).filter((path) => state.selectedFiles.has(path));
}
function statusFilePaths(status) {
  const files = status && status.files ? status.files : [];
  return files.map((file) => file.path);
}
function commitMode() {
  if (state.fetchRequired) return "fetch";
  return state.pendingPush ? "push" : "commit";
}
function setCommitMode(mode) {
  const button = byId("commit-button");
  button.dataset.mode = mode;
  button.textContent = mode === "fetch" ? "Fetch" : mode === "push" ? "Push" : "Commit";
}
function updateCommitControls() {
  const selectedCount = selectedFilePaths().length;
  const noRepository = !(state.status && state.status.repository);
  const noSelection = selectedCount < 1;
  const needsMessage = selectedCount > 1 && !byId("commit-message").value.trim();
  const mode = commitMode();
  const blocksCommit = state.ignoreMode || noSelection || needsMessage;
  setCommitMode(mode);
  byId("commit-button").disabled = state.commitRunning || noRepository || (mode === "commit" && blocksCommit);
  byId("commit-push-button").disabled = state.commitRunning || noRepository || state.fetchRequired || blocksCommit;
  byId("commit-push-button").title = state.fetchRequired ? "Fetch remote changes before commit and push." : "";
  byId("select-all-files").disabled = state.commitRunning || noRepository || state.ignoreMode;
  byId("clear-file-selection").disabled = state.commitRunning || noRepository || state.ignoreMode;
  byId("push-button").disabled = state.commitRunning || noRepository || !state.pendingPush;
  byId("pull-button").disabled = noRepository || !state.pullAvailable;
  byId("fetch-button").disabled = noRepository;
}
function updateSyncIndicator(sync) {
  const behind = sync ? Number(sync.behind || 0) : 0;
  if (!behind) {
    state.fetchAcknowledged = false;
  } else if (state.syncBehind === null || behind > state.syncBehind) {
    state.fetchAcknowledged = false;
  }
  state.syncBehind = behind;
  state.pullAvailable = Boolean(sync && sync.has_upstream);
  state.fetchRequired = behind > 0 && !state.fetchAcknowledged;
  ["pull-button", "fetch-button"].forEach((id) => {
    const button = byId(id);
    button.classList.toggle("has-remote-update", behind > 0);
    button.title = id === "pull-button" && !state.pullAvailable
      ? "Push this branch first, or fetch a branch created on the remote."
      : behind > 0 ? `${behind} remote commit(s) available` : "";
  });
  updateCommitControls();
}
async function refreshSyncStatus() {
  if (!state.status || !state.status.repository) {
    updateSyncIndicator(null);
    return;
  }
  try {
    const sync = await runActionRef("syncStatus", payload(), "", { quiet: true });
    updateSyncIndicator(sync);
  } catch (error) {
    updateSyncIndicator(null);
  }
}
function renderRepositoryActions(message) {
  setText("diff-title", "Repository");
  setText("diff-summary", message || "No file selected");
  byId("diff-viewer").innerHTML = `
    <div class="repo-action-panel">
      <button class="repo-action-button" type="button" data-action="openInFileManager">
        Open in Finder
      </button>
      <button class="repo-action-button" type="button" data-action="openInVSCode"
        data-editor-label-template="Open in {editor}" data-editor-aria-template="Open repository in {editor}"
        data-editor-tooltip-template="Open repository in {editor}">
        Open in ${editorSettings.name()}
      </button>
      <button class="repo-action-button" type="button" data-action="openRepositoryOnGitHub">
        Open repo in GitHub.com
      </button>
      <div id="ai-skill-overview-panel"></div>
    </div>
  `;
  editorSettings.refreshLabels(byId("diff-viewer"));
  if (window.GitDeskAISkills) {
    window.GitDeskAISkills.renderOverviewPanel();
  }
}
function diffLineClass(line) {
  if (line.startsWith("@@")) return "diff-line diff-hunk";
  if (line.startsWith("diff --git") || line.startsWith("index ")) return "diff-line diff-meta";
  if (line.startsWith("---") || line.startsWith("+++")) return "diff-line diff-meta";
  if (line.startsWith("+")) return "diff-line diff-add";
  if (line.startsWith("-")) return "diff-line diff-remove";
  return "diff-line";
}
function renderDiff(diffPayload) {
  const diffText = diffPayload.diff || "";
  setText("diff-title", diffPayload.path || "Diff");
  setText("diff-summary", diffText ? "Unified diff" : "No diff for this file");
  if (!diffText) {
    byId("diff-viewer").innerHTML = '<div class="empty-state">No diff is available for this file</div>';
    return;
  }
  byId("diff-viewer").innerHTML = `
    <pre class="diff-code">${diffText.split("\n").map((line) => (
      `<span class="${diffLineClass(line)}">${escapeHtml(line || " ")}</span>`
    )).join("")}</pre>
  `;
}
function renderChangedFiles() {
  const files = state.status && state.status.files ? state.status.files : [];
  const list = byId("changed-files");
  const summary = state.status && state.status.summary ? state.status.summary : {};
  setText("status-counts", `${summary.changed || 0} changed files`);
  if (!files.length) {
    list.innerHTML = "";
    renderRepositoryActions("Working tree clean");
    updateCommitControls();
    return;
  }
  list.innerHTML = renderChangedFileTree({
    files,
    selectedFiles: state.selectedFiles,
    selectedDiffPath: state.selectedDiffPath,
    ignoreMode: state.ignoreMode,
    collapsedFolders: state.collapsedFolders,
  });
  if (!state.selectedDiffPath) {
    renderRepositoryActions("Select a changed file to inspect its diff");
  }
  updateCommitControls();
}
function applyStatus(status) {
  const previousSelection = selectedFilePaths();
  state.status = status;
  renderRepository(status && status.repository);
  const currentPaths = new Set(statusFilePaths(status));
  const currentFolders = folderPaths(status && status.files ? status.files : []);
  if (state.selectionTouched) {
    state.selectedFiles = new Set(previousSelection.filter((path) => currentPaths.has(path)));
  } else {
    state.selectedFiles = new Set(currentPaths);
  }
  state.collapsedFolders = new Set(Array.from(state.collapsedFolders).filter((path) => currentFolders.has(path)));
  if (state.selectedDiffPath && !currentPaths.has(state.selectedDiffPath)) {
    state.selectedDiffPath = "";
  }
  renderChangedFiles();
  refreshSyncStatus().catch(() => {});
}
function reset() {
  state.status = null; state.selectedFiles.clear();
  state.selectedDiffPath = ""; state.ignoreMode = false;
  state.selectionTouched = false; state.collapsedFolders.clear();
  state.pendingPush = false; state.commitRunning = false;
  state.fetchRequired = false; state.fetchAcknowledged = false;
  state.syncBehind = null; state.pullAvailable = false;
  renderRepository(null);
  byId("toggle-git-ignore").classList.remove("active");
  updateSyncIndicator(null);
  renderChangedFiles();
}
async function loadFileDiff(filePath) {
  state.selectedDiffPath = filePath;
  renderChangedFiles();
  const diff = await runActionRef("fileDiff", payload({ file_path: filePath }));
  renderDiff(diff);
}
function handleFileSelection(event) {
  if (event.target.classList.contains("ignore-checkbox")) {
    ignoreFile(event.target.value).catch(() => {});
    return;
  }
  if (!event.target.classList.contains("file-checkbox")) {
    return;
  }
  state.selectionTouched = true;
  if (event.target.checked) {
    state.selectedFiles.add(event.target.value);
    updateCommitControls();
    return;
  }
  state.selectedFiles.delete(event.target.value);
  updateCommitControls();
}
function handleFileClick(event) {
  const toggle = event.target.closest(".folder-toggle");
  if (toggle) {
    toggleFolder(toggle.dataset.path || "");
    return;
  }
  const button = event.target.closest(".file-diff-button");
  if (button) {
    loadFileDiff(button.dataset.path || "");
  }
}
function toggleFolder(path) {
  if (!path) return;
  if (state.collapsedFolders.has(path)) {
    state.collapsedFolders.delete(path);
  } else {
    state.collapsedFolders.add(path);
  }
  renderChangedFiles();
}
function toggleIgnoreMode() {
  state.ignoreMode = !state.ignoreMode;
  byId("toggle-git-ignore").classList.toggle("active", state.ignoreMode);
  renderChangedFiles();
}
async function ignoreFile(filePath) {
  const data = await runActionRef("ignoreFile", payload({ file_path: filePath }), "Added to .gitignore");
  state.selectionTouched = true;
  state.selectedFiles = withoutIgnoredPath(state.selectedFiles, filePath);
  applyStatus(data.status);
}
function selectAllFiles() {
  if (state.ignoreMode) return;
  const files = state.status && state.status.files ? state.status.files : [];
  state.selectionTouched = true;
  state.selectedFiles = new Set(files.map((file) => file.path));
  renderChangedFiles();
}
function clearFileSelection() {
  if (state.ignoreMode) return;
  state.selectionTouched = true;
  state.selectedFiles.clear();
  renderChangedFiles();
}
function commitMessageForSelection() {
  const selected = selectedFilePaths();
  const message = byId("commit-message").value.trim();
  if (message) return message;
  if (!selected.length) {
    throw new Error("Select at least one changed file to commit.");
  }
  if (selected.length === 1) return `Update ${selected[0]}`;
  throw new Error("Commit message is required when more than one file is selected.");
}
async function commitSelected(pushAfter) {
  if (state.commitRunning) return;
  if (state.fetchRequired) {
    await fetchBranch();
    return;
  }
  let message = "";
  try {
    message = commitMessageForSelection();
  } catch (error) {
    showMessage(error.message || "Commit message is required.", true);
    return;
  }
  let data;
  state.commitRunning = true; updateCommitControls();
  try {
    data = await runActionRef("commit", payload({
      message,
      files: selectedFilePaths(),
      push: pushAfter,
    }), "");
  } catch (error) {
    if (error.code === "COMMIT_PUSH_FAILED" && error.details && error.details.status) {
      byId("commit-message").value = "";
      state.selectedFiles.clear();
      state.selectionTouched = false;
      state.selectedDiffPath = "";
      state.pendingPush = true;
      applyStatus(error.details.status);
    }
    return;
  } finally {
    state.commitRunning = false;
    updateCommitControls();
  }
  if (data.noop) {
    applyStatus(data.status);
    return;
  }
  appendActivity(pushAfter ? "Commit pushed" : "Commit created");
  byId("commit-message").value = "";
  state.selectedFiles.clear();
  state.selectionTouched = false;
  state.selectedDiffPath = "";
  state.pendingPush = !pushAfter;
  applyStatus(data.status);
  if (pushAfter && window.GitDeskPages) {
    window.GitDeskPages.notePushedCommit(data.hexsha || "");
  }
  if (pushAfter && window.GitDeskActions) {
    window.GitDeskActions.refreshAfterPush(data.hexsha || "");
  }
}
async function runPrimaryCommitAction() {
  if (state.fetchRequired) {
    await fetchBranch();
    return;
  }
  if (state.pendingPush) {
    await pushBranch();
    return;
  }
  await commitSelected(false);
}
async function pushBranch() {
  const data = await runActionRef("push", payload(), "Branch pushed");
  state.pendingPush = false;
  if (data.status) {
    applyStatus(data.status);
  }
  if (window.GitDeskPages) {
    window.GitDeskPages.notePushedCommit("");
  }
  if (window.GitDeskActions) {
    window.GitDeskActions.refreshAfterPush(data.head_sha || "");
  }
}
async function pullBranch() {
  const data = await runActionRef("pull", payload(), "Branch pulled");
  applyStatus(data.status);
}
async function fetchBranch() {
  const data = await runActionRef("fetch", payload(), "Fetched from origin");
  state.fetchAcknowledged = true;
  state.fetchRequired = false;
  updateCommitControls();
  applyStatus(data.status);
  renderBranchesRef(data.branches);
}
async function runRepositoryAction(action) {
  const labels = {
    openInFileManager: "Repository opened in file manager",
    openInVSCode: `Repository opened in ${editorSettings.name()}`,
    openRepositoryOnGitHub: "Repository opened in GitHub.com",
  };
  await runActionRef(action, payload(), labels[action]);
}
function handleRepoAction(event) {
  const button = event.target.closest(".repo-action-button");
  if (button) {
    runRepositoryAction(button.dataset.action || "");
  }
}
function bind(options) {
  runActionRef = options.runAction;
  repositoryPayloadRef = options.repositoryPayload;
  renderBranchesRef = options.renderBranches;
  byId("changed-files").addEventListener("change", handleFileSelection);
  byId("changed-files").addEventListener("click", handleFileClick);
  byId("diff-viewer").addEventListener("click", handleRepoAction);
  byId("toggle-git-ignore").addEventListener("click", toggleIgnoreMode);
  byId("select-all-files").addEventListener("click", selectAllFiles);
  byId("clear-file-selection").addEventListener("click", clearFileSelection);
  byId("commit-message").addEventListener("input", updateCommitControls);
  byId("commit-button").addEventListener("click", () => runPrimaryCommitAction());
  byId("commit-push-button").addEventListener("click", () => commitSelected(true));
  byId("push-button").addEventListener("click", pushBranch);
  byId("pull-button").addEventListener("click", pullBranch);
  byId("fetch-button").addEventListener("click", fetchBranch);
}
window.GitDeskOverview = {
  applyStatus,
  bind,
  reset,
  show() {
    showPanel("overview");
  },
};
})();
