/*
  Owner-aware GitHub catalog rendering for personal and organization repositories.
*/

// Keeps GitHub owner discovery and catalog grouping separate from modal workflow actions.
(() => {
const renderHelpers = window.GitDeskRender;

// Fail during startup when the shared DOM helpers are unavailable instead of binding partial controls.
if (!renderHelpers) {
  throw new Error("GitDesk repository catalog dependencies did not load.");
}

const { byId } = renderHelpers;

// Escapes GitHub-provided metadata before inserting it into owner options or repository rows.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Returns de-duplicated owner records from the account, memberships, and accessible repositories.
function catalogOwners(context, repositories) {
  const owners = new Map();
  const accountLogin = String(context.accountLogin || "").trim();
  const activeProfile = (context.credentialProfiles || []).find((profile) => profile.login === accountLogin) || {};
  const profileType = String(activeProfile.resource_owner_type || "User");
  // The active PAT profile's resource owner remains first even when membership discovery is unavailable.
  if (accountLogin) {
    owners.set(accountLogin.toLowerCase(), { login: accountLogin, type: profileType });
  }
  // Saved profiles must appear even when the active token's repository response omits their owners.
  (context.credentialProfiles || []).forEach((profile) => {
    const login = String(profile.login || "").trim();
    // Invalid legacy metadata cannot create a usable owner selection.
    if (login) {
      owners.set(login.toLowerCase(), { login, type: profile.resource_owner_type || "User" });
    }
  });
  (context.organizations || []).forEach((organization) => {
    const login = String(organization.login || "").trim();
    // Empty membership records cannot produce a usable select option.
    if (login) {
      owners.set(login.toLowerCase(), { login, type: "Organization" });
    }
  });
  (repositories || []).forEach((repository) => {
    const login = String(repository.owner || "").trim();
    // Outside-collaborator repositories still need their owner represented in the Clone filter.
    if (login) {
      owners.set(login.toLowerCase(), { login, type: repository.owner_type || "Owner" });
    }
  });
  return Array.from(owners.values()).sort((left, right) => {
    // Pin the personal account first, then sort all other owners for predictable scanning.
    if (left.login === accountLogin) return -1;
    if (right.login === accountLogin) return 1;
    return left.login.localeCompare(right.login);
  });
}

// Builds owner options with type labels so personal and organization destinations are unambiguous.
function ownerOptions(owners) {
  return owners.map((owner) => {
    const suffix = owner.type === "Organization" ? " — Organization" : " — Personal";
    return `<option value="${escapeHtml(owner.login)}">${escapeHtml(owner.login + suffix)}</option>`;
  }).join("");
}

// Synchronizes Clone and Create New owner selectors without discarding the user's current selection.
function renderOwnerControls(context, repositories) {
  const owners = catalogOwners(context, repositories);
  const filter = byId("github-owner-filter");
  const currentFilter = filter.value;
  filter.innerHTML = `<option value="">All owners</option>${ownerOptions(owners)}`;
  filter.value = owners.some((owner) => owner.login === currentFilter) ? currentFilter : "";

  const createOwner = byId("new-repo-owner");
  const currentOwner = createOwner.value || context.accountLogin || "";
  const createOwners = (context.credentialProfiles || []).map((profile) => ({
    login: profile.login,
    type: profile.resource_owner_type || "User",
  }));
  createOwner.innerHTML = ownerOptions(createOwners);
  createOwner.value = createOwners.some((owner) => owner.login === currentOwner)
    ? currentOwner
    : context.accountLogin || "";

  const limited = context.organizationAccess === "repositories_only";
  const accessNote = byId("github-org-access-note");
  accessNote.textContent = limited
    ? "Repositories reflect this PAT, but GitHub blocked organization membership discovery. "
      + "A classic PAT needs read:org; organization policy or SSO may also restrict access."
    : "Only repositories authorized for this PAT appear. Organization policy, token permissions, "
      + "or SSO can limit results.";
  byId("new-repo-owner-note").textContent = "Each owner uses its own saved PAT profile.";
}

// Chooses a safe default local folder name from one repository record.
function defaultFolderName(repository) {
  return String(repository.name || repository.full_name || "repository").split("/").pop();
}

// Renders one cloneable GitHub repository row with privacy and lifecycle metadata.
function catalogRow(repository) {
  const privacy = repository.private ? "private" : "public";
  const fork = repository.fork ? " fork" : "";
  const archived = repository.archived ? " archived" : "";
  const disabled = repository.clone_url ? "" : "disabled";
  return `
    <div class="catalog-row">
      <div>
        <div class="row-title">${escapeHtml(repository.full_name || repository.name)}</div>
        <div class="row-meta">${escapeHtml(privacy + fork + archived)}</div>
        <div class="row-meta">${escapeHtml(repository.description || repository.default_branch || "")}</div>
      </div>
      <button class="clone-github-repo" type="button"
        data-clone-url="${escapeHtml(repository.clone_url || "")}"
        data-repository-owner="${escapeHtml(repository.owner || "")}"
        data-folder-name="${escapeHtml(defaultFolderName(repository))}" ${disabled}>Clone</button>
    </div>
  `;
}

// Renders repositories grouped by owner after applying the owner and text filters.
function renderCatalog(repositories, context) {
  const list = byId("github-repo-list");
  const textFilter = byId("github-repo-filter").value.trim().toLowerCase();
  const ownerFilter = byId("github-owner-filter").value.trim().toLowerCase();
  const visible = (repositories || []).filter((repository) => {
    const haystack = [repository.full_name, repository.description, repository.default_branch]
      .join(" ").toLowerCase();
    const matchesOwner = !ownerFilter || String(repository.owner || "").toLowerCase() === ownerFilter;
    return matchesOwner && (!textFilter || haystack.indexOf(textFilter) >= 0);
  });

  // Catalog actions require an authenticated account because HTTPS cloning uses its saved token.
  if (!context.accountLogin) {
    list.innerHTML = '<div class="empty-state">No active account</div>';
    return;
  }
  // Keep empty filters distinct from an API failure by explaining the PAT-aware result set.
  if (!visible.length) {
    list.innerHTML = '<div class="empty-state">No repositories available for these filters and PAT permissions</div>';
    return;
  }

  const groups = new Map();
  visible.forEach((repository) => {
    const owner = repository.owner || "Other";
    // Create each owner section lazily so no empty organization headings are rendered.
    if (!groups.has(owner)) groups.set(owner, []);
    groups.get(owner).push(repository);
  });
  list.innerHTML = Array.from(groups.entries()).map(([owner, records]) => `
    <section class="catalog-owner-group" aria-label="${escapeHtml(owner)} repositories">
      <div class="catalog-owner-title">${escapeHtml(owner)}</div>
      ${records.map(catalogRow).join("")}
    </section>
  `).join("");
}

// Shows the GitHub remote inferred from a selected local repository without changing that remote.
function renderExistingRemote(repository, context) {
  const preview = byId("existing-repo-remote");
  const owner = String((repository || {}).github_owner || "").trim();
  const repo = String((repository || {}).github_repo || "").trim();
  // A cleared or manually edited path has no verified origin metadata yet.
  if (!repository) {
    preview.innerHTML = "Choose a local Git repository to inspect its GitHub origin.";
    return;
  }
  // Local repositories without a supported GitHub origin remain valid local-only entries.
  if (!owner || !repo) {
    preview.innerHTML = "No GitHub origin detected. GitDesk will add this as a local-only repository.";
    return;
  }
  const activeProfile = (context.credentialProfiles || []).find((profile) => profile.login === owner) || {};
  const activeProfileIsOrganization = activeProfile.resource_owner_type === "Organization";
  const isOrganization = activeProfileIsOrganization
    || (context.organizations || []).some((organization) => organization.login === owner);
  const ownerType = isOrganization ? "Organization" : owner === context.accountLogin ? "Personal" : "GitHub owner";
  preview.innerHTML = `<strong>${escapeHtml(owner + "/" + repo)}</strong>`
    + `<small>${escapeHtml(ownerType)} origin detected</small>`;
}

window.GitDeskRepositoryCatalog = {
  renderCatalog,
  renderExistingRemote,
  renderOwnerControls,
};
})();
