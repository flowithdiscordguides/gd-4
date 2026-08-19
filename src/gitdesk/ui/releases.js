/*
  GitHub Releases panel manager with draft review and publish support.
*/

// Keeps release form state separate from the main controller so app.js stays below the file-size ceiling.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk release dependencies did not load.");
}

const {
  byId,
  setText,
  setValue,
} = renderHelpers;

let runActionRef = null;
let githubPayloadRef = null;
const state = {
  releases: [],
  selectedRelease: null,
};

// Copies form data into a GitHub payload without using object spread in older WebView runtimes.
function withRelease(basePayload, release) {
  const payload = {};
  Object.keys(basePayload || {}).forEach((key) => {
    payload[key] = basePayload[key];
  });
  payload.release = release;
  return payload;
}

// Escapes release metadata before injecting release cards and asset rows.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Formats GitHub timestamps in the user's locale for quick release review.
function formatDateTime(value) {
  const parsed = new Date(value || "");
  if (Number.isNaN(parsed.getTime())) {
    return "Not published";
  }
  return parsed.toLocaleString();
}

// Formats release asset sizes without pulling in a separate dependency.
function formatSize(bytes) {
  const size = Number(bytes || 0);
  if (size >= 1024 * 1024) {
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }
  if (size >= 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${size} B`;
}

// Finds a release from the currently rendered list by its numeric GitHub id.
function releaseById(releaseId) {
  const idText = String(releaseId || "");
  return state.releases.find((release) => String(release.id) === idText) || null;
}

// Returns the selected release-label mode from the radio group.
function selectedLabelMode() {
  const selected = document.querySelector('input[name="release-label"]:checked');
  return selected ? selected.value : "latest";
}

// Applies release label settings to the API fields GitHub expects.
function releaseLabelPayload() {
  const mode = selectedLabelMode();
  return {
    prerelease: mode === "prerelease",
    make_latest: mode === "latest" ? "true" : "false",
  };
}

// Renders uploaded release assets so drafts can be reviewed before publication.
function renderAssets(release) {
  const assets = release && release.assets ? release.assets : [];
  if (!assets.length) {
    return '<div class="empty-state">No assets attached</div>';
  }
  return assets.map((asset) => `
    <div class="release-asset-row">
      <strong>${escapeHtml(asset.name)}</strong>
      <span>${escapeHtml(formatSize(asset.size))}</span>
      <span>${escapeHtml(asset.state || "uploaded")}</span>
    </div>
  `).join("");
}

// Writes one release into the edit/publish form.
function applyReleaseToForm(release) {
  state.selectedRelease = release || null;
  setValue("release-tag", release ? release.tag_name : "");
  setValue("release-title", release ? release.name : "");
  setValue("release-target", release ? release.target_commitish : "");
  setValue("release-body", release ? release.body : "");
  byId("release-notes").checked = false;
  byId("release-label-latest").checked = !(release && release.prerelease);
  byId("release-label-prerelease").checked = Boolean(release && release.prerelease);
  byId("release-label-none").checked = false;
  byId("release-assets").innerHTML = renderAssets(release);
  setText("release-form-summary", release ? `Editing ${release.tag_name}` : "New release");
}

// Renders the release list and keeps draft rows clickable for GitHub.com-like draft review.
function renderReleases(releases) {
  const list = byId("releases-list");
  state.releases = releases || [];
  setText("releases-summary", `${state.releases.length} releases`);

  if (!state.releases.length) {
    list.innerHTML = '<div class="empty-state">No releases loaded</div>';
    applyReleaseToForm(null);
    return;
  }

  list.innerHTML = state.releases.map((release) => {
    const stateText = release.draft ? "draft" : release.prerelease ? "prerelease" : "published";
    const pillClass = release.draft ? "warning" : release.prerelease ? "warning" : "success";
    const timeValue = release.published_at || release.created_at;
    return `
      <button class="release-row release-open" type="button" data-release-id="${escapeHtml(release.id)}">
        <span>
          <span class="row-title">${escapeHtml(release.tag_name)} - ${escapeHtml(release.name)}</span>
          <span class="row-meta">${escapeHtml(formatDateTime(timeValue))}</span>
        </span>
        <span class="status-pill ${pillClass}">${stateText}</span>
      </button>
    `;
  }).join("");
}

// Opens a release row in the form without making another network request.
function openRelease(event) {
  const button = event.target.closest(".release-open");
  if (!button) {
    return;
  }
  applyReleaseToForm(releaseById(button.dataset.releaseId));
}

// Loads releases from GitHub for the configured owner/repo pair.
async function refreshReleases() {
  const releases = await runActionRef("listReleases", githubPayloadRef(), "Releases refreshed");
  renderReleases(releases);
  if (window.GitDeskReleaseAlerts) {
    window.GitDeskReleaseAlerts.clearReleaseReady();
  }
}

// Refreshes releases after tab activation without turning a failed auto-load into an unhandled error.
function refreshOnOpen() {
  refreshReleases().catch(() => {});
}

// Builds the release payload for creating a release or publishing the selected draft.
function formPayload() {
  const label = releaseLabelPayload();
  return {
    id: state.selectedRelease ? state.selectedRelease.id : "",
    tag_name: byId("release-tag").value,
    title: byId("release-title").value,
    target_commitish: byId("release-target").value,
    body: byId("release-body").value,
    draft: false,
    prerelease: label.prerelease,
    make_latest: label.make_latest,
    generate_release_notes: byId("release-notes").checked,
  };
}

// Publishes the visible release form, using PATCH when a draft row is selected.
async function publishRelease(event) {
  event.preventDefault();
  const repository = githubPayloadRef();
  const releaseData = formPayload();
  const published = await runActionRef(
    "publishRelease",
    withRelease(repository, releaseData),
    "Release published",
  );
  byId("release-form").reset();
  applyReleaseToForm(null);
  await refreshReleases().catch(() => {});
  if (window.GitDeskSyncStageThree) {
    window.GitDeskSyncStageThree.prompt(repository.path, published, {
      tagName: releaseData.tag_name,
      artifactReleaseEligible: !releaseData.prerelease && releaseData.make_latest === "true",
    });
  }
}

// Binds release controls after app.js supplies the native action wrapper.
function bind(options) {
  runActionRef = options.runAction;
  githubPayloadRef = options.githubPayload;
  byId("refresh-releases").addEventListener("click", refreshReleases);
  byId("releases-list").addEventListener("click", openRelease);
  byId("release-form").addEventListener("submit", publishRelease);
  byId("release-new").addEventListener("click", () => applyReleaseToForm(null));
  document.querySelector('.tab-button[data-tab="releases"]').addEventListener("click", () => {
    window.setTimeout(refreshOnOpen, 0);
  });
  applyReleaseToForm(null);
}

// Publishes the small API used by app.js and future release refresh hooks.
window.GitDeskReleases = {
  bind,
  refreshReleases,
};
})();
