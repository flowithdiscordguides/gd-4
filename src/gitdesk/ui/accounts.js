/*
  GitHub account controls for multi-account authentication. Tokens never leave Python once submitted.
*/

// Keeps account UI state private while exposing only active-account helpers to the main controller.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk account dependencies did not load.");
}

const { byId, setText } = renderHelpers;
let runActionRef = null;
let authChangedRef = null;
let githubPayloadRef = null;
let authState = { accounts: [], active_account: "" };
let expirationTimer = null;

// Browser timers cap delays at a signed 32-bit millisecond value, so long lifetimes refresh in bounded stages.
const MAX_TIMEOUT_DELAY = 2147483647;

// Returns the account list from the latest backend auth state.
function accounts() {
  return authState.accounts || [];
}

// Returns accounts whose non-secret metadata still records a saved backend token.
function signedInAccounts() {
  return accounts().filter((account) => account.token_present);
}

// Calculates expiration from non-secret metadata so an open Settings page updates as time passes.
function tokenExpired(account) {
  const expiration = account ? Date.parse(account.token_expires_at || "") : NaN;
  return Number.isFinite(expiration) && expiration <= Date.now();
}

// Excludes known-expired profiles from controls that initiate GitHub operations.
function usableAccounts() {
  return signedInAccounts().filter((account) => !tokenExpired(account));
}

// Formats GitHub's UTC expiration for a concise, locale-aware Settings status.
function tokenExpirationLabel(account) {
  const expiration = account ? Date.parse(account.token_expires_at || "") : NaN;
  if (!Number.isFinite(expiration)) return "";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(expiration);
}

// Re-renders at the active PAT's expiration moment without polling or reading its credential value.
function scheduleExpirationRefresh(account) {
  window.clearTimeout(expirationTimer);
  const expiration = account ? Date.parse(account.token_expires_at || "") : NaN;
  if (!Number.isFinite(expiration) || expiration <= Date.now()) return;
  const delay = Math.min(expiration - Date.now() + 1000, MAX_TIMEOUT_DELAY);
  expirationTimer = window.setTimeout(renderAccounts, delay);
}

// Returns the resource-owner key for the currently active PAT profile.
function activeLogin() {
  return authState.active_account || "";
}

// Returns the active account metadata without exposing the token.
function activeAccount() {
  const login = activeLogin();
  const signedIn = signedInAccounts();
  return signedIn.find((account) => account.login === login) || signedIn[0] || null;
}

// Uses GitHub's public avatar endpoint so the header reflects the active account in Repo Mode.
function renderHeaderAccount() {
  const avatar = document.getElementById("account-avatar");
  const switcher = document.getElementById("header-account-switcher");
  const headerSelect = document.getElementById("header-account-select");
  const active = activeAccount();
  if (!avatar || !switcher || !headerSelect) {
    return;
  }
  switcher.classList.remove("visible");
  avatar.classList.remove("visible");
  avatar.removeAttribute("title");
  if (!active || !active.login || !active.token_present || tokenExpired(active)) {
    avatar.removeAttribute("src");
    headerSelect.removeAttribute("title");
    headerSelect.parentElement.removeAttribute("title");
    return;
  }
  const profileCount = usableAccounts().length;
  const switcherTitle = profileCount < 2
    ? "Add another PAT profile in Settings to enable account switching"
    : `Switch GitHub PAT profile. Active: ${active.login}`;
  switcher.classList.add("visible");
  switcher.classList.toggle("single-profile", profileCount < 2);
  avatar.onload = () => avatar.classList.add("visible");
  avatar.onerror = () => avatar.classList.remove("visible");
  avatar.alt = `${active.login} GitHub avatar`;
  avatar.src = `https://github.com/${encodeURIComponent(active.login)}.png?size=96`;
  avatar.title = `Signed in as ${active.login}`;
  headerSelect.title = switcherTitle;
  headerSelect.parentElement.title = switcherTitle;
}

// Escapes account metadata before rendering it into Settings controls.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Builds one safe profile option shared by the Settings and header account selectors.
function accountOptionMarkup(account) {
  const type = account.resource_owner_type === "Organization" ? "Organization" : "Personal";
  const actor = account.authenticated_login && account.authenticated_login !== account.login
    ? ` via @${account.authenticated_login}` : "";
  const expiration = tokenExpired(account) ? " — Expired" : "";
  const label = `${account.login} — ${type}${actor}${expiration}`;
  return `<option value="${escapeHtml(account.login)}">${escapeHtml(label)}</option>`;
}

// Renders the active-account select and the account state summary.
function renderAccounts() {
  const select = byId("account-select");
  const headerSelect = byId("header-account-select");
  const signedIn = signedInAccounts();
  const usable = usableAccounts();
  const active = activeAccount();
  const expired = tokenExpired(active);
  const optionMarkup = signedIn.length
    ? signedIn.map(accountOptionMarkup).join("")
    : '<option value="">No PAT profiles saved</option>';

  select.innerHTML = optionMarkup;
  headerSelect.innerHTML = usable.length
    ? usable.map(accountOptionMarkup).join("")
    : '<option value="">No usable PAT profiles</option>';
  select.value = active ? active.login : "";
  headerSelect.value = active ? active.login : "";
  select.disabled = !signedIn.length;
  headerSelect.disabled = usable.length < 2;
  byId("clear-account").disabled = !(active && active.token_present);
  byId("clear-account").textContent = "Remove token";
  byId("clone-use-token").checked = Boolean(active && active.token_present && !expired);
  byId("clone-use-token").disabled = !(active && active.token_present && !expired);

  const tokenLabel = expired ? "token expired" : active && active.token_present ? "token saved" : "token not saved";
  const stateLabel = active ? `@${active.login} PAT profile — ${tokenLabel}` : "No GitHub PAT profiles saved";
  const detail = active
    ? `Authenticated as @${active.authenticated_login}; commits use ${active.name} <${active.email}>`
    : "Add a resource-owner PAT profile to clone and push.";
  setText("token-state", stateLabel);
  setText("account-details", detail);
  const expirationStatus = byId("pat-expiration-status");
  const expirationLabel = tokenExpirationLabel(active);
  expirationStatus.hidden = !expirationLabel;
  expirationStatus.classList.toggle("danger", expired);
  expirationStatus.classList.toggle("success", Boolean(expirationLabel) && !expired);
  expirationStatus.textContent = expired
    ? `Expired ${expirationLabel}. Save a replacement PAT to restore GitHub access.`
    : expirationLabel ? `Expires ${expirationLabel}` : "";
  scheduleExpirationRefresh(active);
  renderHeaderAccount();
}

// Applies backend auth state and updates every control that depends on the active account.
function applyAuthState(auth) {
  authState = auth || { accounts: [], active_account: "" };
  renderAccounts();
}

// Notifies the main controller when account actions also returned refreshed settings.
function notifyAuthChanged(data) {
  if (authChangedRef && data.settings) {
    authChangedRef(data.settings);
  }
}

// Enables profile submission only when both the PAT value and its exact resource owner are present.
function updateTokenSubmitAvailability() {
  byId("save-account").disabled = !byId("token-input").value.trim()
    || !byId("pat-resource-owner").value.trim();
}

// Saves a PAT as a GitHub account after Python validates the token against GitHub.
async function saveAccount(event) {
  event.preventDefault();
  const tokenInput = byId("token-input");
  const token = tokenInput.value.trim();
  // Keyboard form submission can bypass a disabled submit button, so stop before invoking the native bridge.
  const resourceOwner = byId("pat-resource-owner").value.trim();
  if (!token || !resourceOwner) {
    updateTokenSubmitAvailability();
    tokenInput.focus();
    return;
  }
  tokenInput.value = "";
  updateTokenSubmitAvailability();
  try {
    const data = await runActionRef("saveAccount", {
      token,
      resource_owner: resourceOwner,
    }, "GitHub PAT profile saved");
    applyAuthState(data.auth);
    notifyAuthChanged(data);
  } catch (error) {
    // The shared action wrapper already reports the structured failure; contain it at the DOM event boundary.
    tokenInput.focus();
  }
}

// Switches the active account used by API calls and Git authentication.
async function selectAccount(event) {
  const login = event.currentTarget.value;
  if (!login) {
    return;
  }
  byId("account-select").disabled = true;
  byId("header-account-select").disabled = true;
  try {
    const data = await runActionRef("selectAccount", { login }, "Active GitHub account changed");
    applyAuthState(data.auth);
    notifyAuthChanged(data);
  } catch (error) {
    // Restore both selectors after the shared action wrapper reports an unavailable exact profile.
    renderAccounts();
  }
}

// Removes the active account token while keeping non-secret account and repository metadata.
async function clearAccount() {
  const login = activeLogin();
  if (!login) {
    return;
  }
  const data = await runActionRef("clearAccount", { account_login: login }, "GitHub token removed");
  applyAuthState(data.auth);
  notifyAuthChanged(data);
}

// Shows or hides the PAT setup guidance without sending any secret-bearing form data to Python.
function togglePatHelp() {
  if (byId("pat-help").hidden) {
    openPatHelp();
    return;
  }
  closePatHelp();
}

// Wraps the static PAT guidance content in a real modal panel with a visible close action.
function ensurePatHelpDialog() {
  const helpPanel = byId("pat-help");
  if (helpPanel.querySelector(".pat-help-panel")) return;

  const panel = document.createElement("div");
  const header = document.createElement("div");
  const closeButton = document.createElement("button");
  const originalNodes = Array.from(helpPanel.childNodes);
  const title = originalNodes.find((node) => node.nodeType === 1 && node.matches("label"));

  panel.className = "pat-help-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-labelledby", "pat-help-title");
  header.className = "pat-help-title-row";
  closeButton.id = "close-pat-help";
  closeButton.type = "button";
  closeButton.textContent = "Close";

  if (title) {
    title.id = "pat-help-title";
    header.appendChild(title);
  }
  header.appendChild(closeButton);
  panel.appendChild(header);
  originalNodes.forEach((node) => {
    if (node !== title) panel.appendChild(node);
  });
  addPatSetupAction(panel);
  helpPanel.appendChild(panel);
}

// Opens PAT setup and selects its editable owner so the user can replace the active-profile default immediately.
function openPatHelp() {
  const ownerInput = byId("pat-resource-owner");
  // Preserve an owner the user already entered while providing the active repository owner as a useful default.
  if (!ownerInput.value.trim()) {
    ownerInput.value = githubOwner();
  }
  updateTokenSubmitAvailability();
  byId("pat-help").hidden = false;
  byId("show-pat-help").setAttribute("aria-expanded", "true");
  ownerInput.focus();
  ownerInput.select();
}

// Closes the modal and restores the help button's expanded state.
function closePatHelp() {
  byId("pat-help").hidden = true;
  byId("show-pat-help").setAttribute("aria-expanded", "false");
}

// Closes the modal when the user clicks the backdrop or close button.
function handlePatHelpClick(event) {
  if (event.target.id === "pat-help" || event.target.id === "close-pat-help") {
    closePatHelp();
  }
}

// Returns the owner currently configured for the repository settings form.
function githubOwner() {
  if (!githubPayloadRef) {
    return activeLogin();
  }
  const payload = githubPayloadRef() || {};
  return String(payload.owner || "").trim() || activeLogin();
}

// Returns the resource owner explicitly entered for the new token, falling back to repository/account context.
function patResourceOwner() {
  return byId("pat-resource-owner").value.trim() || githubOwner();
}

// Builds GitHub's documented fine-grained PAT template URL for GitDesk repository access.
function gitdeskPatSetupUrl() {
  const params = new URLSearchParams({
    name: "GitDesk",
    description: "GitDesk repository, Pull Request, release, and GitHub Pages workflows",
    expires_in: "30",
    metadata: "read",
    contents: "write",
    pages: "write",
    administration: "write",
    actions: "read",
    deployments: "read",
    workflows: "write",
    pull_requests: "write",
  });
  const owner = patResourceOwner();
  if (owner) {
    params.set("target_name", owner);
  }
  return `https://github.com/settings/personal-access-tokens/new?${params.toString()}`;
}

// Opens the official GitHub token form with GitDesk's required repository permissions prefilled.
async function openGitdeskPatSetup() {
  await runActionRef("openGitHubUrl", { url: gitdeskPatSetupUrl() }, "GitDesk token setup opened");
}

// Adds an app-owned token setup action to the static PAT guidance modal.
function addPatSetupAction(panel) {
  const actionRow = document.createElement("div");
  const setupButton = document.createElement("button");

  actionRow.className = "button-row";
  setupButton.id = "open-gitdesk-pat-setup";
  setupButton.type = "button";
  setupButton.textContent = "Open prefilled GitDesk token setup";
  actionRow.appendChild(setupButton);
  panel.appendChild(actionRow);
}

// Binds account controls after the main app provides its native-action wrapper.
function bind(runAction, authChanged, options = {}) {
  runActionRef = runAction;
  authChangedRef = authChanged;
  githubPayloadRef = options.githubPayload || null;
  ensurePatHelpDialog();
  byId("account-form").addEventListener("submit", saveAccount);
  byId("token-input").addEventListener("input", updateTokenSubmitAvailability);
  byId("pat-resource-owner").addEventListener("input", updateTokenSubmitAvailability);
  byId("show-pat-help").addEventListener("click", togglePatHelp);
  byId("open-gitdesk-pat-setup").addEventListener("click", openGitdeskPatSetup);
  byId("pat-help").addEventListener("click", handlePatHelpClick);
  byId("account-select").addEventListener("change", selectAccount);
  byId("header-account-select").addEventListener("change", selectAccount);
  byId("clear-account").addEventListener("click", clearAccount);
  updateTokenSubmitAvailability();
}

// Publishes the small account API needed by app bootstrap and operation payloads.
window.GitDeskAccounts = {
  activeAccount,
  activeLogin,
  apply: applyAuthState,
  bind,
  // Returns copied non-secret profile metadata so repository controls cannot mutate authentication state.
  signedInProfiles() {
    return usableAccounts().map((account) => ({ ...account }));
  },
  payload() {
    return { account_login: activeLogin() };
  },
};
})();
