/*
  Progressive skipped-item ledger and backend-owned native reveal actions for Backup transfers.
*/

// Keeps source locations out of browser state while exposing every opaque skipped-item record.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
if (!nativeBridge || !renderHelpers) {
  throw new Error("GitDesk skipped Backup item dependencies did not load.");
}
const { callNative } = nativeBridge;
const { byId, escapeHtml } = renderHelpers;
const PAGE_SIZE = 100;
const state = { items: [], jobId: "", visible: PAGE_SIZE };

// Returns modal markup so the parent transfer surface controls one cohesive dialog.
function markup() {
  return `
    <section id="backup-skipped-section" class="backup-skipped-section" hidden
      aria-labelledby="backup-skipped-title">
      <header><div><h3 id="backup-skipped-title">Skipped items</h3>
        <p id="backup-skipped-summary"></p></div>
        <span id="backup-skipped-count" class="backup-skipped-count"></span></header>
      <div id="backup-skipped-list" class="backup-skipped-list" role="list"></div>
      <div class="backup-skipped-footer">
        <p id="backup-skipped-status" aria-live="polite">
          Original locations are recorded in backup-log.json; use Open in Finder to copy an item manually.
        </p>
        <button id="show-more-backup-skips" type="button" hidden>Show more</button>
      </div>
    </section>
  `;
}

// Renders the current bounded window while retaining access to every item through Show more.
function renderRows() {
  const visibleItems = state.items.slice(0, state.visible);
  byId("backup-skipped-list").innerHTML = visibleItems.map((item) => `
    <div class="backup-skipped-row" role="listitem">
      <span><strong>${escapeHtml(item.name || "Skipped item")}</strong>
        <small>${escapeHtml(item.reason || "The item could not be copied.")}</small></span>
      <button type="button" data-open-backup-skip="${escapeHtml(item.id || "")}"
        aria-label="Open ${escapeHtml(item.name || "skipped item")} in Finder">Open in Finder</button>
    </div>
  `).join("");
  const remaining = Math.max(0, state.items.length - visibleItems.length);
  const moreButton = byId("show-more-backup-skips");
  moreButton.hidden = remaining === 0;
  moreButton.textContent = `Show ${Math.min(PAGE_SIZE, remaining)} more`;
}

// Applies one completed job's public ledger without rendering captured absolute source paths.
function render(job) {
  const result = job && job.result ? job.result : {};
  state.items = Array.isArray(result.skipped_items) ? result.skipped_items : [];
  state.jobId = String(job && job.job_id ? job.job_id : "");
  state.visible = PAGE_SIZE;
  const section = byId("backup-skipped-section");
  section.hidden = state.items.length === 0;
  if (!state.items.length) return;
  byId("backup-skipped-summary").textContent =
    "The backup continued and these items remain pending for the next sync.";
  byId("backup-skipped-count").textContent = String(state.items.length);
  renderRows();
}

// Clears all prior terminal records before another transfer starts in the reusable dialog.
function clear() {
  state.items = [];
  state.jobId = "";
  state.visible = PAGE_SIZE;
  const section = document.getElementById("backup-skipped-section");
  if (section) {
    section.hidden = true;
    byId("backup-skipped-list").innerHTML = "";
  }
}

// Reveals one item through its process-owned job and opaque id instead of a browser-provided path.
async function openItem(button) {
  const itemId = String(button.dataset.openBackupSkip || "");
  const item = state.items.find((candidate) => candidate.id === itemId);
  if (!item || !state.jobId) return;
  button.disabled = true;
  try {
    await callNative("openBackupSkippedItem", { job_id: state.jobId, item_id: itemId });
    byId("backup-skipped-status").textContent = `${item.name || "Skipped item"} opened in Finder.`;
  } catch (error) {
    byId("backup-skipped-status").textContent =
      error.message || "The original skipped item is no longer available.";
  } finally {
    button.disabled = false;
  }
}

// Uses document delegation because the transfer modal injects this module's markup after script evaluation.
function bindEvents() {
  document.addEventListener("click", (event) => {
    const openButton = event.target.closest("[data-open-backup-skip]");
    if (openButton) openItem(openButton).catch(() => {});
    if (event.target.id === "show-more-backup-skips") {
      state.visible += PAGE_SIZE;
      renderRows();
    }
  });
}

window.GitDeskBackupSkippedItems = { clear, markup, render };
bindEvents();
})();
