/*
  In-app diagnostics capture for WebView builds where native DevTools are not exposed by WebUI.
*/

// Keeps diagnostics internals private while exposing only the controls needed by the app.
(() => {
const MAX_DEBUG_ENTRIES = 200;
const FEEDBACK_DURATION_MS = 1200;
const entries = [];
let feedbackTimer = 0;
const originalConsole = {
  log: console.log.bind(console),
  info: console.info.bind(console),
  warn: console.warn.bind(console),
  error: console.error.bind(console),
};

// Converts arbitrary console arguments into safe, readable text for the diagnostics panel.
function stringifyValue(value) {
  if (value instanceof Error) {
    const summary = value.message ? `${value.name || "Error"}: ${value.message}` : value.name || "Error";
    const fields = [summary];
    if (value.code) {
      fields.push(`Code: ${value.code}`);
    }
    if (value.details && Object.keys(value.details).length) {
      fields.push(`Details: ${JSON.stringify(value.details)}`);
    }
    const stack = String(value.stack || "").split("\n").slice(1).join("\n").trim();
    if (stack) {
      fields.push(stack);
    }
    return fields.join("\n");
  }

  if (typeof value === "string") {
    return value;
  }

  try {
    return JSON.stringify(value);
  } catch (error) {
    return String(value);
  }
}

// Escapes captured console text before inserting it into the diagnostics panel.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Adds a diagnostic entry and keeps the log bounded so long sessions do not grow without limit.
function addEntry(level, values) {
  entries.unshift({
    level,
    message: values.map(stringifyValue).join(" "),
    timestamp: new Date().toLocaleTimeString(),
  });

  if (entries.length > MAX_DEBUG_ENTRIES) {
    entries.pop();
  }

  renderDebugPanel();
  if (level === "error") {
    signalOutcome(true);
  }
}

// Renders the captured diagnostics when the DevTools panel exists in the document.
function renderDebugPanel() {
  const list = document.getElementById("debug-log");
  const summary = document.getElementById("debug-summary");
  if (!list || !summary) {
    return;
  }

  const activityCount = document.querySelectorAll("#activity-log .activity-entry").length;
  summary.textContent = `${activityCount} system events - ${entries.length} console events`;
  if (!entries.length) {
    list.innerHTML = '<div class="empty-state">No console events captured</div>';
    return;
  }

  list.innerHTML = entries.map((entry) => `
    <div class="debug-entry ${entry.level}">
      <div class="debug-meta">
        <span>${escapeHtml(entry.level)}</span>
        <time>${escapeHtml(entry.timestamp)}</time>
      </div>
      <pre>${escapeHtml(entry.message)}</pre>
    </div>
  `).join("");
}

// Converts captured entries into a plain-text transcript for clipboard export.
function entriesToText() {
  if (!entries.length) {
    return "No console events captured";
  }

  return entries.map((entry) => {
    return `[${entry.timestamp}] ${entry.level.toUpperCase()}: ${entry.message}`;
  }).join("\n\n");
}

// Copies text by selecting a temporary textarea when the async clipboard API is unavailable.
function copyWithTextarea(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "readonly");
  textarea.style.position = "fixed";
  textarea.style.top = "-1000px";
  textarea.style.left = "-1000px";
  document.body.appendChild(textarea);
  textarea.select();

  const copied = document.execCommand && document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!copied) {
    return Promise.reject(new Error("Clipboard copy failed."));
  }
  return Promise.resolve();
}

// Copies text with the best available browser API and falls back to document selection.
function copyText(text) {
  if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
    return navigator.clipboard.writeText(text).catch((error) => copyWithTextarea(text));
  }
  return copyWithTextarea(text);
}

// Normalizes visible Activity text so copied output reads cleanly outside the app.
function cleanText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

// Reads the unified DevTools status, Activity entries, and console capture into one support transcript.
function activityOutputText() {
  const sections = [];
  const statusElement = document.getElementById("message-area");
  const status = cleanText(statusElement ? statusElement.textContent : "");
  const activityEntries = Array.from(document.querySelectorAll("#activity-log .activity-entry")).map((entry) => {
    return cleanText(entry.textContent);
  });

  if (status) {
    sections.push(`Status:\n${status}`);
  }
  if (activityEntries.length) {
    sections.push(`Activity:\n${activityEntries.join("\n")}`);
  }
  sections.push(`Console:\n${entriesToText()}`);
  return sections.join("\n\n");
}

// Shows a stable success or error color briefly without flashing, pulsing, or moving the control.
function signalOutcome(isError) {
  const button = document.querySelector('.tab-button[data-tab="debug"]');
  if (!button) {
    return;
  }
  const className = isError ? "debug-feedback-error" : "debug-feedback-success";
  window.clearTimeout(feedbackTimer);
  button.classList.remove("debug-feedback-success", "debug-feedback-error");
  button.classList.add(className);
  feedbackTimer = window.setTimeout(() => {
    button.classList.remove(className);
    feedbackTimer = 0;
  }, FEEDBACK_DURATION_MS);
}

// Writes copy feedback directly to DevTools so this works even if the main app failed startup.
function appendActivityFeedback(message, isError) {
  const log = document.getElementById("activity-log");
  if (!log) {
    return;
  }

  const entry = document.createElement("div");
  entry.className = `activity-entry${isError ? " error" : ""}`;
  entry.innerHTML = `<time>${new Date().toLocaleTimeString()}</time><div>${escapeHtml(message)}</div>`;
  log.prepend(entry);
  signalOutcome(isError);
  renderDebugPanel();
}

// Copies every visible DevTools output section from the panel header copy button.
function copyActivityOutput() {
  copyText(activityOutputText()).then(() => {
    appendActivityFeedback("Copied all DevTools output", false);
  }, (error) => {
    appendActivityFeedback(error.message || "Could not copy DevTools output.", true);
  });
}

// Opens the diagnostics panel without depending on the main app controller or renderer module.
function showDebugPanel() {
  document.querySelectorAll(".panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === "panel-debug");
  });

  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === "debug");
  });

  renderDebugPanel();
}

// Binds diagnostics controls separately so startup failures do not hide the error log.
function bindDebugControls() {
  const debugTab = document.querySelector('[data-tab="debug"]');
  const clearButton = document.getElementById("clear-debug-log");
  const copyButton = document.getElementById("copy-activity-output");
  if (debugTab) {
    debugTab.addEventListener("click", showDebugPanel);
  }
  if (clearButton) {
    clearButton.addEventListener("click", clearEntries);
  }
  if (copyButton) {
    copyButton.addEventListener("click", copyActivityOutput);
  }
}

// Clears captured diagnostics and rerenders the panel.
function clearEntries() {
  entries.splice(0, entries.length);
  renderDebugPanel();
}

// Wraps console methods so browser diagnostics remain visible inside the app.
function installConsoleCapture() {
  ["log", "info", "warn", "error"].forEach((level) => {
    console[level] = function captureConsoleCall() {
      const values = Array.prototype.slice.call(arguments);
      addEntry(level, values);
      originalConsole[level].apply(console, values);
    };
  });
}

// Captures uncaught exceptions that would normally only appear in native browser developer tools.
window.addEventListener("error", (event) => {
  addEntry("error", [event.error || event.message]);
});

// Captures unhandled promise failures, which are common when bridge calls fail before UI handlers catch them.
window.addEventListener("unhandledrejection", (event) => {
  addEntry("error", [event.reason || "Unhandled promise rejection"]);
});

// Exposes a tiny API for app controls without leaking implementation details across modules.
window.GitDeskDebug = {
  clear() {
    clearEntries();
  },
  copyActivity: copyActivityOutput,
  copyText,
  open: showDebugPanel,
  render: renderDebugPanel,
  signal: signalOutcome,
  text: entriesToText,
};

// Runs a callback immediately when the document is already parsed, or waits for parsing to finish.
function onDocumentReady(callback) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", callback);
    return;
  }
  callback();
}

installConsoleCapture();
onDocumentReady(() => {
  bindDebugControls();
  renderDebugPanel();
});
})();
