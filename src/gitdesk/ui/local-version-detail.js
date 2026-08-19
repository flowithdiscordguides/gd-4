/*
  Version-list and selected-version inspector rendering for the Local Mode master-detail workspace.
*/

// Keeps version-specific presentation isolated from Local Mode's controller and general markup renderer.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk Local Mode version-detail dependencies did not load.");
}

const { byId, setText } = renderHelpers;
let onDeleteVersion = null;
let bound = false;

// Escapes physical folder values before inserting them into the selectable version-list markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Returns the established inline trashcan used for destructive row actions.
function trashIcon() {
  return `
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
      <path d="M4 7h16"></path>
      <path d="M10 11v6"></path>
      <path d="M14 11v6"></path>
      <path d="M6 7l1 14h10l1-14"></path>
      <path d="M9 7V4h6v3"></path>
    </svg>
  `;
}

// Scrolls only the version viewport enough to reveal its selected row without moving the surrounding page.
function revealActiveRow(list) {
  const activeRow = list.querySelector(".local-version-row.active");
  if (!activeRow) {
    return;
  }
  requestAnimationFrame(() => {
    if (!activeRow.isConnected) {
      return;
    }
    const listBounds = list.getBoundingClientRect();
    const rowBounds = activeRow.getBoundingClientRect();
    if (rowBounds.top < listBounds.top) {
      list.scrollTop -= listBounds.top - rowBounds.top;
    } else if (rowBounds.bottom > listBounds.bottom) {
      list.scrollTop += rowBounds.bottom - listBounds.bottom;
    }
  });
}

// Renders every physical version under the active feature, including selection and empty states.
function renderList(localState, project, feature) {
  const list = byId("local-version-list");
  if (!project) {
    list.innerHTML = '<div class="empty-state">No project selected</div>';
    return;
  }
  if (!feature) {
    list.innerHTML = '<div class="empty-state">No feature selected</div>';
    setText("local-summary", `${project.name} - no feature selected`);
    return;
  }

  const versions = feature.versions || [];
  setText("local-summary", `${project.name} / ${feature.name} - ${versions.length} versions`);
  if (!versions.length) {
    list.innerHTML = '<div class="empty-state">No version folders</div>';
    return;
  }
  list.innerHTML = versions.map((version) => {
    const active = version.path === localState.active_version ? " active" : "";
    return `
      <div class="local-version-listing${active}">
        <button class="local-version-row${active}" type="button" data-path="${escapeHtml(version.path)}">
          <strong>${escapeHtml(version.name)}</strong>
        </button>
        <button class="local-version-delete icon-button" type="button"
          data-delete-version-path="${escapeHtml(version.path)}" data-version-name="${escapeHtml(version.name)}"
          aria-label="Delete ${escapeHtml(version.name)}" title="Delete version">
          ${trashIcon()}
        </button>
      </div>
    `;
  }).join("");
  revealActiveRow(list);
}

// Routes the exact row path to the deletion controller while preventing the row-selection handler from running.
function handleListClick(event) {
  const button = event.target.closest("[data-delete-version-path]");
  if (!button || !onDeleteVersion) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
  const versionName = button.dataset.versionName || "this version";
  onDeleteVersion(button.dataset.deleteVersionPath || "", versionName, button);
}

// Renders factual project, feature, order, and path context for the currently selected version.
function renderDetail(project, feature, version) {
  const emptyState = byId("local-version-detail-empty");
  const content = byId("local-version-detail-content");
  const versions = feature ? feature.versions || [] : [];
  const versionIndex = version ? versions.findIndex((item) => item.path === version.path) : -1;
  const hasVersion = Boolean(project && feature && version && versionIndex >= 0);
  emptyState.hidden = hasVersion;
  content.hidden = !hasVersion;
  if (!hasVersion) {
    return;
  }

  setText("local-selected-version-name", version.name);
  setText("local-selected-version-order", `${versionIndex + 1} of ${versions.length}`);
  setText("local-selected-version-feature", feature.name);
  setText("local-selected-version-project", project.name);
  setText("local-selected-version-path", version.path);
  byId("local-selected-version-path").title = version.path;
  const resources = version.shared_resources || [];
  byId("local-selected-version-resources").innerHTML = resources.length
    ? resources.map((resource) => `
      <div class="local-version-resource-row">
        <span>
          ${escapeHtml(resource.name)}
          ${resource.legacy
            ? `<small>${escapeHtml(resource.tracking_message)}</small>`
            : resource.update_available
              ? `<small>${escapeHtml(resource.latest_version_label)} available</small>` : ""}
        </span>
        <strong>${escapeHtml(resource.version_label)}</strong>
      </div>
    `).join("")
    : '<p class="local-version-resource-empty">No tracked Shared Resources</p>';
}

// Updates the master list and its selected-version inspector from one coherent Local Mode snapshot.
function render(localState, project, feature, version) {
  renderList(localState, project, feature);
  renderDetail(project, feature, version);
}

// Binds the persistent list container once while allowing its controller callback to refresh.
function bind(options) {
  onDeleteVersion = options && options.onDeleteVersion;
  if (bound) {
    return;
  }
  bound = true;
  byId("local-version-list").addEventListener("click", handleListClick);
}

window.GitDeskLocalVersionDetail = { bind, render, trashIcon };
})();
