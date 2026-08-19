/*
  Local Mode selected-version synchronization into a configured Private Beta stage.
*/

// Keeps unconditional Local-to-Private Beta replacement separate from the Local Mode controller.
(() => {
// Mirrors one selected version while preserving only the destination repository's .git metadata.
async function syncToPrivateBeta(runAction, projectPath, versionPath) {
  const data = await runAction("syncLocalVersionToPrivateBeta", {
    project_path: projectPath,
    version_path: versionPath,
  }, "Local version synced to Private Beta");
  if (window.GitDeskSyncChains) {
    window.GitDeskSyncChains.applyCompletedSync(data);
    window.GitDeskSyncChains.clearProjectNotification(projectPath);
  }
  if (window.GitDeskSyncChains) {
    try {
      await window.GitDeskSyncChains.refreshNotificationsAfterLocalSync();
    } catch (error) {
      // The completed sync remains successful; the next Local Mode poll will retry notification detection.
    }
  }
}

window.GitDeskLocalSync = { syncToPrivateBeta };
})();
