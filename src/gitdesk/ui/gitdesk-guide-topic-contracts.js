/*
 * Teaching contracts for every ordered GitDesk Guide topic.
 * Product behavior stays in the topic registries; this map owns how each topic is learned and verified.
 */
window.GitDeskGuideContracts = {
  start: {
    group: "Start",
    time: "4 minute orientation",
    sectionTitle: "Find your bearings",
    goals: ["Recognize the four main interface regions.", "Know where to begin a task or investigate a problem."],
    guideposts: [
      ["Choose a mode first", "Repo Mode works with Git repositories. Local Mode works with physical versions."],
      ["The toolbar follows the mode", "Its pages change with the active workspace instead of opening another app."],
      ["Activity is your evidence", "Settings establishes access; Activity and DevTools explain what happened."]
    ],
    prerequisite: "Have GitDesk open. A GitHub account is optional for this orientation.",
    practice: "Find the mode switch, toolbar, Settings, and DevTools in your own window.",
    proof: "You can point to the control that starts a repository task, a local-folder task, and troubleshooting.",
    recovery: "If a screenshot differs, follow the visible labels in the current app and use its active-mode state."
  },
  "repo-mode": {
    group: "Start",
    time: "5 minute decision guide",
    sectionTitle: "Know what Repo Mode owns",
    goals: ["Decide when Repo Mode is the right workspace.", "Prepare the account and repository context it needs."],
    guideposts: [
      ["Repository work lives here", "Clone, status, commits, branches, Pages, Actions, and releases share one "
        + "context."],
      ["Identity scopes the workspace", "The active PAT profile determines which managed repositories are available."],
      ["Local versions stay separate", "Numbered physical versions and Sync Chain sources begin in Local Mode."]
    ],
    prerequisite: "Use a saved GitHub account for private repositories or GitHub-hosted actions.",
    practice: "Open Repo Mode, select one saved repository, and load Status without making a commit.",
    proof: "The header shows the intended account and repository, and Overview shows that repository's current state.",
    recovery: "If the repository is absent, review its owner PAT, repository access, and saved local path."
  },
  "local-mode": {
    group: "Start",
    time: "6 minute decision guide",
    sectionTitle: "Read the folder model",
    goals: [
      "Recognize GitDesk's project, feature, and version folder model.",
      "Select the exact version before action."
    ],
    guideposts: [
      ["Folders are the source", "Projects, features, and numbered versions remain physical folders on disk."],
      ["Selection is consequential", "Notes, version creation, deletion, and promotion act on the selected version."],
      ["Promotion is explicit", "A configured Sync Chain moves one chosen version forward into managed repositories."]
    ],
    prerequisite: "Know the parent folder for a new project or the existing project folder to import.",
    practice: "Open Local Mode and identify the selected Project, Feature, Version, and inspector path.",
    proof: "The inspector's project, feature, and path all match the folder you intend to work on.",
    recovery: "If context is wrong, stop before destructive or sync actions and reselect the project and version."
  },
  "sync-chains": {
    group: "Start",
    time: "8 minute release model",
    sectionTitle: "Follow the promotion path",
    goals: ["Explain the four-folder promotion path.", "Distinguish working-tree sync from artifact-only publication."],
    guideposts: [
      ["Stages are separate repositories", "Local, Private Beta, Public Beta, and Public keep independent folders."],
      ["Promotion moves forward", "Each edge replaces its destination from the immediately earlier approved stage."],
      ["Git history is retained", "Working files mirror forward while each destination keeps its own .git metadata."]
    ],
    prerequisite: "Register the Local project and each repository in GitDesk before assigning stages.",
    practice: "Sketch the configured stage order and name which folder is the source of each sync action.",
    proof: "You can identify the exact source, destination, and post-sync review required for every configured edge.",
    recovery: "If an edge is unavailable, confirm earlier stages, distinct paths, and saved repository assignments."
  },
  header: {
    group: "Orientation",
    time: "3 minute tour",
    sectionTitle: "Read the active context",
    goals: ["Read the active account, mode, and repository context.", "Know which controls refresh or change it."],
    guideposts: [
      ["Context comes before action", "Mode, account, and repository determine which pages can act."],
      ["Add changes the catalog", "It opens repository intake; it does not perform a commit or sync."],
      ["Status refreshes evidence", "Use it before deciding what repository action to take next."]
    ],
    prerequisite: "Open GitDesk's main window.",
    practice: "Read the header left to right and say which mode and repository are active.",
    proof: "You can change mode deliberately and restore the intended repository without guessing.",
    recovery: "If repository controls are disabled, select a signed-in profile and a managed repository first."
  },
  toolbar: {
    group: "Orientation",
    time: "3 minute tour",
    sectionTitle: "Navigate by workflow",
    goals: ["Map each page icon to its workflow.", "Use active and notification states as navigation evidence."],
    guideposts: [
      ["One page owns the workspace", "Selecting a toolbar item replaces the current main work area."],
      ["Mode changes the useful set", "Local and repository tasks expose different destinations."],
      ["State is visible", "Active highlights show location; notification dots point to follow-up work."]
    ],
    prerequisite: "Choose Repo Mode or Local Mode in the header.",
    practice: "Open two toolbar pages and use the active highlight to name your current location.",
    proof: "You can return to Overview, Local Projects, Settings, and this Guide from their visible controls.",
    recovery: "If a page is unavailable, verify the current mode and required account or repository context."
  },
  repositories: {
    group: "Repo workflows",
    time: "7 minute setup",
    sectionTitle: "Choose the right intake",
    goals: ["Choose Clone, Add Existing, or Create New correctly.", "Route organization work through its owner PAT."],
    guideposts: [
      ["Owner access is explicit", "The active PAT can list only repositories GitHub allows it to access."],
      ["Intake methods differ", "Clone downloads, Add Existing registers, and Create New creates both remote and "
        + "local."],
      ["Existing origins are authoritative", "Add Existing reads ownership from the selected repository's origin."]
    ],
    prerequisite: "Save a PAT profile for the personal or organization owner you need.",
    practice: "Open Add and choose the intake tab that matches an existing remote, existing folder, or new repo.",
    proof: "The registered repository appears under the correct account and opens from the header selector.",
    recovery: "If it is missing, refresh and inspect resource owner, repository selection, policy, approval, and SSO."
  },
  overview: {
    group: "Repo workflows",
    time: "6 minute workflow",
    sectionTitle: "Build a clean commit",
    goals: ["Review changed paths and diffs before staging.", "Choose Commit or Commit and push intentionally."],
    guideposts: [
      ["Status is the starting evidence", "The changed-file tree defines the current review scope."],
      ["Selection defines the commit", "Only the checked paths belong to the next commit action."],
      ["History connects release signals", "Tags lead into Actions results and then available Releases."]
    ],
    prerequisite: "Select a managed repository with a valid local Git checkout.",
    practice: "Load Status, inspect one diff, and choose a coherent path set without committing it.",
    proof: "The selected paths and commit message describe one reviewable change.",
    recovery: "If the tree is unexpected, refresh Status and confirm the header repository before staging anything."
  },
  "repo-pages": {
    group: "Repo workflows",
    time: "6 minute workflow",
    sectionTitle: "Connect branches to publishing",
    goals: ["Create or select a local branch safely.", "Choose the correct GitHub Pages source model."],
    guideposts: [
      ["Branches change local context", "Creation starts from current HEAD and checkout changes the active branch."],
      ["Pages has two source models", "Branch publishing chooses branch and folder; Actions uses repository "
        + "workflows."],
      ["Deployment proof is explicit", "Success provides a URL; failure remains non-clickable with a red X."]
    ],
    prerequisite: "Use a repository with an initial commit; Pages also requires suitable GitHub permissions.",
    practice: "Identify whether the repository should publish from a branch or an existing Pages workflow.",
    proof: "The saved source matches the repository design and the latest deployment result is unambiguous.",
    recovery: "On failure, open the exact Actions run instead of relying on an older successful site URL."
  },
  automation: {
    group: "Repo workflows",
    time: "5 minute review",
    sectionTitle: "Follow the release signal",
    goals: ["Inspect a workflow run beyond its summary row.", "Publish only a reviewed release form."],
    guideposts: [
      ["Runs are evidence, not decoration", "Summary, Jobs, Artifacts, warnings, and failures explain automation."],
      ["Audio is secondary feedback", "Jingles announce new terminal runs while visible status remains authoritative."],
      ["Release fields are deliberate", "Tag, target, notes, and assets should be reviewed before publication."]
    ],
    prerequisite: "Select a repository whose account can read Actions and Releases.",
    practice: "Open one run detail and locate its Summary, Jobs, and Artifacts before opening Releases.",
    proof: "You can state whether the run succeeded and which release inputs will be published.",
    recovery: "If details do not load, retain the visible error and copy Activity before retrying or reporting it."
  },
  "local-projects": {
    group: "Local workflows",
    time: "8 minute workspace tour",
    sectionTitle: "Stay anchored to one version",
    goals: ["Navigate the project ribbon and workbench without losing context.", "Separate core and advanced actions."],
    guideposts: [
      ["The ribbon owns identity", "Artwork, Project, Feature, Category, and project actions stay together."],
      ["The workbench owns versions", "Selection and its inspector form one connected decision surface."],
      ["Rare actions stay disclosed", "More tools contains notes, sync, comparison, ignore, resources, and rename."]
    ],
    prerequisite: "Create or import at least one Local Mode project.",
    practice: "Select a project, feature, and version, then verify the inspector before opening More tools.",
    proof: "The ribbon, version row, and inspector all describe the same intended folder.",
    recovery: "If a menu moves or context changes unexpectedly, close it and reselect from the ribbon before acting."
  },
  media: {
    group: "Local workflows",
    time: "7 minute workflow",
    sectionTitle: "Protect originals, publish releases",
    goals: ["Create or register an album without risking originals.", "Publish deliberate Shared Resource releases."],
    guideposts: [
      ["Albums stay folder-backed", "GitDesk records a reference and does not own or delete registered originals."],
      ["Intake never overwrites", "Verified files import sequentially and filename collisions receive numbered "
        + "siblings."],
      ["Publication is versioned", "Publish creates a resource; Publish update records later content changes."]
    ],
    prerequisite: "Choose an album parent or an existing image and video folder.",
    practice: "Open an album, inspect one item, and identify whether Publish or Publish update applies.",
    proof: "The album remains intact and the resource shows the intended numbered release.",
    recovery: "If intake rejects a file, review its verified type, size, content, and collision result."
  },
  versions: {
    group: "Local workflows",
    time: "5 minute workflow",
    sectionTitle: "Decide what moves forward",
    goals: [
      "Understand copy versus move during version creation.",
      "Verify the new version before opening or syncing."
    ],
    guideposts: [
      ["The source remains meaningful", "Unchecked paths are copied so the earlier version still retains them."],
      ["Checked means move", "Selected cleanup paths advance into the new version instead of remaining behind."],
      ["Reselect before action", "Folder, notes, resources, and sync use the version currently selected."]
    ],
    prerequisite: "Select an existing version whose contents you understand.",
    practice: "Classify one path to move and one path to copy before opening Create new version.",
    proof: "The new version contains the intended paths and the source retains every path meant to stay copied.",
    recovery: "If the cleanup choice is unclear, cancel and inspect the source folder before creating the version."
  },
  settings: {
    group: "Reference",
    time: "7 minute setup",
    sectionTitle: "Put each preference in its place",
    goals: ["Know which settings area owns each preference.", "Save account and appearance changes deliberately."],
    guideposts: [
      ["GitHub settings own access", "PAT profiles, repository identity, and completion jingles live together."],
      ["User settings own local workflow", "Resources, categories, project migration, and editor choice stay local."],
      ["Theme is a complete system", "Semantic color roles, gradients, and profiles update related surfaces together."]
    ],
    prerequisite: "Know which account owner, local project convention, or appearance you intend to change.",
    practice: "Locate one GitHub, one User, one System, and one Theme control without saving a draft.",
    proof: "The saved setting appears in its owning area and the related UI reflects the intended state.",
    recovery: "If a draft is wrong, use its scoped reset or leave the surface before applying it."
  },
  activity: {
    group: "Reference",
    time: "3 minute recovery guide",
    sectionTitle: "Turn failures into evidence",
    goals: ["Use Activity as the first operation record.", "Capture useful evidence before clearing diagnostics."],
    guideposts: [
      ["Start with the nearest message", "Activity reports the visible foreground operation and its result."],
      ["DevTools adds technical context", "Captured console events can explain errors the status line cannot."],
      ["Preserve evidence first", "Copy Activity before clearing or retrying a failure you may need to report."]
    ],
    prerequisite: "Keep the failed or completed operation visible in the current session.",
    practice: "Open Activity, then DevTools, and locate the Copy Activity and Clear controls.",
    proof: "You can provide the operation, visible result, and captured diagnostic context without exposing a PAT.",
    recovery: "If no useful event appears, reproduce only the safe action once and preserve the resulting message."
  },
  icons: {
    group: "Reference",
    time: "3 minute reference",
    sectionTitle: "Read GitDesk at a glance",
    goals: ["Match guide symbols to app controls.", "Distinguish icon actions from intentional text actions."],
    guideposts: [
      ["Symbols come from GitDesk", "The guide mirrors packaged assets and current app markup instead of inventing "
        + "art."],
      ["Labels still matter", "Accessible names and nearby text explain icons whose meaning is not universal."],
      ["Text actions remain text", "Commands such as Pull, Fetch, Commit, and Publish retain visible labels."]
    ],
    prerequisite: "Use this reference when a symbol in another chapter is unfamiliar.",
    practice: "Find the Guide, Settings, Local Mode, New version, and Remove symbols in the reference.",
    proof: "You can identify the matching app action without relying on color alone.",
    recovery: "When a source icon changes, trust the current app label and update the mirrored guide source."
  }
};
