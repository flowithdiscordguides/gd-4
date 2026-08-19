/*
  GitHub Actions warning, failure, notice, and annotation-access rendering helpers.
*/

// Keeps issue-specific formatting out of the near-ceiling Actions detail page renderer.
(() => {
// Escapes all GitHub-provided annotation and error text before inserting it into the detail page.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Maps GitHub's notice, warning, and failure levels onto GitDesk's existing status colors.
function annotationStatus(annotation) {
  const level = String(annotation && annotation.annotation_level || "warning").toLowerCase();
  if (level === "failure") return { className: "danger", label: "error" };
  if (level === "notice") return { className: "building", label: "notice" };
  return { className: "warning", label: "warning" };
}

// Builds a readable file and line location only when GitHub supplied source coordinates.
function annotationLocation(annotation) {
  const path = String(annotation && annotation.path || "").trim();
  const startLine = Number(annotation && annotation.start_line || 0);
  const endLine = Number(annotation && annotation.end_line || 0);
  if (!path) return "";
  if (!startLine) return path;
  return endLine && endLine !== startLine ? `${path}:${startLine}-${endLine}` : `${path}:${startLine}`;
}

// Copies job annotations into one summary list while retaining the job that produced each issue.
function allAnnotations(jobs) {
  const annotations = [];
  (jobs || []).forEach((job) => {
    (job.annotations || []).forEach((annotation) => {
      const copied = {};
      Object.keys(annotation).forEach((key) => {
        copied[key] = annotation[key];
      });
      copied.job_name = job.name;
      annotations.push(copied);
    });
  });
  return annotations;
}

// Renders one GitHub annotation with severity, job/title, message, location, and optional raw details.
function annotationMarkup(annotation) {
  const status = annotationStatus(annotation);
  const heading = annotation.job_name || annotation.title || annotation.path || "Workflow issue";
  const message = annotation.message || annotation.raw_details || "GitHub did not provide issue details.";
  const location = annotationLocation(annotation);
  const rawDetails = annotation.raw_details && annotation.raw_details !== message ? annotation.raw_details : "";
  const metadata = [location, rawDetails].filter(Boolean).join(" - ");
  return `
    <div class="annotation-row annotation-${status.className}">
      <span class="status-pill ${status.className}">${escapeHtml(status.label)}</span>
      <span class="annotation-copy">
        <strong>${escapeHtml(heading)}</strong>
        <span>${escapeHtml(message)}</span>
        ${metadata ? `<small>${escapeHtml(metadata)}</small>` : ""}
      </span>
    </div>
  `;
}

// Renders annotation API failures explicitly so missing Checks permission never looks like an empty success.
function annotationErrorMarkup(error) {
  const jobName = error && error.job ? `${error.job}: ` : "";
  const message = error && error.message ? error.message : "GitHub annotations could not be loaded.";
  return `
    <div class="annotation-row annotation-danger">
      <span class="status-pill danger">error</span>
      <span class="annotation-copy">
        <strong>Annotations unavailable</strong>
        <span>${escapeHtml(jobName + message)}</span>
      </span>
    </div>
  `;
}

// Returns a complete issue list, including fetch errors, or a clear empty state when GitHub reported none.
function renderAnnotations(annotations, errors) {
  const issueRows = (annotations || []).map(annotationMarkup);
  const errorRows = (errors || []).map(annotationErrorMarkup);
  const rows = issueRows.concat(errorRows);
  return rows.length ? rows.join("") : '<div class="empty-state">No warnings or errors reported</div>';
}

window.GitDeskActionsIssues = { allAnnotations, renderAnnotations };
})();
