/*
  Settings tab controller for splitting GitHub, user, system, and theme controls into focused panels.
*/

// Keeps Settings markup and tab behavior isolated from the main app controller and backend bridge.
(() => {
// The Settings root stays in index.html so this module can own the heavier tab markup.
const ROOT_ID = "settings-content-root";

// Settings tab buttons use a narrow selector so primary sidebar tabs are not affected.
const TAB_SELECTOR = "#panel-settings .settings-tab";

// Settings panels share the same data key as their controlling tab button.
const PANEL_SELECTOR = "#panel-settings .settings-tab-panel";

// Keyboard navigation mirrors native tab widgets without adding any dependency.
const MOVEMENT_KEYS = ["ArrowLeft", "ArrowRight", "Home", "End"];

// Returns the static Settings HTML string; it takes no parameters and has no side effects.
function settingsMarkup() {
  return `
    <div class="settings-tabs" role="tablist" aria-label="Settings sections">
      <button
        id="settings-tab-github"
        class="settings-tab active"
        type="button"
        role="tab"
        aria-selected="true"
        aria-controls="settings-panel-github"
        data-settings-tab="github"
      >
        GitHub settings
      </button>
      <button
        id="settings-tab-user"
        class="settings-tab"
        type="button"
        role="tab"
        aria-selected="false"
        aria-controls="settings-panel-user"
        data-settings-tab="user"
      >
        User settings
      </button>
      <button
        id="settings-tab-system"
        class="settings-tab"
        type="button"
        role="tab"
        aria-selected="false"
        aria-controls="settings-panel-system"
        data-settings-tab="system"
      >
        System settings
      </button>
      <button
        id="settings-tab-theme"
        class="settings-tab"
        type="button"
        role="tab"
        aria-selected="false"
        aria-controls="settings-panel-theme"
        data-settings-tab="theme"
      >
        Theme
      </button>
    </div>
    <div class="settings-tab-content">
      <section
        id="settings-panel-github"
        class="settings-tab-panel active"
        role="tabpanel"
        aria-labelledby="settings-tab-github"
        data-settings-panel="github"
      >
        <div class="settings-grid settings-github-grid">
          <form id="account-form" class="settings-block settings-account-card">
            <label for="token-input">Add PAT</label>
            <input
              id="token-input"
              type="password"
              autocomplete="off"
              placeholder="GitHub personal access token"
            >
            <div class="button-row">
              <button id="save-account" type="submit" disabled>Save PAT profile</button>
              <button id="show-pat-help" type="button" aria-expanded="false" aria-controls="pat-help">
                How to get PAT
              </button>
            </div>
          </form>
          <div id="pat-help" class="settings-block settings-help-card" hidden>
            <label>GitHub PAT setup</label>
            <p class="row-meta">Create one fine-grained token for each personal or organization resource owner.</p>
            <ol class="row-meta">
              <li>Enter the exact organization login or personal account that owns the repositories.</li>
              <li>Open the prefilled setup and confirm GitHub selected that Resource owner.</li>
              <li>Select only the repositories GitDesk should manage, or all repositories when appropriate.</li>
              <li>Generate the token after any required organization approval or policy checks.</li>
              <li>Copy the token once, paste it into Add PAT, then save the account.</li>
            </ol>
            <div class="pat-owner-field">
              <label for="pat-resource-owner">PAT resource owner</label>
              <input
                id="pat-resource-owner"
                type="text"
                autocomplete="off"
                spellcheck="false"
                placeholder="organization or personal login"
              >
              <p class="row-meta">
                Type the exact owner here before opening GitHub. This controls the selected Resource owner page.
              </p>
            </div>
            <div class="pat-permission-summary" aria-labelledby="pat-permission-title">
              <strong id="pat-permission-title">Prefilled repository permissions</strong>
              <ul class="row-meta">
                <li>Write: Contents, Pull requests, Workflows, Pages, and Administration</li>
                <li>Read: Actions, Deployments, and Metadata</li>
              </ul>
              <p class="row-meta">GitHub does not offer Checks API access to fine-grained PATs.</p>
            </div>
            <a
              href="https://docs.github.com/articles/creating-a-personal-access-token-for-the-command-line"
              target="_blank"
              rel="noreferrer"
            >
              Open official GitHub PAT docs
            </a>
          </div>
          <div class="settings-block settings-active-account">
            <label for="account-select">Active PAT Profile</label>
            <select id="account-select"></select>
            <p id="account-details" class="row-meta">No PAT profiles saved</p>
            <p id="pat-expiration-status" class="pat-expiration-status" role="status" hidden></p>
            <button id="clear-account" type="button">Remove token</button>
          </div>
          <form id="github-form" class="settings-block settings-repo-card">
            <label for="github-owner">GitHub owner</label>
            <input id="github-owner" type="text" spellcheck="false" placeholder="owner">
            <label for="github-repo">GitHub repository</label>
            <input id="github-repo" type="text" spellcheck="false" placeholder="repository">
            <button id="save-github-repo" type="submit">Save repository</button>
          </form>
          <section class="settings-block settings-jingle-card" aria-labelledby="action-jingles-title">
            <label id="action-jingles-title">Actions jingles</label>
            <p class="row-meta">Play a distinct sound when a Repo Mode Actions run succeeds or fails.</p>
            <div class="action-jingle-row">
              <div>
                <strong>Success</strong>
                <span id="action-jingle-success-file" class="row-meta">Built-in success jingle</span>
              </div>
              <button id="replace-action-jingle-success" type="button"
                aria-label="Replace success jingle">Replace jingle</button>
            </div>
            <div class="action-jingle-row">
              <div>
                <strong>Failure</strong>
                <span id="action-jingle-failure-file" class="row-meta">Built-in failure jingle</span>
              </div>
              <button id="replace-action-jingle-failure" type="button"
                aria-label="Replace failure jingle">Replace jingle</button>
            </div>
            <p id="action-jingle-status" class="row-meta" role="status" aria-live="polite"></p>
          </section>
        </div>
      </section>
      <section
        id="settings-panel-user"
        class="settings-tab-panel"
        role="tabpanel"
        aria-labelledby="settings-tab-user"
        data-settings-panel="user"
        hidden
      >
        <div id="settings-user-content" class="settings-grid settings-user-grid"></div>
      </section>
      <section
        id="settings-panel-system"
        class="settings-tab-panel"
        role="tabpanel"
        aria-labelledby="settings-tab-system"
        data-settings-panel="system"
        hidden
      >
        <div id="settings-system-content" class="settings-grid settings-system-grid"></div>
        <div class="settings-hidden-meta" hidden>
          <code id="settings-location">Not loaded</code>
        </div>
      </section>
      <section
        id="settings-panel-theme"
        class="settings-tab-panel"
        role="tabpanel"
        aria-labelledby="settings-tab-theme"
        data-settings-panel="theme"
        hidden
      >
        <div id="settings-theme-content" class="settings-grid settings-theme-grid"></div>
      </section>
    </div>
  `;
}

// Injects static Settings controls; returns true when the markup exists for later binders.
function ensureSettingsMarkup() {
  const root = document.getElementById(ROOT_ID);
  if (!root) {
    return false;
  }
  if (root.querySelector(".settings-tabs")) {
    return true;
  }
  root.innerHTML = settingsMarkup();
  return true;
}

// Returns the Settings tab buttons in visual order; it takes no parameters.
function settingsTabs() {
  return Array.from(document.querySelectorAll(TAB_SELECTOR));
}

// Returns the Settings tab panels; it takes no parameters and reads the current DOM.
function settingsPanels() {
  return Array.from(document.querySelectorAll(PANEL_SELECTOR));
}

// Accepts one tab button and returns its stable tab key, or an empty string for invalid input.
function tabNameFromButton(button) {
  return button && button.dataset ? String(button.dataset.settingsTab || "") : "";
}

// Accepts a tab key and focus flag, then mutates tab and panel state without returning a value.
function activateSettingsTab(tabName, focusTab = false) {
  if (!tabName) {
    return;
  }

  // The tab button state drives visual styling and screen-reader selection.
  settingsTabs().forEach((button) => {
    const isActive = tabNameFromButton(button) === tabName;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-selected", isActive ? "true" : "false");
    button.tabIndex = isActive ? 0 : -1;
    if (isActive && focusTab) {
      button.focus();
    }
  });

  // Hidden panels are removed from sequential navigation so inactive forms cannot receive focus.
  settingsPanels().forEach((panel) => {
    const isActive = panel.dataset.settingsPanel === tabName;
    panel.classList.toggle("active", isActive);
    panel.hidden = !isActive;
  });
}

// Accepts the current tab index, pressed key, and tab count, then returns the next tab index.
function nextTabIndex(currentIndex, key, tabCount) {
  if (key === "Home") {
    return 0;
  }
  if (key === "End") {
    return tabCount - 1;
  }
  if (key === "ArrowLeft") {
    return (currentIndex - 1 + tabCount) % tabCount;
  }
  return (currentIndex + 1) % tabCount;
}

// Accepts a keydown event, updates tab state for movement keys, and returns without a value.
function handleSettingsTabKeydown(event) {
  if (MOVEMENT_KEYS.indexOf(event.key) < 0) {
    return;
  }

  const tabs = settingsTabs();
  const currentIndex = tabs.indexOf(event.currentTarget);
  if (currentIndex < 0 || !tabs.length) {
    return;
  }

  event.preventDefault();
  const targetIndex = nextTabIndex(currentIndex, event.key, tabs.length);
  activateSettingsTab(tabNameFromButton(tabs[targetIndex]), true);
}

// Injects Settings markup, binds tab events, and returns without a value.
function bindSettingsTabs() {
  if (!ensureSettingsMarkup()) {
    return;
  }

  const tabs = settingsTabs();
  if (!tabs.length) {
    return;
  }

  // Each button owns its tab key, so delegated state is unnecessary here.
  tabs.forEach((button) => {
    button.addEventListener("click", () => activateSettingsTab(tabNameFromButton(button)));
    button.addEventListener("keydown", handleSettingsTabKeydown);
  });

  const activeTab = tabs.find((button) => button.classList.contains("active")) || tabs[0];
  activateSettingsTab(tabNameFromButton(activeTab));
}

// Accepts a callback, runs it after DOM parsing, and returns without a value.
function onDocumentReady(callback) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", callback);
    return;
  }
  callback();
}

onDocumentReady(bindSettingsTabs);
})();
