/*
  Dynamic toolbar and workspace markup for Project Sync Chain setup.
*/

// Injects the page before app.js binds generic toolbar navigation.
(() => {
// Adds a globally visible one-way-chain icon to the primary toolbar.
function injectToolbarButton() {
  if (document.querySelector('.tab-button[data-tab="sync-chain"]')) return;
  const button = document.createElement("button");
  button.className = "tab-button";
  button.type = "button";
  button.dataset.tab = "sync-chain";
  button.title = "Sync Chain Setup";
  button.setAttribute("aria-label", "Sync Chain Setup");
  button.innerHTML = `
    <img class="sync-chain-toolbar-icon" src="./sync-chain-icon.svg" alt="" draggable="false">
    <span class="tab-alert-dot success" data-sync-chain-alert hidden aria-hidden="true"></span>
  `;
  const settingsButton = document.querySelector('.tab-button[data-tab="settings"]');
  settingsButton.parentNode.insertBefore(button, settingsButton);
}

// Adds the chain list, editor, and new-chain controls as one scrollable workspace panel.
function injectPanel() {
  if (document.getElementById("panel-sync-chain")) return;
  document.querySelector(".workspace").insertAdjacentHTML("beforeend", `
    <section id="panel-sync-chain" class="panel" aria-labelledby="sync-chain-title">
      <div class="panel-header sync-chain-header">
        <div>
          <h2 id="sync-chain-title">Project Sync Chains</h2>
          <p id="sync-chain-summary">Configure one-way project promotion folders</p>
        </div>
        <div class="button-row">
          <select id="sync-chain-project"></select>
          <button id="create-sync-chain" type="button">Create chain</button>
          <button id="refresh-sync-chains" type="button">Refresh</button>
        </div>
      </div>
      <div class="sync-chain-layout">
        <aside class="settings-block sync-chain-list-card">
          <label>Saved chains</label>
          <div id="sync-chain-list" class="sync-chain-list" aria-live="polite"></div>
        </aside>
        <section id="sync-chain-editor" class="settings-block sync-chain-editor" aria-live="polite">
          <div class="empty-state">Select or create a Sync Chain</div>
        </section>
      </div>
    </section>
  `);
}

// Installs every Sync Chain UI surface before stateful controller binding begins.
function injectUI() {
  injectToolbarButton();
  injectPanel();
}

window.GitDeskSyncChainUI = { injectUI };
})();
