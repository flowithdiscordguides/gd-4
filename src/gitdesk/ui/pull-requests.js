/*
  Repo Mode Pull Request controller using selected-repository owner-routed native actions.
*/

// Coordinates list/detail/mutation state while the view module owns all generated markup.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const repositoryManager = window.GitDeskRepositories;
const pullRequestUI = window.GitDeskPullRequestUI;

if (!nativeBridge || !renderHelpers || !repositoryManager || !pullRequestUI) {
  throw new Error("GitDesk Pull Request dependencies did not load.");
}

const { callNative } = nativeBridge;
const { appendActivity, byId, setBusy, showMessage } = renderHelpers;
const state = { list: null, selectedNumber: 0, detail: null, busy: false };

// Returns the selected managed repository and exact PAT profile context.
function repositoryPayload(extraFields = {}) {
  return { ...repositoryManager.payload(), ...extraFields };
}

// Runs one native action with consistent visible feedback and no unhandled rejection.
async function runAction(action, payload, successMessage) {
  if (state.busy) throw new Error("A Pull Request action is already running.");
  state.busy = true;
  setBusy(true);
  showMessage("");
  try {
    const data = await callNative(action, payload);
    if (successMessage) appendActivity(successMessage);
    return data;
  } catch (error) {
    const message = error.message || "Pull Request operation failed.";
    console.error(`Pull Request action failed: ${action}`, error);
    showMessage(message, true);
    appendActivity(message, true);
    throw error;
  } finally {
    state.busy = false;
    setBusy(false);
  }
}

// Loads open Pull Requests and preserves selection only while that PR remains open.
async function refreshList(selectNumber = state.selectedNumber) {
  const data = await runAction("listPullRequests", repositoryPayload(), "");
  state.list = data;
  const exists = (data.pull_requests || []).some((pull) => pull.number === selectNumber);
  state.selectedNumber = exists ? selectNumber : 0;
  pullRequestUI.renderList(data, state.selectedNumber);
  if (state.selectedNumber) {
    await loadDetail(state.selectedNumber);
  } else {
    state.detail = null;
    byId("pull-request-detail").innerHTML =
      '<div class="empty-state">Select a Pull Request to inspect files, commits, and review activity.</div>';
  }
}

// Loads one complete PR review context and re-highlights its list row.
async function loadDetail(number) {
  const detail = await runAction(
    "pullRequestDetail",
    repositoryPayload({ number }),
    "",
  );
  state.selectedNumber = Number(number);
  state.detail = detail;
  pullRequestUI.renderList(state.list || { pull_requests: [] }, state.selectedNumber);
  pullRequestUI.renderDetail(detail);
}

// Opens the creation form with GitHub's current default branch prefilled as base.
function openCreateDialog() {
  byId("pull-request-create-form").reset();
  byId("pull-request-base").value = state.list ? state.list.default_branch || "" : "";
  byId("pull-request-create-dialog").hidden = false;
  byId("pull-request-title-input").focus();
}

// Closes the creation form without changing current list or detail state.
function closeCreateDialog() {
  byId("pull-request-create-dialog").hidden = true;
}

// Creates one PR, refreshes the list, and opens the resulting detail.
async function createPullRequest(event) {
  event.preventDefault();
  const data = await runAction("createPullRequest", repositoryPayload({
    title: byId("pull-request-title-input").value,
    head: byId("pull-request-head").value,
    base: byId("pull-request-base").value,
    body: byId("pull-request-body").value,
    draft: byId("pull-request-draft").checked,
  }), "Pull Request created");
  closeCreateDialog();
  await refreshList(data.pull_request.number);
}

// Adds a conversation comment and reloads detail so GitHub remains authoritative.
async function commentPullRequest(event) {
  event.preventDefault();
  await runAction("commentPullRequest", repositoryPayload({
    number: state.selectedNumber,
    body: byId("pull-request-comment").value,
  }), "Pull Request comment added");
  await loadDetail(state.selectedNumber);
}

// Submits the exact decision represented by the clicked review button.
async function reviewPullRequest(event) {
  event.preventDefault();
  const button = event.submitter;
  const reviewEvent = button ? button.dataset.reviewEvent || "" : "";
  await runAction("reviewPullRequest", repositoryPayload({
    number: state.selectedNumber,
    event: reviewEvent,
    body: byId("pull-request-review-body").value,
  }), "Pull Request review submitted");
  await loadDetail(state.selectedNumber);
}

// Merges through GitHub and refreshes the open list so merged work disappears naturally.
async function mergePullRequest(event) {
  event.preventDefault();
  const data = await runAction("mergePullRequest", repositoryPayload({
    number: state.selectedNumber,
    merge_method: byId("pull-request-merge-method").value,
  }), "Pull Request merge requested");
  showMessage(data.message || (data.merged ? "Pull Request merged." : "Pull Request was not merged."));
  await refreshList(0);
}

// Routes dynamically rendered list and detail forms through one stable page container.
function handlePageClick(event) {
  const row = event.target.closest("[data-pull-request-number]");
  if (row) loadDetail(Number(row.dataset.pullRequestNumber)).catch(() => {});
}

// Routes dynamically rendered detail form submissions by stable form id.
function handlePageSubmit(event) {
  if (event.target.id === "pull-request-comment-form") {
    commentPullRequest(event).catch(() => {});
  } else if (event.target.id === "pull-request-review-form") {
    reviewPullRequest(event).catch(() => {});
  } else if (event.target.id === "pull-request-merge-form") {
    mergePullRequest(event).catch(() => {});
  }
}

// Injects the page before app.js binds generic navigation, then installs feature-specific handlers.
function init() {
  pullRequestUI.injectUI();
  byId("refresh-pull-requests").addEventListener("click", () => refreshList().catch(() => {}));
  byId("new-pull-request").addEventListener("click", openCreateDialog);
  byId("close-pull-request-create").addEventListener("click", closeCreateDialog);
  byId("pull-request-create-dialog").addEventListener("click", (event) => {
    if (event.target.id === "pull-request-create-dialog") closeCreateDialog();
  });
  byId("pull-request-create-form").addEventListener("submit", (event) => {
    createPullRequest(event).catch(() => {});
  });
  byId("pull-request-list").addEventListener("click", handlePageClick);
  byId("pull-request-detail").addEventListener("submit", handlePageSubmit);
  document.querySelector('.tab-button[data-tab="pull-requests"]').addEventListener("click", () => {
    refreshList().catch(() => {});
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !byId("pull-request-create-dialog").hidden) closeCreateDialog();
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
})();
