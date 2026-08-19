/*
  GitHub Pages deployment-result renderer for the selected Actions run.
*/

// Exposes one escaped renderer so every Actions detail pane uses identical success and failure semantics.
(() => {
let runActionRef = null;
const deploymentSiteControl = window.GitDeskDeploymentSiteControl;

if (!deploymentSiteControl) {
  throw new Error("GitDesk Actions deployment dependencies did not load.");
}

// Escapes GitHub-provided status text and URLs before rendering the result banner.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Returns a native-browser button only for the selected run's authoritative successful Pages deployment.
function render(deployment) {
  const state = deployment && deployment.state ? deployment.state : "";
  const url = deployment && deployment.url ? deployment.url : "";
  if (state === "success" && url) {
    return deploymentSiteControl.render(url);
  }
  if (state === "failure") {
    return `
      <span class="actions-pages-result danger" role="status">
        <span class="actions-pages-mark" aria-hidden="true">×</span>
        <span>Page deployment failed</span>
      </span>
    `;
  }
  if (state === "building") {
    return '<span class="actions-pages-result building">Page deployment in progress</span>';
  }
  if (state === "unavailable") {
    return `
      <span class="actions-pages-result unavailable">
        ${escapeHtml(deployment.error || "Page deployment status unavailable")}
      </span>
    `;
  }
  return "";
}

// Stores the native action boundary supplied by the Actions detail controller.
function install(runAction) {
  runActionRef = runAction;
}

// Opens a successful Pages target through the operating system's default-browser service.
function handleClick(event) {
  const url = deploymentSiteControl.urlFromEvent(event);
  if (!url || !runActionRef) return false;
  runActionRef(
    "openExternalUrl",
    { url },
    "Published site opened in your default browser",
  ).catch(() => {});
  return true;
}

// Publishes the renderer consumed by actions-detail.js.
window.GitDeskActionsDeployment = { handleClick, install, render };
})();
