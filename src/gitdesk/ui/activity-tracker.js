/*
  Project Hub activity range controls and navigable factual Project Activity Atlas.
*/

// Keeps visualization state separate from the Project Hub workflow controller.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const viewportModule = window.GitDeskActivityViewport;

if (!nativeBridge || !renderHelpers || !viewportModule) {
  throw new Error("GitDesk activity tracker dependencies did not load.");
}

const { callNative } = nativeBridge;
const { appendActivity, byId, setBusy, showMessage } = renderHelpers;
const { createActivityViewport } = viewportModule;

// The palette stays vivid against both themes while assigning stable colors by project order.
const PROJECT_COLORS = [
  "#6fffd2", "#ff6fb5", "#ffd166", "#73a7ff", "#b58cff", "#ff826e", "#65e6ff", "#9cff6f",
];

// Tracker state retains factual selection and delegates view interaction without rescanning Git history.
const state = {
  payload: null,
  selectedKey: "",
  viewport: null,
  bound: false,
  refreshPromise: null,
  announceRefresh: false,
};

// Escapes project and date labels before they enter generated HTML or SVG markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Formats an ISO date at midday so timezone conversion cannot move it to an adjacent calendar day.
function formatDate(value) {
  const parsed = new Date(`${value}T12:00:00`);
  return Number.isNaN(parsed.getTime()) ? String(value || "") : parsed.toLocaleDateString(undefined, {
    weekday: "short",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// Formats the factual commit timestamp in the user's locale while preserving invalid source text visibly.
function formatTimestamp(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value || "Unknown") : parsed.toLocaleString();
}

// Assigns one palette color to each project in the current response.
function projectMap(payload) {
  const map = {};
  (payload.projects || []).forEach((project, index) => {
    map[project.id] = { ...project, color: PROJECT_COLORS[index % PROJECT_COLORS.length] };
  });
  return map;
}

// Flattens normalized activity records so every rendered artifact has one factual backend source.
function activitiesFromPayload(payload) {
  return (payload.days || []).flatMap((day) => (day.activities || []).map((activity) => ({
    ...activity,
    date: day.date,
  })));
}

// Keeps activity selection stable across refreshes using backend ids derived from factual source records.
function activityKey(activity) {
  return `${activity.project_id}:${activity.id}`;
}

// Groups factual activity into owning active projects so labels live inside the graphic.
function activeProjectGroups(payload, projects) {
  const groupedActivities = {};
  activitiesFromPayload(payload).forEach((activity) => {
    if (!groupedActivities[activity.project_id]) groupedActivities[activity.project_id] = [];
    groupedActivities[activity.project_id].push(activity);
  });
  return (payload.projects || []).filter((project) => groupedActivities[project.id]).map((project) => ({
    ...projects[project.id],
    activities: groupedActivities[project.id],
  }));
}

// Builds one labeled project-work artifact with its core facts visible before interaction.
function activityArtifactMarkup(activity, color) {
  const title = activity.title || "Project activity";
  const subtitle = activity.subtitle || activity.project_name || "";
  const label = `${title}, ${subtitle}, ${formatTimestamp(activity.occurred_at)}`;
  return `
    <button class="activity-work-artifact" type="button" data-activity-key="${escapeHtml(activityKey(activity))}"
      data-activity-kind="${escapeHtml(activity.kind)}" style="--project-color:${color}"
      aria-label="${escapeHtml(label)}" aria-pressed="false">
      <span class="activity-artifact-kind">${escapeHtml(activity.kind_label || "Activity")}</span>
      <span class="activity-artifact-copy">
        <strong title="${escapeHtml(title)}">${escapeHtml(title)}</strong>
        <span>${escapeHtml(subtitle)}</span>
        <span>
          <time datetime="${escapeHtml(activity.occurred_at)}">
            ${escapeHtml(formatTimestamp(activity.occurred_at))}</time>
          <code>${escapeHtml(activity.short_code)}</code></span>
      </span>
    </button>
  `;
}

// Builds a self-identifying project space whose work artifacts need no external color legend.
function projectSpaceMarkup(group, x, y, width, height) {
  const commitCount = group.activities.filter((activity) => activity.kind === "commit").length;
  const localCount = group.activities.length - commitCount;
  const artifacts = group.activities.map((activity) => {
    return activityArtifactMarkup(activity, group.color);
  }).join("");
  return `
    <foreignObject class="activity-project-object" x="${x}" y="${y}" width="${width}" height="${height}">
      <article xmlns="http://www.w3.org/1999/xhtml" class="activity-project-space"
        style="--project-color:${group.color}">
        <header>
          <span class="activity-project-marker" aria-hidden="true"></span>
          <div><small>Active project</small><strong>${escapeHtml(group.name)}</strong></div>
          <span>
            ${group.activities.length} activities &middot; ${localCount} local &middot; ${commitCount} commits
          </span>
        </header>
        <div class="activity-artifact-list">${artifacts}</div>
      </article>
    </foreignObject>
  `;
}

// Renders a masonry-like activity atlas with factual project identity embedded in every space.
function renderAtlas(payload, projects) {
  const container = byId("activity-atlas");
  const groups = activeProjectGroups(payload, projects);
  if (!groups.length) {
    state.viewport.clear();
    container.innerHTML = '<div class="empty-state">No project activity exists in this range.</div>';
    return;
  }
  const width = Math.max(760, container.clientWidth || 760);
  const columnCount = width >= 1400 ? 3 : width >= 900 ? 2 : 1;
  const gap = 26;
  const padding = 26;
  const panelWidth = (width - padding * 2 - gap * (columnCount - 1)) / columnCount;
  const columnHeights = Array(columnCount).fill(padding + 52);
  const spaces = groups.map((group) => {
    const column = columnHeights.indexOf(Math.min(...columnHeights));
    const panelHeight = 88 + group.activities.length * 82;
    const x = padding + column * (panelWidth + gap);
    const y = columnHeights[column];
    columnHeights[column] += panelHeight + gap;
    return projectSpaceMarkup(group, x, y, panelWidth, panelHeight);
  }).join("");
  const visibleHeight = Math.max(390, container.clientHeight || 440);
  const contentHeight = Math.max(visibleHeight, Math.max(...columnHeights) + padding);
  const totals = payload.totals || {};
  const atlasLabel = `${totals.activities || 0} activities across ${totals.projects || 0} active projects`;
  const streakContinuation = totals.current_streak_open ? "+" : "";
  const streakLabel = `Visible streak ${totals.current_streak || 0}${streakContinuation} days &middot; `
    + `visible best ${totals.longest_streak || 0} days`;
  container.innerHTML = `
    <div class="activity-atlas-hud">
      <strong>${escapeHtml(atlasLabel)}</strong>
      <span>${streakLabel} &middot; scroll atlas &middot; Ctrl/Cmd + scroll to zoom</span>
      <button type="button" data-activity-reset>Reset view</button>
    </div>
    <div class="activity-atlas-zoom-controls" role="group" aria-label="Activity Atlas zoom controls">
      <button type="button" data-activity-zoom-in aria-label="Zoom in" title="Zoom in">+</button>
      <button type="button" data-activity-zoom-out aria-label="Zoom out" title="Zoom out">&minus;</button>
    </div>
    <svg class="activity-atlas-svg" viewBox="0 0 ${width} ${visibleHeight}" role="group" tabindex="0"
      aria-label="${escapeHtml(atlasLabel)}">
      ${spaces}
    </svg>
  `;
  state.viewport.setContentSize(width, contentHeight, visibleHeight);
  if (!activitiesFromPayload(payload).some((activity) => activityKey(activity) === state.selectedKey)) {
    state.selectedKey = "";
  }
  renderArtifactPopover(payload);
}

// Finds the explicitly selected factual activity without creating a detached default inspector.
function selectedActivity(payload) {
  const activities = activitiesFromPayload(payload);
  return activities.find((activity) => activityKey(activity) === state.selectedKey) || null;
}

// Marks the selected artifact so visual state and assistive state agree with the in-graphic disclosure.
function markSelectedArtifact() {
  byId("activity-atlas").querySelectorAll("[data-activity-key]").forEach((artifact) => {
    const selected = artifact.dataset.activityKey === state.selectedKey;
    artifact.classList.toggle("selected", selected);
    artifact.setAttribute("aria-pressed", String(selected));
  });
}

// Opens the selected activity as a floating dossier inside the atlas rather than a bottom section.
function renderArtifactPopover(payload) {
  const container = byId("activity-atlas");
  const existing = container.querySelector("[data-activity-popover]");
  if (existing) existing.remove();
  const activity = selectedActivity(payload);
  if (!activity) {
    markSelectedArtifact();
    return;
  }
  const facts = (activity.facts || []).filter((fact) => fact.value).map((fact) => `
    <div><dt>${escapeHtml(fact.label)}</dt><dd>${escapeHtml(fact.value)}</dd></div>
  `).join("");
  container.insertAdjacentHTML("beforeend", `
    <aside class="activity-artifact-popover" data-activity-popover>
      <button type="button" data-activity-popover-close aria-label="Close activity details">Close</button>
      <small>${escapeHtml(activity.project_name)} / ${escapeHtml(activity.short_code)}</small>
      <strong>${escapeHtml(activity.title || "Project activity")}</strong>
      <time datetime="${escapeHtml(activity.occurred_at)}">${escapeHtml(formatTimestamp(activity.occurred_at))}</time>
      <dl>${facts}</dl>
    </aside>
  `);
  markSelectedArtifact();
}

// Applies a complete backend response to range controls, the factual atlas, and any scan warnings.
function render(payload) {
  state.payload = payload;
  if (window.GitDeskSyncChains) window.GitDeskSyncChains.applyActivityNotifications(payload);
  const range = payload.range || {};
  const projects = projectMap(payload);
  byId("activity-range").value = range.preset || "month";
  byId("activity-custom-start").min = range.first_use || "";
  byId("activity-custom-start").max = range.end || "";
  if (!byId("activity-custom-start").value) byId("activity-custom-start").value = range.start || "";
  byId("activity-custom-start").disabled = range.preset !== "custom";
  byId("activity-range-label").textContent = `${formatDate(range.start)} to ${formatDate(range.end)}`;
  renderAtlas(payload, projects);
  byId("activity-warnings").textContent = (payload.warnings || []).join(" ");
}

// Loads the selected range with shared busy, status, Activity, and error feedback.
function refresh(announce = true) {
  state.announceRefresh = state.announceRefresh || announce;
  // Startup and Local Mode can request the same expensive scan together, so every caller shares one bridge request.
  if (state.refreshPromise) {
    return state.refreshPromise;
  }
  setBusy(true);
  showMessage("");
  state.refreshPromise = callNative("projectActivity", {
    preset: byId("activity-range").value,
    start: byId("activity-custom-start").value,
  }).then((payload) => {
    render(payload);
    if (state.announceRefresh) appendActivity("Project activity refreshed");
    return payload;
  }).catch((error) => {
    const message = error.message || "Project activity could not be loaded.";
    console.error("Project activity refresh failed", error);
    showMessage(message, true);
    appendActivity(message, true);
    throw error;
  }).finally(() => {
    state.refreshPromise = null;
    state.announceRefresh = false;
    setBusy(false);
  });
  return state.refreshPromise;
}

// Enables the custom date only for that mode and refreshes rolling presets immediately.
function handleRangeChange() {
  const custom = byId("activity-range").value === "custom";
  byId("activity-custom-start").disabled = !custom;
  if (!custom) refresh().catch(() => {});
}

// Toggles a clicked or keyboard-activated artifact without requesting Git history again.
function selectActivity(target) {
  if (!target || !state.payload) return;
  const nextKey = target.dataset.activityKey || "";
  state.selectedKey = state.selectedKey === nextKey ? "" : nextKey;
  renderArtifactPopover(state.payload);
}

// Handles the atlas's embedded reset and close controls without adding persistent external UI.
function handleAtlasControl(event) {
  if (event.target.closest("[data-activity-reset]")) {
    state.viewport.reset();
  } else if (event.target.closest("[data-activity-zoom-in]")) {
    state.viewport.zoomIn();
  } else if (event.target.closest("[data-activity-zoom-out]")) {
    state.viewport.zoomOut();
  } else if (event.target.closest("[data-activity-popover-close]")) {
    state.selectedKey = "";
    renderArtifactPopover(state.payload);
  }
}

// Binds controls after Project Hub injects the tracker markup, then performs the quiet initial load.
function bind() {
  if (state.bound) return;
  state.bound = true;
  byId("activity-range").addEventListener("change", handleRangeChange);
  byId("activity-apply-range").addEventListener("click", () => refresh().catch(() => {}));
  byId("activity-refresh").addEventListener("click", () => refresh().catch(() => {}));
  state.viewport = createActivityViewport(byId("activity-atlas"), selectActivity);
  byId("activity-atlas").addEventListener("click", handleAtlasControl);
  refresh(false).catch(() => {});
}

window.GitDeskActivityTracker = { bind, refresh };
})();
