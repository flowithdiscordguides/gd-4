/*
  Shared successful deployment-site control for GitHub Pages and Actions surfaces.
*/

// Keeps successful deployment markup and click-target parsing identical wherever the result appears.
(() => {
// Escapes authoritative deployment URLs before inserting them into generated markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Returns the canonical successful deployment button for an already-approved URL.
function render(url) {
  if (!url) return "";
  const safeUrl = escapeHtml(url);
  return `
    <button class="deployment-site-link" type="button" data-deployment-site-url="${safeUrl}"
      title="Open ${safeUrl} in your default browser">
      <span class="deployment-site-mark" aria-hidden="true">✓</span>
      <span class="deployment-site-copy">
        <strong>Visit deployed site</strong>
        <small>${safeUrl}</small>
      </span>
    </button>
  `;
}

// Resolves the canonical deployment URL from a delegated click without owning the native action boundary.
function urlFromEvent(event) {
  const target = event && event.target;
  const button = target && typeof target.closest === "function"
    ? target.closest("[data-deployment-site-url]")
    : null;
  return button ? button.dataset.deploymentSiteUrl || "" : "";
}

// Publishes the dependency-free control consumed by both deployment-state controllers.
window.GitDeskDeploymentSiteControl = { render, urlFromEvent };
})();
