/* App-owned confirmation for Sync Chain metadata removal in desktop WebViews. */

(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
if (!nativeBridge || !renderHelpers) throw new Error("GitDesk Sync Chain deletion dependencies did not load.");

const { appendActivity, byId, setBusy, showMessage } = renderHelpers;
const state = { action: "", chainId: "", stage: "", returnFocus: null, busy: false };

function injectDialog() {
  document.body.insertAdjacentHTML("beforeend", `
    <section id="sync-chain-delete-modal" class="sync-chain-delete-modal" hidden>
      <div class="sync-chain-delete-dialog" role="dialog" aria-modal="true" tabindex="-1"
        aria-labelledby="sync-chain-delete-title" aria-describedby="sync-chain-delete-description">
        <header><span>Sync Chain setup</span><h2 id="sync-chain-delete-title"></h2></header>
        <p id="sync-chain-delete-description"></p>
        <p id="sync-chain-delete-status" role="status" aria-live="polite"></p>
        <div class="sync-chain-delete-actions">
          <button id="cancel-sync-chain-delete" type="button">Cancel</button>
          <button id="confirm-sync-chain-delete" type="button">Remove</button>
        </div>
      </div>
    </section>
  `);
}

function render() {
  const deletingChain = state.action === "deleteSyncChain";
  byId("sync-chain-delete-modal").hidden = !state.action;
  byId("sync-chain-delete-title").textContent = deletingChain ? "Delete this chain?" : "Remove this stage?";
  byId("sync-chain-delete-description").textContent = deletingChain
    ? "Only the saved chain setup will be deleted. Local and repository folders stay untouched."
    : "This stage and every stage after it will leave the chain. Their folders stay untouched.";
  byId("cancel-sync-chain-delete").disabled = state.busy;
  byId("confirm-sync-chain-delete").disabled = state.busy;
  byId("confirm-sync-chain-delete").textContent = state.busy ? "Removing…" : deletingChain
    ? "Delete chain" : "Remove stage";
}

function open(action, button) {
  if (state.busy) return;
  state.action = action;
  state.chainId = button.dataset.chainId || "";
  state.stage = button.dataset.stage || "";
  state.returnFocus = button;
  byId("sync-chain-delete-status").textContent = "";
  render();
  byId("cancel-sync-chain-delete").focus();
}

function close() {
  if (state.busy || !state.action) return;
  const returnFocus = state.returnFocus;
  state.action = ""; state.chainId = ""; state.stage = ""; state.returnFocus = null;
  render();
  if (returnFocus && returnFocus.isConnected) returnFocus.focus();
}

async function confirmRemoval() {
  if (!state.action || state.busy) return;
  state.busy = true; setBusy(true); render();
  try {
    const payload = { chain_id: state.chainId };
    if (state.stage) payload.stage = state.stage;
    const data = await nativeBridge.callNative(state.action, payload);
    window.GitDeskSyncChains.applyResponse(data);
    appendActivity(state.action === "deleteSyncChain" ? "Sync Chain deleted" : "Sync Chain stage removed");
    state.action = ""; state.chainId = ""; state.stage = ""; state.returnFocus = null;
  } catch (error) {
    const message = error.message || "GitDesk could not update this Sync Chain.";
    byId("sync-chain-delete-status").textContent = message;
    showMessage(message, true);
  } finally {
    state.busy = false; setBusy(false); render();
  }
}

function handlePanelClick(event) {
  const deleteButton = event.target.closest("#delete-sync-chain");
  const removeButton = event.target.closest(".remove-sync-stage");
  if (deleteButton) open("deleteSyncChain", deleteButton);
  if (removeButton) open("removeSyncStage", removeButton);
}

function handleDialog(event) {
  if (!state.action || state.busy) return;
  if ((event.type === "click" && event.target.id === "sync-chain-delete-modal")
      || (event.type === "keydown" && event.key === "Escape")) {
    event.preventDefault(); close(); return;
  }
  if (event.type !== "keydown" || event.key !== "Tab") return;
  const cancel = byId("cancel-sync-chain-delete");
  const confirm = byId("confirm-sync-chain-delete");
  if (event.shiftKey && document.activeElement === cancel) {
    event.preventDefault(); confirm.focus();
  } else if (!event.shiftKey && document.activeElement === confirm) {
    event.preventDefault(); cancel.focus();
  }
}

function init() {
  injectDialog();
  byId("panel-sync-chain").addEventListener("click", handlePanelClick);
  byId("cancel-sync-chain-delete").addEventListener("click", close);
  byId("confirm-sync-chain-delete").addEventListener("click", confirmRemoval);
  byId("sync-chain-delete-modal").addEventListener("click", handleDialog);
  document.addEventListener("keydown", handleDialog);
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
else init();
})();
