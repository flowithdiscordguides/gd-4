/*
  GitHub Actions refresh scheduling for active runs and newly pushed commits.
*/

// Keeps timers and pushed-SHA reconciliation out of the near-limit Actions panel controller.
(() => {
// Active runs keep their existing fast cadence so live job state remains responsive.
const POLL_MS = 2000;

// Elapsed labels update independently because they do not require another GitHub request.
const ELAPSED_MS = 1000;

// GitHub may expose a pushed commit before its workflow run; bounded backoff avoids permanent API polling.
const POST_PUSH_RETRY_MS = [1500, 3000, 5000, 8000, 13000, 21000];

// Normalizes Git commit identifiers before comparing the pushed revision with Actions run data.
function normalizeSha(value) {
  return String(value || "").trim().toLowerCase();
}

// Creates one repository-scoped scheduler around callbacks owned by the Actions controller.
function create(options) {
  let pollTimer = null;
  let elapsedTimer = null;
  let postPushTimer = null;
  let expectedSha = "";
  let retryIndex = 0;

  // Clears only pushed-commit reconciliation while leaving active-run timers under sync().
  function clearPostPushWatch() {
    expectedSha = "";
    retryIndex = 0;
    if (postPushTimer) {
      window.clearTimeout(postPushTimer);
      postPushTimer = null;
    }
  }

  // Returns whether GitHub has exposed a workflow run for the exact pushed commit.
  function hasExpectedRun(runs) {
    return Boolean(expectedSha) && runs.some((run) => normalizeSha(run.sha) === expectedSha);
  }

  // Schedules the next bounded reconciliation request after a completed Actions response.
  function schedulePostPushRetry() {
    if (!expectedSha || postPushTimer || retryIndex >= POST_PUSH_RETRY_MS.length) {
      return;
    }
    const delay = POST_PUSH_RETRY_MS[retryIndex];
    retryIndex += 1;
    postPushTimer = window.setTimeout(() => {
      postPushTimer = null;
      options.refresh({ quiet: true, queueIfBusy: true });
    }, delay);
  }

  // Aligns active-run polling and elapsed updates with the latest rendered workflow list.
  function sync(runs) {
    const runList = Array.isArray(runs) ? runs : [];
    if (hasExpectedRun(runList)) {
      clearPostPushWatch();
    }
    const releaseWatch = window.GitDeskReleaseAlerts && window.GitDeskReleaseAlerts.isWatchingBuild();
    const hasActiveRuns = runList.some(options.isActiveRun) || releaseWatch;
    if (hasActiveRuns && !pollTimer) {
      pollTimer = window.setInterval(() => options.refresh({ quiet: true }), POLL_MS);
    } else if (!hasActiveRuns && pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
    if (hasActiveRuns && !elapsedTimer) {
      elapsedTimer = window.setInterval(options.updateElapsedLabels, ELAPSED_MS);
    } else if (!hasActiveRuns && elapsedTimer) {
      window.clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
    options.updateElapsedLabels();
  }

  // Continues bounded reconciliation only after the previous refresh has settled.
  function refreshSettled() {
    schedulePostPushRetry();
  }

  // Starts an exact-SHA watch for commit, branch, or tag pushes and replaces any older watch.
  function notePush(commitSha) {
    clearPostPushWatch();
    expectedSha = normalizeSha(commitSha);
    if (!expectedSha) {
      options.refresh({ quiet: true, queueIfBusy: true });
      return;
    }
    schedulePostPushRetry();
  }

  // Clears repository-specific push state and recalculates the existing live timer contract.
  function reset() {
    clearPostPushWatch();
    sync([]);
  }

  return { notePush, refreshSettled, reset, sync };
}

window.GitDeskActionsRefresh = { create };
})();
