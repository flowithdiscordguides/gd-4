/*
  Repo Mode Pull Request navigation, markup, and escaped rendering.
*/

// Publishes a narrow view API while the controller owns bridge calls and mutable selection.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk Pull Request UI dependencies did not load.");
}

const { byId, escapeHtml } = renderHelpers;

// Adds the Pull Requests page beside other repository workflow destinations.
function injectToolbarButton() {
  if (document.querySelector('.tab-button[data-tab="pull-requests"]')) return;
  const button = document.createElement("button");
  button.className = "tab-button";
  button.type = "button";
  button.dataset.tab = "pull-requests";
  button.title = "Pull Requests";
  button.setAttribute("aria-label", "Pull Requests");
  button.innerHTML = `
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <circle cx="6" cy="5" r="2"></circle><circle cx="18" cy="19" r="2"></circle>
      <path d="M6 7v12M18 17v-4a4 4 0 0 0-4-4H9m3-3-3 3 3 3"></path>
    </svg>
  `;
  const actionsButton = document.querySelector('.tab-button[data-tab="actions"]');
  actionsButton.parentNode.insertBefore(button, actionsButton);
}

// Adds the master-detail review workspace before Settings.
function injectPanel() {
  if (document.getElementById("panel-pull-requests")) return;
  const panel = document.createElement("section");
  panel.id = "panel-pull-requests";
  panel.className = "panel";
  panel.setAttribute("aria-labelledby", "pull-requests-title");
  panel.innerHTML = `
    <header class="panel-header pull-requests-header">
      <div>
        <h2 id="pull-requests-title">Pull Requests</h2>
        <p id="pull-requests-summary">Open a repository to review its work.</p>
      </div>
      <div class="button-row">
        <button id="new-pull-request" type="button">New Pull Request</button>
        <button id="refresh-pull-requests" type="button">Refresh</button>
      </div>
    </header>
    <div class="pull-requests-layout">
      <aside class="pull-request-list-pane">
        <div id="pull-request-list" class="pull-request-list" aria-live="polite"></div>
      </aside>
      <section id="pull-request-detail" class="pull-request-detail" aria-live="polite">
        <div class="empty-state">Select a Pull Request to inspect files, commits, and review activity.</div>
      </section>
    </div>
    <div id="pull-request-create-dialog" class="pull-request-dialog" role="dialog"
      aria-modal="true" aria-labelledby="pull-request-create-title" hidden>
      <form id="pull-request-create-form" class="pull-request-create-form">
        <header><h3 id="pull-request-create-title">Create Pull Request</h3>
          <button id="close-pull-request-create" type="button">Close</button></header>
        <label for="pull-request-title-input">Title</label>
        <input id="pull-request-title-input" maxlength="500" required>
        <div class="pull-request-branch-row">
          <label>Head branch<input id="pull-request-head" spellcheck="false" required></label>
          <span aria-hidden="true">→</span>
          <label>Base branch<input id="pull-request-base" spellcheck="false" required></label>
        </div>
        <label for="pull-request-body">Description</label>
        <textarea id="pull-request-body" rows="8"></textarea>
        <label class="check-row"><input id="pull-request-draft" type="checkbox"><span>Create as draft</span></label>
        <button class="primary" type="submit">Create Pull Request</button>
      </form>
    </div>
  `;
  const settingsPanel = document.getElementById("panel-settings");
  settingsPanel.parentNode.insertBefore(panel, settingsPanel);
}

// Installs both navigation and page markup before app.js binds generic tabs.
function injectUI() {
  injectToolbarButton();
  injectPanel();
}

// Returns a concise state label with draft and merge information.
function pullStateLabel(pull) {
  if (pull.merged) return "merged";
  if (pull.draft) return "draft";
  return pull.state || "open";
}

// Renders the open Pull Request list and preserves the active row.
function renderList(data, selectedNumber) {
  const pulls = data && Array.isArray(data.pull_requests) ? data.pull_requests : [];
  byId("pull-requests-summary").textContent =
    `${pulls.length} open Pull Request${pulls.length === 1 ? "" : "s"} · ${data.owner || ""}/${data.repo || ""}`;
  byId("pull-request-list").innerHTML = pulls.length ? pulls.map((pull) => `
    <button class="pull-request-row${pull.number === selectedNumber ? " active" : ""}" type="button"
      data-pull-request-number="${pull.number}">
      <span class="pull-request-number">#${pull.number}</span>
      <span><strong>${escapeHtml(pull.title)}</strong>
        <small>${escapeHtml(pull.user.login)} · ${escapeHtml(pull.head.ref)} → ${escapeHtml(pull.base.ref)}</small>
      </span>
      <span class="status-pill ${pull.draft ? "warning" : "success"}">${escapeHtml(pullStateLabel(pull))}</span>
    </button>
  `).join("") : '<div class="empty-state">No open Pull Requests.</div>';
}

// Renders one unified patch as escaped preformatted text or an honest unavailable state.
function fileMarkup(file) {
  const patch = file.patch
    ? `<pre class="pull-request-patch">${escapeHtml(file.patch)}</pre>`
    : '<p class="row-meta">GitHub did not return a text patch for this file.</p>';
  return `
    <details class="pull-request-file">
      <summary>
        <strong>${escapeHtml(file.filename)}</strong>
        <span>+${file.additions} −${file.deletions}</span>
      </summary>
      ${patch}
    </details>
  `;
}

// Renders comments and reviews in one readable chronological conversation.
function conversationMarkup(detail) {
  const events = [
    ...(detail.conversation || []).map((item) => ({ ...item, event_type: item.kind })),
    ...(detail.reviews || []).map((item) => ({
      ...item,
      event_type: "review",
      created_at: item.submitted_at,
    })),
  ].sort((left, right) => String(left.created_at).localeCompare(String(right.created_at)));
  return events.length ? events.map((item) => `
    <article class="pull-request-conversation-item">
      <header><strong>${escapeHtml(item.user.login || "GitHub user")}</strong>
        <span>${escapeHtml(item.event_type === "review" ? item.state : item.event_type)}</span></header>
      ${item.path ? `<code>${escapeHtml(item.path)}${item.line ? `:${item.line}` : ""}</code>` : ""}
      <p>${escapeHtml(item.body || "No review body.").replace(/\n/g, "<br>")}</p>
    </article>
  `).join("") : '<div class="empty-state">No review conversation yet.</div>';
}

// Renders complete review context and explicit comment/review/merge actions.
function renderDetail(detail) {
  const pull = detail.pull_request || {};
  const reviewerNames = (detail.requested_reviewers || []).map((user) => `@${user.login}`);
  const teamNames = (detail.requested_teams || []).map((team) => team.name);
  const requested = [...reviewerNames, ...teamNames].join(", ") || "No pending review requests";
  byId("pull-request-detail").innerHTML = `
    <div class="pull-request-detail-header">
      <div><span>#${pull.number} · ${escapeHtml(pullStateLabel(pull))}</span>
        <h3>${escapeHtml(pull.title)}</h3>
        <p>${escapeHtml(pull.head.label)} → ${escapeHtml(pull.base.label)}</p></div>
      <div class="pull-request-totals">
        <strong>+${pull.additions}</strong><strong>−${pull.deletions}</strong>
        <span>${pull.changed_files} files · ${pull.commits} commits</span>
      </div>
    </div>
    <p class="pull-request-body">${escapeHtml(pull.body || "No description.").replace(/\n/g, "<br>")}</p>
    <div class="pull-request-review-request">
      <strong>Requested reviewers</strong><span>${escapeHtml(requested)}</span>
    </div>
    <section class="pull-request-section"><h4>Files</h4>
      <div class="pull-request-files">${(detail.files || []).map(fileMarkup).join("")
        || '<div class="empty-state">No changed files returned.</div>'}</div></section>
    <section class="pull-request-section"><h4>Commits</h4>
      <div class="pull-request-commits">${(detail.commits || []).map((commit) => `
        <div><code>${escapeHtml(commit.sha.slice(0, 8))}</code><span><strong>${escapeHtml(commit.subject)}</strong>
          <small>${escapeHtml(commit.author)} · ${escapeHtml(commit.date)}</small></span></div>
      `).join("") || '<div class="empty-state">No commits returned.</div>'}</div></section>
    <section class="pull-request-section"><h4>Conversation and reviews</h4>
      <div class="pull-request-conversation">${conversationMarkup(detail)}</div></section>
    <section class="pull-request-action-grid">
      <form id="pull-request-comment-form"><label for="pull-request-comment">Add comment</label>
        <textarea id="pull-request-comment" rows="4" required></textarea>
        <button type="submit">Comment</button></form>
      <form id="pull-request-review-form"><label for="pull-request-review-body">Submit review</label>
        <textarea id="pull-request-review-body" rows="4"></textarea>
        <div class="button-row">
          <button type="submit" data-review-event="COMMENT">Review comment</button>
          <button type="submit" data-review-event="APPROVE">Approve</button>
          <button class="danger-action" type="submit" data-review-event="REQUEST_CHANGES">Request changes</button>
        </div></form>
      <form id="pull-request-merge-form"><label for="pull-request-merge-method">Merge Pull Request</label>
        <select id="pull-request-merge-method"><option value="merge">Merge commit</option>
          <option value="squash">Squash and merge</option><option value="rebase">Rebase and merge</option></select>
        <button type="submit" ${pull.draft || pull.merged ? "disabled" : ""}>Merge</button></form>
    </section>
  `;
}

window.GitDeskPullRequestUI = { injectUI, renderDetail, renderList };
})();
