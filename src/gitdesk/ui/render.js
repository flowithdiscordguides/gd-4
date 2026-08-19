/*
  Rendering helpers for GitDesk's plain HTML frontend.
*/

// Keeps render helpers private while publishing a deliberate API for the controller.
(() => {
// Reads an element by id and fails loudly during development if the markup changes.
function byId(id) {
  const element = document.getElementById(id);
  if (!element) {
    throw new Error(`Missing element: ${id}`);
  }
  return element;
}

// Sets text content while normalizing nullish values to an empty string.
function setText(id, value) {
  byId(id).textContent = value == null ? "" : String(value);
}

// Sets an input value while avoiding the string "undefined" in form controls.
function setValue(id, value) {
  byId(id).value = value == null ? "" : String(value);
}

// Escapes data before inserting it through template strings.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Interactive controls use an app-owned tooltip so hover timing is deterministic across desktop WebViews.
const TOOLTIP_DELAY_MS = 200;
const TOOLTIP_SELECTOR = [
  "button:is([title], [data-gitdesk-tooltip])",
  "select:is([title], [data-gitdesk-tooltip])",
  "[role='button']:is([title], [data-gitdesk-tooltip])",
  "summary:is([title], [data-gitdesk-tooltip])",
].join(",");
let tooltipTimer = 0;
let tooltipTarget = null;
let tooltipElement = null;

// Returns the titled interactive ancestor represented by a pointer or focus event target.
function tooltipControl(node) {
  return node instanceof Element ? node.closest(TOOLTIP_SELECTOR) : null;
}

// Creates one body-level tooltip portal so card and panel overflow cannot clip its content.
function ensureTooltipElement() {
  if (tooltipElement) {
    return tooltipElement;
  }
  tooltipElement = document.createElement("div");
  tooltipElement.id = "gitdesk-tooltip";
  tooltipElement.className = "gitdesk-tooltip";
  tooltipElement.setAttribute("role", "tooltip");
  tooltipElement.hidden = true;
  document.body.append(tooltipElement);
  return tooltipElement;
}

// Restores the native title only after the pointer or focus leaves, preventing a delayed duplicate tooltip.
function restoreTooltipTitle(target) {
  if (!target || !target.dataset.gitdeskTooltip) {
    return;
  }
  if (!target.hasAttribute("title")) {
    target.title = target.dataset.gitdeskTooltip;
  }
  delete target.dataset.gitdeskTooltip;
}

// Hides the shared tooltip and returns its target to normal accessible markup.
function hideTooltip() {
  window.clearTimeout(tooltipTimer);
  tooltipTimer = 0;
  if (tooltipElement) {
    tooltipElement.removeAttribute("data-visible");
    tooltipElement.hidden = true;
  }
  restoreTooltipTitle(tooltipTarget);
  tooltipTarget = null;
}

// Positions the portal above its control when possible and below it near the top viewport edge.
function positionTooltip(target, tooltip) {
  const targetRect = target.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();
  const margin = 8;
  const left = Math.min(
    Math.max(targetRect.left + (targetRect.width - tooltipRect.width) / 2, margin),
    window.innerWidth - tooltipRect.width - margin,
  );
  let top = targetRect.top - tooltipRect.height - margin;
  if (top < margin) {
    top = targetRect.bottom + margin;
  }
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${Math.min(top, window.innerHeight - tooltipRect.height - margin)}px`;
}

// Updates tooltip text without reviving a native title while the app tooltip owns the control.
function setTooltipText(target, text) {
  if (!target) {
    return;
  }
  const nextText = String(text || "");
  if (target === tooltipTarget && target.dataset.gitdeskTooltip !== undefined) {
    if (!nextText) {
      hideTooltip();
      target.removeAttribute("title");
      return;
    }
    target.dataset.gitdeskTooltip = nextText;
    target.removeAttribute("title");
    if (tooltipElement && !tooltipElement.hidden) {
      tooltipElement.textContent = nextText;
      positionTooltip(target, tooltipElement);
    }
    return;
  }
  if (nextText) {
    target.title = nextText;
    return;
  }
  target.removeAttribute("title");
}

// Reveals the current target only if it remains connected after the short hover delay.
function showTooltip(target) {
  if (tooltipTarget !== target || !target.isConnected) {
    return;
  }
  const text = target.dataset.gitdeskTooltip || "";
  if (!text) {
    hideTooltip();
    return;
  }
  const tooltip = ensureTooltipElement();
  tooltip.textContent = text;
  tooltip.hidden = false;
  positionTooltip(target, tooltip);
  tooltip.setAttribute("data-visible", "");
}

// Suppresses the browser title immediately and schedules the app tooltip within the requested 0.3-second ceiling.
function scheduleTooltip(target) {
  if (!target || target === tooltipTarget) {
    return;
  }
  hideTooltip();
  const text = target.getAttribute("title") || "";
  if (!text) {
    return;
  }
  tooltipTarget = target;
  target.dataset.gitdeskTooltip = text;
  target.removeAttribute("title");
  tooltipTimer = window.setTimeout(() => showTooltip(target), TOOLTIP_DELAY_MS);
}

// Routes pointer hover through the closest titled control and ignores movement among its icon children.
function handleTooltipPointerOver(event) {
  scheduleTooltip(tooltipControl(event.target));
}

// Ends pointer-owned tooltip state only when the pointer leaves the complete control.
function handleTooltipPointerOut(event) {
  const relatedControl = tooltipControl(event.relatedTarget);
  if (relatedControl === tooltipTarget || document.activeElement === tooltipTarget) {
    return;
  }
  hideTooltip();
}

// Gives keyboard focus the same fast tooltip behavior as pointer hover.
function handleTooltipFocusIn(event) {
  scheduleTooltip(tooltipControl(event.target));
}

// Removes keyboard-owned tooltip state after focus leaves the represented control.
function handleTooltipFocusOut(event) {
  if (tooltipControl(event.relatedTarget) === tooltipTarget) {
    return;
  }
  hideTooltip();
}

document.addEventListener("pointerover", handleTooltipPointerOver);
document.addEventListener("pointerout", handleTooltipPointerOut);
document.addEventListener("focusin", handleTooltipFocusIn);
document.addEventListener("focusout", handleTooltipFocusOut);
window.addEventListener("resize", hideTooltip);
window.addEventListener("scroll", hideTooltip, true);

// Displays one tab panel and marks its corresponding sidebar button active.
function showPanel(tabName) {
  document.querySelectorAll(".panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `panel-${tabName}`);
  });

  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tabName);
  });
}

// Renders the top repository summary from backend metadata.
function renderRepository(repository) {
  if (!repository || !repository.path) {
    setText("repo-summary", "No repository selected");
    return;
  }

  const repoLabel = repository.github_owner && repository.github_repo
    ? `${repository.github_owner}/${repository.github_repo}`
    : repository.path.split(/[\\/]/).pop();
  const remoteLabel = repository.has_origin ? "origin" : "local";
  setText("repo-summary", `${repoLabel} - ${repository.branch} - ${remoteLabel}`);
}

// Renders changed files with selectable checkboxes for commit creation.
function renderStatus(status, selectedFiles) {
  const files = status && status.files ? status.files : [];
  const summary = status && status.summary ? status.summary : {};
  const list = byId("changed-files");
  setText("status-counts", `${summary.changed || 0} changed files`);

  if (!files.length) {
    list.innerHTML = '<div class="empty-state">Working tree clean</div>';
    return;
  }

  list.innerHTML = files.map((file) => {
    const checked = selectedFiles.has(file.path) ? "checked" : "";
    const pillClass = file.conflict ? "danger" : file.untracked ? "warning" : "";
    const original = file.original_path ? `<div class="row-meta">from ${escapeHtml(file.original_path)}</div>` : "";
    return `
      <label class="file-row">
        <input type="checkbox" class="file-checkbox" value="${escapeHtml(file.path)}" ${checked}>
        <span>
          <span class="file-path">${escapeHtml(file.path)}</span>
          ${original}
        </span>
        <span class="status-pill ${pillClass}">${escapeHtml(file.label)}</span>
      </label>
    `;
  }).join("");
}

// Renders local branches and checkout actions.
function renderBranches(branches) {
  const list = byId("branches-list");
  const branchItems = branches && branches.branches ? branches.branches : [];
  const current = branches && branches.current ? `Current branch: ${branches.current}` : "No branch loaded";
  const canCreateBranch = !branches || branches.has_commits !== false;
  const createButton = byId("create-branch");
  setText("current-branch", current);
  createButton.disabled = !canCreateBranch;
  createButton.title = canCreateBranch ? "" : "Create the first commit before creating another branch.";

  if (!branchItems.length) {
    const emptyMessage = canCreateBranch
      ? "No local branches loaded"
      : "No commits yet. Create the first commit before creating another branch.";
    list.innerHTML = `<div class="empty-state">${escapeHtml(emptyMessage)}</div>`;
    return;
  }

  list.innerHTML = branchItems.map((branch) => {
    const activePill = branch.active ? '<span class="status-pill success">active</span>' : "";
    const disabled = branch.active ? "disabled" : "";
    return `
      <div class="branch-row">
        <div>
          <div class="row-title">${escapeHtml(branch.name)}</div>
          ${activePill}
        </div>
        <button class="checkout-branch" type="button" data-branch="${escapeHtml(branch.name)}" ${disabled}>
          Checkout
        </button>
      </div>
    `;
  }).join("");
}

// Renders recent GitHub Actions workflow runs.
function renderWorkflowRuns(payload) {
  const list = byId("workflow-runs");
  const runs = payload && payload.runs ? payload.runs : [];
  setText("actions-summary", `${runs.length} workflow runs`);

  if (!runs.length) {
    list.innerHTML = '<div class="empty-state">No workflow runs loaded</div>';
    return;
  }

  list.innerHTML = runs.map((run) => {
    const conclusion = run.conclusion || run.status || "unknown";
    const pillClass = conclusion === "success" ? "success" : conclusion === "failure" ? "danger" : "warning";
    return `
      <div class="run-row">
        <div>
          <div class="row-title">${escapeHtml(run.name)}</div>
          <div class="row-meta">${escapeHtml(run.branch)} ${escapeHtml(run.event)} #${escapeHtml(run.run_number)}</div>
        </div>
        <span class="status-pill ${pillClass}">${escapeHtml(conclusion)}</span>
      </div>
    `;
  }).join("");
}

// Renders GitHub releases with draft/prerelease state markers.
function renderReleases(releases) {
  const list = byId("releases-list");
  const releaseCount = releases && releases.length ? releases.length : 0;
  setText("releases-summary", `${releaseCount} releases`);

  if (!releaseCount) {
    list.innerHTML = '<div class="empty-state">No releases loaded</div>';
    return;
  }

  list.innerHTML = releases.map((release) => {
    const state = release.draft ? "draft" : release.prerelease ? "prerelease" : "published";
    const pillClass = release.draft ? "warning" : release.prerelease ? "warning" : "success";
    return `
      <div class="release-row">
        <div>
          <div class="row-title">${escapeHtml(release.tag_name)} - ${escapeHtml(release.name)}</div>
          <div class="row-meta">${escapeHtml(release.published_at || release.created_at)}</div>
        </div>
        <span class="status-pill ${pillClass}">${state}</span>
      </div>
    `;
  }).join("");
}

// Writes a visible status message for the current operation.
function showMessage(message, isError = false) {
  const element = byId("message-area");
  element.textContent = message || "";
  element.classList.toggle("error", Boolean(isError));
}

// Updates the busy indicator so long-running Git and API operations are visible.
function setBusy(isBusy) {
  setText("busy-indicator", isBusy ? "Working" : "Idle");
}

// Appends a system event inside DevTools and gives its toolbar icon stable status feedback.
function appendActivity(message, isError = false) {
  const log = byId("activity-log");
  const entry = document.createElement("div");
  entry.className = `activity-entry${isError ? " error" : ""}`;
  entry.innerHTML = `<time>${new Date().toLocaleTimeString()}</time><div>${escapeHtml(message)}</div>`;
  log.append(entry);
  log.scrollTop = log.scrollHeight;
  if (window.GitDeskDebug) {
    window.GitDeskDebug.signal(Boolean(isError));
    window.GitDeskDebug.render();
  }
}

// Publishes render helpers for the classic-script controller used inside WebUI's WebView shell.
window.GitDeskRender = {
  appendActivity,
  byId,
  escapeHtml,
  renderBranches,
  renderReleases,
  renderRepository,
  renderStatus,
  renderWorkflowRuns,
  setBusy,
  setText,
  setTooltipText,
  setValue,
  showMessage,
  showPanel,
};
})();
