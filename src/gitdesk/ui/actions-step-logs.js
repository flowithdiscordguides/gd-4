/*
  Expandable GitHub Actions step rows with lazy, cached job-log output.
*/

// Keeps downloaded workflow output and disclosure state private to the Actions detail surface.
(() => {
// The loader is installed by actions.js so this focused renderer never reaches around the app controller.
let loadJobLogs = null;

// Reset generations prevent an old repository's in-flight response from repainting a new repository context.
let cacheGeneration = 0;

// One cached record per globally unique GitHub job avoids downloading the same plain-text log for every step.
const jobStates = new Map();

// Escapes job names and console output before placing GitHub-controlled text into markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Returns a stable disclosure key even when GitHub omits a step number from an incomplete job.
function stepKey(step, index) {
  const number = step && step.number != null ? step.number : `index-${index}`;
  return String(number);
}

// Returns one cached job record, creating its idle disclosure state on first render.
function jobState(job) {
  const key = String(job && job.id || "");
  if (!jobStates.has(key)) {
    jobStates.set(key, {
      error: "",
      expanded: new Set(),
      payload: null,
      status: "idle",
    });
  }
  return jobStates.get(key);
}

// Maps GitHub step status onto the existing success, building, warning, and danger color roles.
function statusClass(step) {
  if (step && step.status && step.status !== "completed") return "building";
  if (step && step.conclusion === "success") return "success";
  if (step && ["failure", "cancelled", "timed_out"].includes(step.conclusion)) return "danger";
  return "warning";
}

// Returns a readable state label so step status is never communicated by color alone.
function statusLabel(step) {
  if (!step) return "queued";
  if (step.status && step.status !== "completed") {
    return step.status === "in_progress" ? "running" : step.status;
  }
  return step.conclusion || "complete";
}

// Returns a compact status glyph that follows GitHub's scan-friendly job-step pattern.
function statusGlyph(step) {
  const status = statusClass(step);
  if (status === "success") return "✓";
  if (status === "danger") return "×";
  if (status === "building") return "•";
  return "–";
}

// Converts a GitHub timestamp into milliseconds while treating absent times as unavailable.
function timestamp(value) {
  const parsed = Date.parse(value || "");
  return Number.isNaN(parsed) ? 0 : parsed;
}

// Formats one step duration without allowing a running step to report a negative interval.
function formatElapsed(step) {
  const start = timestamp(step && step.started_at);
  const completed = timestamp(step && step.completed_at);
  const end = step && step.status !== "completed" ? Date.now() : completed;
  const seconds = start ? Math.floor(Math.max(0, (end || Date.now()) - start) / 1000) : 0;
  if (seconds >= 60) return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s`;
  return `${seconds}s`;
}

// Finds the downloaded output associated with one displayed step, falling back to ordered position when needed.
function stepOutput(record, step, index) {
  const outputs = record.payload && Array.isArray(record.payload.steps) ? record.payload.steps : [];
  const numbered = step.number == null
    ? null
    : outputs.find((output) => String(output.number) === String(step.number));
  return numbered || outputs[index] || { lines: [] };
}

// Extracts a raw workflow command's message while discarding command properties used for annotations.
function rawCommandMessage(text, command) {
  const prefix = `::${command}`;
  if (!text.toLowerCase().startsWith(prefix)) return null;
  const separator = text.indexOf("::", prefix.length);
  return separator >= 0 ? text.slice(separator + 2) : text;
}

// Converts runner control commands into the readable severity prefixes shown by GitHub's log viewer.
function displayLineText(value) {
  const text = String(value == null ? "" : value);
  if (text.startsWith("##[group]")) return text.slice(9);
  const commands = [
    ["error", "Error"],
    ["warning", "Warning"],
    ["notice", "Notice"],
  ];
  for (const [command, label] of commands) {
    const legacyPrefix = `##[${command}]`;
    if (text.toLowerCase().startsWith(legacyPrefix)) return `${label}: ${text.slice(legacyPrefix.length)}`;
    const message = rawCommandMessage(text, command);
    if (message != null) return `${label}: ${message}`;
  }
  return text;
}

// Returns a semantic class for runner warning/error command lines while preserving their exact text.
function logLineClass(line) {
  const text = String(line && line.text || "").toLowerCase();
  if (text.includes("##[error]") || text.startsWith("::error")) return " error";
  if (text.includes("##[warning]") || text.startsWith("::warning")) return " warning";
  return "";
}

// Renders one numbered console line; timestamps stay available as hover text without adding visual noise.
function logLineMarkup(line) {
  const timestampText = line && line.timestamp ? ` title="${escapeHtml(line.timestamp)}"` : "";
  return `
    <span class="action-log-line${logLineClass(line)}"${timestampText}>
      <span class="action-log-line-number" aria-hidden="true">${escapeHtml(line.number)}</span>
      <code>${escapeHtml(displayLineText(line.text))}</code>
    </span>
  `;
}

// Renders the loaded output region, omitting runner end-group commands that are not user-visible on GitHub.
function loadedOutputMarkup(record, step, index) {
  const output = stepOutput(record, step, index);
  const lines = (output.lines || []).filter((line) => {
    const text = String(line.text || "").toLowerCase();
    return text !== "##[endgroup]" && text !== "::endgroup::";
  });
  if (!lines.length) {
    return '<div class="action-step-log-empty">No output was recorded for this step.</div>';
  }
  return `<div class="action-step-log-lines">${lines.map(logLineMarkup).join("")}</div>`;
}

// Renders loading, failure, or loaded output for one currently expanded step.
function expandedMarkup(record, step, index, regionId) {
  let body = "";
  if (record.status === "loading") {
    body = '<div class="action-step-log-state"><span class="run-spinner" aria-hidden="true"></span>'
      + "Loading step output</div>";
  } else if (record.status === "error") {
    body = `
      <div class="action-step-log-state error">
        <span>${escapeHtml(record.error || "Step output could not be loaded.")}</span>
        <button type="button" data-step-log-retry="${escapeHtml(index)}"
          data-action-step-index="${escapeHtml(index)}">Retry</button>
      </div>
    `;
  } else if (record.status === "loaded") {
    body = loadedOutputMarkup(record, step, index);
  }
  return `
    <div id="${escapeHtml(regionId)}" class="action-step-log" role="region" aria-live="polite"
      aria-label="${escapeHtml(step.name || "Workflow step")} output">
      ${body}
    </div>
  `;
}

// Renders one accessible disclosure row and its output region when expanded.
function stepMarkup(job, step, index, record) {
  const key = stepKey(step, index);
  const expanded = record.expanded.has(key);
  const regionId = `action-step-log-${String(job.id)}-${key}`;
  return `
    <div class="action-step-item ${statusClass(step)}">
      <button class="action-step-toggle" type="button" data-action-step-index="${escapeHtml(index)}"
        aria-expanded="${expanded ? "true" : "false"}" aria-controls="${escapeHtml(regionId)}">
        <span class="action-step-chevron" aria-hidden="true">›</span>
        <span class="action-step-status ${statusClass(step)}" aria-hidden="true">${statusGlyph(step)}</span>
        <span class="action-step-copy">
          <strong>${escapeHtml(step.name || `Step ${step.number || index + 1}`)}</strong>
          <small>${escapeHtml(statusLabel(step))}</small>
        </span>
        <span class="action-step-duration">${escapeHtml(formatElapsed(step))}</span>
      </button>
      ${expanded ? expandedMarkup(record, step, index, regionId) : ""}
    </div>
  `;
}

// Renders every reported job step as a compact disclosure list.
function render(job) {
  const steps = job && Array.isArray(job.steps) ? job.steps : [];
  if (!steps.length) {
    return '<div class="empty-state">No steps reported yet</div>';
  }
  const record = jobState(job);
  return steps.map((step, index) => stepMarkup(job, step, index, record)).join("");
}

// Loads and caches all output for one job, then refreshes whichever detail pane remains selected.
async function fetchJobLogs(job, record, generation, onRender) {
  try {
    record.payload = await loadJobLogs(job.id);
    record.status = "loaded";
    record.error = "";
  } catch (error) {
    record.payload = null;
    record.status = "error";
    record.error = error && error.message ? error.message : "Step output could not be loaded.";
  }
  if (generation === cacheGeneration) {
    onRender();
  }
}

// Handles disclosure and retry clicks synchronously while the log download continues in the background.
function handleClick(event, job, onRender) {
  const retryButton = event.target.closest("[data-step-log-retry]");
  const toggleButton = event.target.closest("[data-action-step-index]");
  const button = retryButton || toggleButton;
  if (!button || !job || !Array.isArray(job.steps)) return false;

  const indexValue = retryButton ? retryButton.dataset.stepLogRetry : toggleButton.dataset.actionStepIndex;
  const index = Number(indexValue);
  const step = Number.isInteger(index) ? job.steps[index] : null;
  if (!step) return true;

  const record = jobState(job);
  const key = stepKey(step, index);
  if (!retryButton && record.expanded.has(key)) {
    record.expanded.delete(key);
    onRender();
    return true;
  }

  record.expanded.add(key);
  if (record.status === "idle" || record.status === "error" || retryButton) {
    record.status = "loading";
    record.error = "";
    onRender();
    fetchJobLogs(job, record, cacheGeneration, onRender);
  } else {
    onRender();
  }
  return true;
}

// Connects the renderer to the existing quiet native-action boundary and repository payload provider.
function install(options) {
  const runAction = options && options.runAction;
  const githubPayload = options && options.githubPayload;
  if (typeof runAction !== "function" || typeof githubPayload !== "function") {
    throw new Error("GitDesk Actions step-log dependencies did not load.");
  }
  loadJobLogs = (jobId) => {
    const payload = githubPayload();
    payload.job_id = jobId;
    return runAction("workflowJobLogs", payload, "", { quiet: true });
  };
}

// Clears log output when the account or repository context changes so data never crosses contexts.
function reset() {
  cacheGeneration += 1;
  jobStates.clear();
}

window.GitDeskActionsStepLogs = { handleClick, install, render, reset };
})();
