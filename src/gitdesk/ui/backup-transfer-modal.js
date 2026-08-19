/*
  Explorer-style factual Backup transfer progress, polling, speed, and cancellation.
*/

// Owns the long-running job surface while the source-selection modal retains the reviewed scope.
(() => {
const nativeBridge = window.GitDeskNativeBridge;
const renderHelpers = window.GitDeskRender;
const skippedItems = window.GitDeskBackupSkippedItems;
if (!nativeBridge || !renderHelpers || !skippedItems) {
  throw new Error("GitDesk Backup transfer dependencies did not load.");
}
const { callNative } = nativeBridge;
const { byId } = renderHelpers;
const POLL_INTERVAL_MS = 250;
const state = {
  cancelInFlight: false,
  cancelRequested: false,
  jobId: "",
  lastBytes: 0,
  lastPhase: "",
  lastSampleAt: 0,
  previousFocus: null,
  running: false,
  speed: 0,
  terminalJob: null,
  terminalResolve: null,
};
// Inserts one focused transfer dialog modeled on the Windows Explorer copy surface.
function injectModal() {
  if (document.getElementById("backup-transfer-modal")) return;
  document.body.insertAdjacentHTML("beforeend", `
    <section id="backup-transfer-modal" class="backup-transfer-modal" hidden>
      <div class="backup-transfer-dialog" role="dialog" aria-modal="true"
        aria-labelledby="backup-transfer-title" aria-describedby="backup-transfer-detail">
        <header class="backup-transfer-header">
          <span class="backup-transfer-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M3 6h7l2 2h9v11H3z"></path>
              <path d="M8 13h8m-3-3 3 3-3 3"></path>
            </svg>
          </span>
          <div>
            <p id="backup-transfer-kicker">Creating GitDesk backup</p>
            <h2 id="backup-transfer-title">Calculating selected files…</h2>
          </div>
        </header>
        <div class="backup-transfer-progress-heading" aria-live="polite">
          <strong id="backup-transfer-percent">Calculating…</strong>
          <span id="backup-transfer-phase">Preparing backup</span>
        </div>
        <div id="backup-transfer-track" class="backup-transfer-track indeterminate"
          role="progressbar" aria-label="Backup transfer progress" aria-valuemin="0" aria-valuemax="100">
          <span id="backup-transfer-fill"></span>
        </div>
        <p id="backup-transfer-detail" class="backup-transfer-detail">Reading the confirmed selection…</p>
        <dl class="backup-transfer-facts">
          <div><dt>Items</dt><dd id="backup-transfer-items">Calculating…</dd></div>
          <div><dt>Data</dt><dd id="backup-transfer-bytes">0 B read</dd></div>
          <div><dt>Speed</dt><dd id="backup-transfer-speed">Calculating…</dd></div>
          <div><dt>Time remaining</dt><dd id="backup-transfer-time">Calculating…</dd></div>
        </dl>
        ${skippedItems.markup()}
        <footer class="backup-transfer-actions">
          <p id="backup-transfer-safety">Cancelling removes staging data and does not create a version.</p>
          <div class="button-row">
            <button id="open-completed-backup" type="button" hidden>Open backup</button>
            <button id="finish-backup-transfer" type="button" hidden>Done</button>
            <button id="cancel-backup-transfer" type="button">Cancel</button>
          </div>
        </footer>
      </div>
    </section>
  `);
}
// Formats exact byte counts without rounding away the unit boundary.
function sizeLabel(byteCount) {
  let value = Math.max(0, Number(byteCount || 0));
  const units = ["B", "KB", "MB", "GB", "TB"];
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${index ? value.toFixed(1) : Math.round(value)} ${units[index]}`;
}
// Formats a bounded Explorer-style remaining-time estimate from measured current-phase speed.
function timeLabel(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return "Calculating…";
  const rounded = Math.ceil(seconds);
  if (rounded < 60) return `About ${rounded} second${rounded === 1 ? "" : "s"}`;
  const minutes = Math.ceil(rounded / 60);
  if (minutes < 60) return `About ${minutes} minute${minutes === 1 ? "" : "s"}`;
  const hours = Math.ceil(minutes / 60);
  return `About ${hours} hour${hours === 1 ? "" : "s"}`;
}
// Maps backend phases to user-facing transfer language without inventing work.
function phaseLabel(phase) {
  return {
    preparing: "Calculating selected files",
    copying: "Copying into the new backup version",
    verifying: "Verifying copied files",
    finalizing: "Finishing the backup version",
  }[phase] || "Preparing backup";
}
// Returns a determinate ratio only after the backend supplies a factual phase total.
function progressRatio(progress) {
  if (progress.phase === "finalizing") return 1;
  if (progress.bytes_total > 0) {
    return Math.min(1, Math.max(0, progress.bytes_done / progress.bytes_total));
  }
  if (progress.items_total > 0) {
    return Math.min(1, Math.max(0, progress.items_done / progress.items_total));
  }
  return null;
}
// Derives current-phase throughput only from observed backend byte changes and elapsed wall time.
function updateSpeed(progress) {
  const now = performance.now();
  if (progress.phase !== state.lastPhase) {
    state.lastPhase = progress.phase;
    state.lastBytes = Number(progress.bytes_done || 0);
    state.lastSampleAt = now;
    state.speed = 0;
    return;
  }
  const elapsed = (now - state.lastSampleAt) / 1000;
  const byteDelta = Number(progress.bytes_done || 0) - state.lastBytes;
  if (elapsed >= 0.2 && byteDelta >= 0) {
    const measured = byteDelta / elapsed;
    state.speed = state.speed ? (state.speed * 0.65) + (measured * 0.35) : measured;
    state.lastBytes = Number(progress.bytes_done || 0);
    state.lastSampleAt = now;
  }
}
// Renders one complete polled job snapshot into the progress bar and factual detail fields.
function renderJob(job) {
  const progress = job.progress || {};
  const phase = progress.phase || "preparing";
  const ratio = progressRatio(progress);
  const track = byId("backup-transfer-track");
  updateSpeed(progress);
  byId("backup-transfer-title").textContent = `${phaseLabel(phase)}…`;
  byId("backup-transfer-phase").textContent = phaseLabel(phase);
  track.classList.toggle("indeterminate", ratio == null);
  if (ratio == null) {
    track.removeAttribute("aria-valuenow");
    byId("backup-transfer-percent").textContent = "Calculating…";
    byId("backup-transfer-fill").style.width = "";
  } else {
    const percent = Math.round(ratio * 100);
    track.setAttribute("aria-valuenow", String(percent));
    byId("backup-transfer-percent").textContent = `${percent}% complete`;
    byId("backup-transfer-fill").style.width = `${percent}%`;
  }
  const currentPath = String(progress.current_path || "");
  byId("backup-transfer-detail").textContent = currentPath
    ? currentPath
    : phase === "finalizing" ? "Installing the verified dated version…" : "Reading the confirmed selection…";
  byId("backup-transfer-items").textContent = progress.items_total
    ? `${progress.items_done || 0} of ${progress.items_total}`
    : `${progress.items_done || 0} found`;
  byId("backup-transfer-bytes").textContent = progress.bytes_total
    ? `${sizeLabel(progress.bytes_done)} of ${sizeLabel(progress.bytes_total)}`
    : `${sizeLabel(progress.bytes_done)} read`;
  const measuredPhase = ["copying", "verifying"].includes(phase);
  byId("backup-transfer-speed").textContent = measuredPhase && state.speed > 0
    ? `${sizeLabel(state.speed)}/s`
    : "Calculating…";
  const remainingBytes = Math.max(0, Number(progress.bytes_total || 0) - Number(progress.bytes_done || 0));
  byId("backup-transfer-time").textContent = measuredPhase && state.speed > 0
    ? timeLabel(remainingBytes / state.speed)
    : "Calculating…";
  const cancelButton = byId("cancel-backup-transfer");
  cancelButton.disabled = !job.cancellable || state.cancelRequested;
  cancelButton.textContent = state.cancelRequested ? "Cancelling…" : job.cancellable ? "Cancel" : "Finishing…";
}
// Waits between serialized polls so status requests never accumulate behind one another.
function pollDelay() {
  return new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
}
// Converts a terminal background-job error payload into the established frontend Error shape.
function terminalError(job) {
  const payload = job.error || {};
  const error = new Error(payload.message || "Backup could not be completed.");
  error.code = payload.code || "BACKUP_JOB_FAILED";
  error.details = payload.details || {};
  return error;
}
// Converts an immediate bridge failure into the same persistent terminal shape as a worker failure.
function failedJob(error) {
  return {
    status: "failed",
    progress: {
      phase: state.lastPhase || "preparing",
      bytes_done: state.lastBytes,
      bytes_total: 0,
      items_done: 0,
      items_total: 0,
    },
    cancellable: false,
    error: {
      code: error.code || "BACKUP_JOB_FAILED",
      message: error.message || "Backup could not be completed.",
      details: error.details || {},
    },
  };
}
// Shows one explicit success, cancellation, or failure result until the user acknowledges it.
function renderTerminal(job) {
  const completed = job.status === "completed";
  const cancelled = job.status === "cancelled";
  const result = job.result || {};
  const version = result.created_version || {};
  const error = job.error || {};
  const details = error.details || {};
  const sourceError = Array.isArray(details.errors) ? details.errors[0] || {} : {};
  const failedPath = details.path || sourceError.path || "";
  const failureReason = details.reason || sourceError.message || "";
  const warningCount = Array.isArray(version.metadata_warnings) ? version.metadata_warnings.length : 0;
  const skippedCount = Array.isArray(result.skipped_items) ? result.skipped_items.length : 0;
  const partial = completed && skippedCount > 0;
  const dialog = document.querySelector(".backup-transfer-dialog");
  dialog.classList.toggle("completed", completed);
  dialog.classList.toggle("partial", partial);
  dialog.classList.toggle("failed", !completed && !cancelled);
  dialog.classList.toggle("cancelled", cancelled);
  byId("backup-transfer-kicker").textContent = partial ? "Backup created with exceptions"
    : completed ? "Backup verified" : "Backup not created";
  byId("backup-transfer-title").textContent = completed
    ? result.no_changes ? "Backup is already current"
      : partial ? "Backup completed with skipped items" : "Backup completed"
    : cancelled ? "Backup cancelled" : "Backup failed";
  byId("backup-transfer-phase").textContent = partial ? `${skippedCount} skipped · copied content verified`
    : completed ? "Verified destination" : error.code || "Stopped";
  byId("backup-transfer-percent").textContent = partial ? "Completed with exceptions"
    : completed ? "100% complete" : "Not completed";
  byId("backup-transfer-detail").textContent = completed
    ? version.name ? `Installed ${version.name}` : "No file changes required for the current selection."
    : [error.message, failedPath ? `Item: ${failedPath}` : "", failureReason]
      .filter(Boolean).join(" ");
  byId("backup-transfer-safety").textContent = completed
    ? partial
      ? `${skippedCount} item(s) were not installed and remain pending for the next sync.`
      : warningCount
      ? `All selected content was verified. ${warningCount} portable metadata field(s) were not supported.`
      : "Every selected manifest item exists in the verified dated backup folder."
    : cancelled
      ? "Staging data was removed and no backup version was created."
      : "No incomplete folder was added to Backup history. Review the exact reason above before retrying.";
  skippedItems.render(job);
  byId("cancel-backup-transfer").hidden = true;
  byId("open-completed-backup").hidden = !completed || !version.path;
  const finishButton = byId("finish-backup-transfer");
  finishButton.hidden = false;
  finishButton.textContent = completed ? "Done" : "Back to selection";
  finishButton.focus();
}
// Keeps terminal evidence visible until the user explicitly chooses the next action.
function waitForAcknowledgement(job) {
  state.terminalJob = job;
  return new Promise((resolve) => {
    state.terminalResolve = resolve;
  });
}
// Resolves the terminal hold exactly once so the selection workflow can continue safely.
function acknowledgeTerminal() {
  if (!state.terminalResolve) return;
  const resolve = state.terminalResolve;
  state.terminalResolve = null;
  resolve();
}
// Opens only the exact completed version returned by the verified Backup job.
async function openCompletedBackup() {
  const result = state.terminalJob && state.terminalJob.result ? state.terminalJob.result : {};
  const version = result.created_version || {};
  if (!version.path) return;
  try {
    await callNative("openBackupVersion", { path: version.path });
  } catch (error) {
    byId("backup-transfer-detail").textContent = error.message || "The completed backup could not be opened.";
  }
}
// Sends an already-recorded cancellation intent once the backend has returned the opaque job id.
async function sendCancellation() {
  if (!state.jobId || state.cancelInFlight) return;
  state.cancelInFlight = true;
  try {
    renderJob(await callNative("cancelBackupJob", { job_id: state.jobId }));
  } catch (error) {
    state.cancelRequested = false;
    byId("backup-transfer-detail").textContent = "Cancellation request failed; retry is available.";
  } finally {
    state.cancelInFlight = false;
  }
}

// Requests cancellation now or records intent until the job id arrives from the start action.
async function cancel() {
  if (!state.running || state.cancelRequested) return;
  state.cancelRequested = true;
  byId("cancel-backup-transfer").disabled = true;
  byId("cancel-backup-transfer").textContent = "Cancelling…";
  await sendCancellation();
}

// Polls until the worker reports a terminal state while retaining the dialog through bridge retries.
async function waitForTerminal(initialJob) {
  let job = initialJob;
  while (true) {
    renderJob(job);
    if (["completed", "cancelled", "failed"].includes(job.status)) return job;
    await pollDelay();
    try {
      job = await callNative("backupJobStatus", { job_id: state.jobId });
    } catch (error) {
      byId("backup-transfer-detail").textContent = "Waiting for GitDesk to report transfer progress…";
    }
  }
}

// Starts the confirmed job, shows factual progress, and resolves only with its canonical Backup response.
async function start(selection) {
  if (state.running) throw new Error("A backup transfer is already open.");
  Object.assign(state, {
    cancelInFlight: false,
    cancelRequested: false,
    jobId: "",
    lastBytes: 0,
    lastPhase: "",
    lastSampleAt: 0,
    previousFocus: document.activeElement,
    running: true,
    speed: 0,
    terminalJob: null,
    terminalResolve: null,
  });
  document.querySelector(".backup-transfer-dialog").classList.remove("completed", "partial", "failed", "cancelled");
  skippedItems.clear();
  byId("backup-transfer-modal").hidden = false;
  byId("open-completed-backup").hidden = true;
  byId("finish-backup-transfer").hidden = true;
  byId("cancel-backup-transfer").hidden = false;
  byId("cancel-backup-transfer").disabled = false;
  byId("cancel-backup-transfer").textContent = "Cancel";
  byId("cancel-backup-transfer").focus();
  try {
    let job;
    try {
      job = await callNative("startBackupJob", { selection, confirmed: true });
      state.jobId = job.job_id || "";
      if (state.cancelRequested) await sendCancellation();
      job = await waitForTerminal(job);
    } catch (error) {
      job = failedJob(error);
    }
    renderJob(job);
    renderTerminal(job);
    await waitForAcknowledgement(job);
    if (job.status !== "completed") throw terminalError(job);
    return job.result;
  } finally {
    state.running = false;
    byId("backup-transfer-modal").hidden = true;
    if (state.previousFocus && state.previousFocus.isConnected) state.previousFocus.focus();
  }
}

// Installs the transfer modal and its sole reversible action.
function init() {
  injectModal();
  byId("cancel-backup-transfer").addEventListener("click", () => cancel().catch(() => {}));
  byId("finish-backup-transfer").addEventListener("click", acknowledgeTerminal);
  byId("open-completed-backup").addEventListener("click", () => openCompletedBackup().catch(() => {}));
  document.addEventListener("keydown", (event) => {
    if (byId("backup-transfer-modal").hidden) return;
    if (event.key === "Escape" && state.terminalJob) acknowledgeTerminal();
    else if (event.key === "Escape") cancel().catch(() => {});
    if (event.key === "Tab") {
      event.preventDefault();
      const buttons = Array.from(document.querySelectorAll(
        ".backup-transfer-dialog button:not([hidden]):not(:disabled)",
      )).filter((button) => button.offsetParent !== null);
      const currentIndex = buttons.indexOf(document.activeElement);
      const direction = event.shiftKey ? -1 : 1;
      const nextIndex = (currentIndex + direction + buttons.length) % buttons.length;
      if (buttons.length) buttons[nextIndex].focus();
    }
  });
}

window.GitDeskBackupTransferModal = { start };

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
})();
