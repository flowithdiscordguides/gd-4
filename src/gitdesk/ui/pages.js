/*
  GitHub Pages and commit-history UI manager for GitDesk.
*/

// Keeps Pages UI state private while exposing only the hooks used by app.js and overview.js.
(() => {
const renderHelpers = window.GitDeskRender;
const deploymentManager = window.GitDeskPagesDeployment;

if (!renderHelpers || !deploymentManager) {
  throw new Error("GitDesk Pages dependencies did not load.");
}

const {
  appendActivity,
  byId,
  setText,
  showMessage,
} = renderHelpers;

let runActionRef = null;
let repositoryPayloadRef = null;
let githubPayloadRef = null;
let currentBranchRef = null;
let selectedCommit = null;
let expectedHistorySha = "";

// Installs the commit-history modal styles that remain separate from the Pages deployment stylesheet.
function installStyles() {
  if (document.getElementById("pages-style")) return;
  const style = document.createElement("style");
  style.id = "pages-style";
  style.textContent = `
    .history-button[hidden],.history-dialog[hidden],.tag-dialog[hidden]{display:none}
    .history-dialog,.tag-dialog{position:fixed;inset:10% 12%;z-index:40;background:var(--panel)}
    .history-dialog,.tag-dialog{border:1px solid var(--line);border-radius:8px;padding:18px}
    .history-dialog,.tag-dialog{box-shadow:0 20px 60px rgba(0,0,0,.35);overflow:auto}
    .tag-dialog{inset:24% 30%;display:grid;gap:12px}
    .history-list{display:grid;gap:8px;margin-top:14px}
    .history-row{display:grid;grid-template-columns:90px minmax(0,1fr) 120px 140px 180px 38px;gap:10px}
    .history-row{align-items:center;border:1px solid var(--line);border-radius:8px}
    .history-row{padding:10px;background:var(--surface)}
    .history-row strong,.history-row span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .history-tag-action{display:grid;width:34px;height:34px;min-height:34px;padding:5px;place-items:center}
    .history-tag-action{border-color:rgba(255,255,255,.25);background:var(--gitdesk-success-bg)}
    .history-tag-action img{width:22px;height:22px;object-fit:contain}
    .history-tag-spacer{width:34px;height:34px}
    @media (max-width: 860px){.history-dialog,.tag-dialog{inset:6%}}
    @media (max-width: 860px){.history-row{grid-template-columns:1fr}}
  `;
  document.head.append(style);
}

// Escapes GitHub commit and tag metadata before rendering History rows.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Formats GitHub commit timestamps in the user's local desktop locale.
function formatDateTime(value) {
  const parsed = new Date(value || "");
  if (Number.isNaN(parsed.getTime())) {
    return "Unknown time";
  }
  return parsed.toLocaleString();
}

// Creates the History and tag dialogs once during Repo Mode bootstrap.
function injectHistoryControls() {
  let button = document.getElementById("history-button");
  if (!button) {
    button = document.createElement("button");
    button.id = "history-button";
    button.className = "history-button";
    button.type = "button";
    button.hidden = true;
    button.textContent = "History";
    const tabs = document.getElementById("overview-tabs");
    if (tabs) {
      tabs.append(button);
    } else {
      byId("commit-push-button").after(button);
    }
  }

  if (document.getElementById("history-dialog")) return;

  const historyDialog = document.createElement("section");
  historyDialog.id = "history-dialog";
  historyDialog.className = "history-dialog";
  historyDialog.hidden = true;
  historyDialog.innerHTML = `
    <div class="panel-header">
      <div>
        <h2>Commit history</h2>
        <p id="history-summary">Recent commits</p>
      </div>
      <button id="close-history" type="button">Close</button>
    </div>
    <div id="history-list" class="history-list" aria-live="polite"></div>
  `;
  document.body.append(historyDialog);

  const tagDialog = document.createElement("form");
  tagDialog.id = "tag-dialog";
  tagDialog.className = "tag-dialog";
  tagDialog.hidden = true;
  tagDialog.innerHTML = `
    <h2>Create tag</h2>
    <p id="tag-target">No commit selected</p>
    <label for="tag-name">Tag</label>
    <input id="tag-name" type="text" spellcheck="false" placeholder="v1.0.0">
    <label for="tag-message">Message</label>
    <input id="tag-message" type="text" spellcheck="true" placeholder="Release tag">
    <div class="button-row">
      <button id="create-history-tag" type="submit">Push tag</button>
      <button id="cancel-history-tag" type="button">Cancel</button>
    </div>
  `;
  document.body.append(tagDialog);
}

// Combines local repository and GitHub account fields for History bridge actions.
function payload(extraFields) {
  const base = repositoryPayloadRef();
  const github = githubPayloadRef();
  Object.keys(github).forEach((key) => {
    base[key] = github[key];
  });
  Object.keys(extraFields || {}).forEach((key) => {
    base[key] = extraFields[key];
  });
  return base;
}

// Makes History available after a push establishes a remote commit to display.
function showHistoryButton() {
  const button = document.getElementById("history-button");
  if (button) button.hidden = false;
}

// Records the pushed SHA so the next History refresh can bridge GitHub's commit-list propagation delay.
function notePushedCommit(commitSha) {
  expectedHistorySha = String(commitSha || "").trim().toLowerCase();
  showHistoryButton();
  if (window.GitDeskReleaseAlerts) window.GitDeskReleaseAlerts.noteHistoryReady();
}

// Returns whether the saved GitHub owner/repo settings are enough to request commit history.
function hasGithubRepositorySettings() {
  const github = githubPayloadRef ? githubPayloadRef() : {};
  return Boolean(github && github.owner && github.repo);
}

// Keeps History visible across app launches once the repository settings can load remote commits.
function syncHistoryAvailability(branches) {
  const button = document.getElementById("history-button");
  if (!button) {
    return;
  }
  const knownCommitlessRepository = branches && branches.has_commits === false;
  button.hidden = !hasGithubRepositorySettings() || knownCommitlessRepository;
}

// Opens the commit history dialog and loads recent commits for the active branch.
async function openHistory() {
  byId("history-dialog").hidden = false;
  const branch = currentBranchRef ? currentBranchRef() : "";
  const requestPayload = { branch };
  if (expectedHistorySha) requestPayload.expected_sha = expectedHistorySha;
  const data = await runActionRef("listCommitHistory", payload(requestPayload), "Commit history refreshed");
  const commits = data.commits || [];
  const foundExpectedSha = expectedHistorySha && commits.some((commit) => (
    String(commit.sha || "").toLowerCase() === expectedHistorySha
  ));
  if (foundExpectedSha) {
    expectedHistorySha = "";
  }
  renderHistory(commits);
  if (!expectedHistorySha && window.GitDeskReleaseAlerts) window.GitDeskReleaseAlerts.clearHistoryReady();
}

// Renders commit rows with a create-tag button only when no tag exists for that commit.
function renderHistory(commits) {
  setText("history-summary", `${commits.length} recent commits`);
  if (!commits.length) {
    byId("history-list").innerHTML = '<div class="empty-state">No commits found</div>';
    return;
  }
  byId("history-list").innerHTML = commits.map((commit) => {
    const tags = Array.isArray(commit.tags) ? commit.tags : [];
    const tagAction = tags.length ? '<span class="history-tag-spacer" aria-hidden="true"></span>' : `
      <button class="history-tag-action icon-button" type="button" data-sha="${escapeHtml(commit.sha)}"
        aria-label="Create tag for ${escapeHtml(commit.short_sha)}" title="Create tag">
        <img src="./newtag-icon.svg" alt="" draggable="false">
      </button>
    `;
    return `
      <div class="history-row" data-sha="${escapeHtml(commit.sha)}">
        <strong>${escapeHtml(commit.short_sha)}</strong>
        <span>${escapeHtml(commit.message)}</span>
        <span>${escapeHtml(commit.tag_label || "No tag")}</span>
        <span>${escapeHtml(commit.author)}</span>
        <span>${escapeHtml(formatDateTime(commit.date))}</span>
        ${tagAction}
      </div>
    `;
  }).join("");
  document.querySelectorAll(".history-tag-action").forEach((button) => {
    button.addEventListener("click", openTagDialog);
  });
}

// Opens the tag form for an untagged commit history row.
function openTagDialog(event) {
  event.preventDefault();
  event.stopPropagation();
  selectedCommit = event.currentTarget.dataset.sha || "";
  setText("tag-target", selectedCommit ? `Commit ${selectedCommit.slice(0, 7)}` : "No commit selected");
  byId("tag-name").value = "";
  byId("tag-message").value = "";
  byId("tag-dialog").hidden = false;
  byId("tag-name").focus();
  fillSuggestedTag().catch((error) => {
    showMessage(error.message || "Could not suggest the next tag.", true);
  });
}

// Loads the next release tag from local and origin tags, then fills the tag form if it is still empty.
async function fillSuggestedTag() {
  const suggestion = await runActionRef("suggestNextTag", payload({}), "", { quiet: true });
  const tagName = suggestion && suggestion.tag ? suggestion.tag : "";
  if (!tagName || byId("tag-dialog").hidden || byId("tag-name").value.trim()) {
    return;
  }
  byId("tag-name").value = tagName;
  byId("tag-message").value = tagName;
}

// Creates the remote tag through GitHub's Git database API.
async function createHistoryTag(event) {
  event.preventDefault();
  if (!selectedCommit) {
    showMessage("Select a commit before creating a tag.", true);
    return;
  }
  const tagName = byId("tag-name").value.trim();
  const message = byId("tag-message").value.trim() || tagName;
  const result = await runActionRef("createTagForCommit", payload({
    tag: { tag: tagName, message, sha: selectedCommit },
  }), "Tag pushed");
  if (window.GitDeskReleaseAlerts) {
    window.GitDeskReleaseAlerts.noteTagPushed(result.tag);
  }
  if (window.GitDeskActions) {
    window.GitDeskActions.refreshAfterPush(selectedCommit);
  }
  appendActivity(`Tag ${result.tag} pushed for release`);
  byId("tag-dialog").hidden = true;
  openHistory().catch((error) => {
    showMessage(error.message || "Could not refresh commit history.", true);
  });
}

// Binds events after app.js has initialized the DOM and backend action wrapper.
function bind(options) {
  runActionRef = options.runAction;
  repositoryPayloadRef = options.repositoryPayload;
  githubPayloadRef = options.githubPayload;
  currentBranchRef = options.currentBranch;
  deploymentManager.bind(options);
  installStyles();
  injectHistoryControls();
  byId("history-button").addEventListener("click", () => openHistory().catch(() => {}));
  byId("close-history").addEventListener("click", () => {
    byId("history-dialog").hidden = true;
  });
  byId("cancel-history-tag").addEventListener("click", () => {
    byId("tag-dialog").hidden = true;
  });
  byId("tag-dialog").addEventListener("submit", createHistoryTag);
}

// Publishes Pages controls used by the main app and Overview commit flow.
window.GitDeskPages = {
  bind,
  notePushedCommit,
  showHistoryButton,
  syncHistoryAvailability,
};
})();
