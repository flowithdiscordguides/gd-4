/* Shared polling for artifact-only Sync Chain edges that outlive one WebView callback. */

(() => {
const nativeBridge = window.GitDeskNativeBridge;
if (!nativeBridge) throw new Error("GitDesk artifact job dependencies did not load.");

const JOB_POLL_MS = 400;

function jobError(payload = {}) {
  const error = new Error(payload.message || "Artifact synchronization failed.");
  error.code = payload.code || "SYNC_JOB_FAILED";
  error.details = payload.details || {};
  return error;
}

async function waitForJob(jobId, onProgress) {
  while (true) {
    const job = await nativeBridge.callNative("syncChainJobStatus", { job_id: jobId });
    if (typeof onProgress === "function") onProgress(job.progress || {});
    if (job.status === "succeeded") return job.result;
    if (job.status === "failed") throw jobError(job.error);
    await new Promise((resolve) => window.setTimeout(resolve, JOB_POLL_MS));
  }
}

async function run(chainId, edge, expectedReleaseTag = "", onProgress = null) {
  const started = await nativeBridge.callNative("startSyncChainEdge", {
    chain_id: chainId,
    edge,
    expected_release_tag: expectedReleaseTag,
  });
  return waitForJob(started.job_id, onProgress);
}

window.GitDeskSyncChainArtifactJob = { run };
})();
