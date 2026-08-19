/*
 * First half of the ordered GitDesk Guide topic registry.
 * The Local Projects topic loads separately before the remaining topics append and rendering starts.
 */
window.GitDeskGuideTopics = [
  {
    id: "start",
    icon: "app",
    title: "Start Here",
    kicker: "Your first safe pass through GitDesk",
    lead: "Learn how to choose the right workspace, find the control that owns your task, and verify what happened.",
    quickStart: true,
    map: [
      ["1. Header", "Choose Repo Mode for Git repositories or Local Mode for physical project versions."],
      ["2. Toolbar", "In Repo Mode, use the toolbar to access repository-specific features like "
        + "Overview, Branches, Pages, Actions, and Releases without opening GitHub Desktop or "
        + "GitHub.com.<br> In Local Mode, use the toolbar to access Projects, Features, Versions, local "
        + "folder actions, and Sync Chain Setup."],
      ["3. Settings", "Add a GitHub account, add a PAT, and set user name/email for commits."],
      ["4. DevTools", "Open DevTools to see console events, errors, and warnings."]
    ]
  },
  {
    id: "repo-mode",
    icon: "overview",
    title: "Repo Mode",
    kicker: "Git repository workflow",
    lead: "Repo Mode is for cloning, opening, committing, pushing, branching, publishing Pages, watching Actions, "
      + "and publishing Releases.",
    modes: [
      ["Use Repo Mode for", "A folder that already has Git, a GitHub repository you want to clone, commits, pushes, "
        + "pull/fetch, branches, Pages, Actions, releases, and repository settings."],
      ["Do not use Repo Mode for", "Creating numbered physical project versions. That belongs in Local Mode."],
      ["Cloned metadata recovery", "If an older interrupted Sync Chain left an app-cloned folder without "
        + "<code>.git</code>, Status restores only that metadata from the exact saved GitHub origin. Existing "
        + "working-tree files are not replaced or uploaded."]
    ],
    setup: {
      title: "Enable Repo Mode",
      items: [
        ["Open Settings", "Click the Settings toolbar icon, open GitHub settings, add a GitHub account, and paste a "
          + "PAT into <code>Add PAT</code>."],
        ["Save account details", "Save the token, user name, and email so commits, private repositories, Pages, "
          + "Actions, Releases, and History can use the active account."],
        ["Return to Repo Mode", "Switch the header to Repo Mode, then use <code>Add</code> or the repository "
          + "dropdown to choose the repository GitDesk should operate on."]
      ]
    },
    controls: [
      ["newProject", "Add", "Opens Repositories so you can clone a GitHub repository, create a new GitHub "
        + "repository, or "
        + "add/import an existing local Git repository before getting started."],
      ["overview", "Overview", "<code>Commit and Push</code> local file changes or <code>Fetch</code> changes that "
        + "need to be merged with local.<br> Create tags in the <code>History</code> tab."],
      ["clone", "Clone", "Clones a <code>GitHub URL</code> into a chosen local destination and opens the result in "
        + "<code>Overview</code>."],
      ["branches", "Branches", "<code>Refreshes branches</code>, creates a <code>branch</code> from the current "
        + "<code>HEAD</code>, and checks out existing local branches."],
      ["pages", "GitHub Pages", "Chooses <code>Deploy from a branch</code> or <code>GitHub Actions</code>, saves "
        + "GitHub's Pages source, and opens a successful published URL in the default browser."],
      ["actions", "Actions", "Loads <code>workflow runs</code> list and opens <code>run detail pages</code> for "
        + "jobs, artifacts, warnings, and failures."],
      ["releases", "Releases", "Loads GitHub releases, opens a release in the form, creates releases, and publishes "
        + "selected drafts."]
    ],
    stepsTitle: "Repo Mode Startup",
    steps: [
      "Add a GitHub account in Settings first if you need private clone, push, Pages, Actions, or Releases.",
      "Use Add in the header to clone, add existing, or create a repository under the active account.",
      "Choose the saved repository in the header selector.",
      "Open Overview and use Status to load current files before committing."
    ]
  },
  {
    id: "local-mode",
    icon: "local",
    title: "Local Mode",
    kicker: "Folder project workflow",
    lead: "Local Mode is for physical project folders, feature folders, and numbered version folders before or "
      + "without Git.",
    modes: [
      ["Folder shape", "A new local project starts as <code>01 init/v1 project-name</code>. Features contain "
        + "version folders such as <code>v1</code>, <code>v2</code>, and later versions."],
      ["Release handoff", "When a version is ready for Private Beta, configure the project's Sync Chain, "
        + "<strong><u>select that exact version</u></strong>, and click <strong>Sync to Private "
        + "Beta</strong>. GitDesk keeps the Local Mode folder separate from every Git repository stage."]
    ],
    controls: [
      ["newProject", "New project", "Opens the <strong>create/import modal.</strong> <strong>Create "
        + "Project</strong> makes the folder structure. <strong>Import Project</strong> registers an existing "
        + "folder without moving it."],
      ["category", "Project ribbon", "The compact ribbon keeps Project, Category, artwork, and project actions "
        + "together. Its pencil opens one editor for the name, category, or artwork."],
      ["settings", "Create categories as folders", "In User settings, makes future projects use "
        + "<code>Parent/categories/Category/Project</code>. Review projects opens a modal where existing projects "
        + "can be checked and applied."],
      ["image", "Project icon", "The image icon inside Edit project details saves artwork from inside the active "
        + "project as the definitive override. Use automatic icon clears that path so the latest version's "
        + "media/app-icon.svg can appear, with GitDesk's folder artwork as the final fallback."],
      ["favorite", "Favorite parent", "Saves the typed parent folder in the New Project modal for quick reuse."],
      ["settings", "Maintenance", "Reveals Scan categories and Refresh projects in the Local Projects header. Scan "
        + "categories opens a favorite parent's "
        + "<code>categories</code> folder and repairs paths only for projects already saved in GitDesk. "
        + "Unregistered folders are ignored and project files are never changed."],
      ["rename", "Edit project details", "For projects, the pencil opens a modal for name, category, and icon "
        + "changes. The separate version action names a bare <code>v1</code> folder when available."],
      ["newVersion", "Create new version", "Opens the <strong>version creation modal</strong>. <strong>Checked "
        + "paths</strong> are <strong><u>moved</u></strong> into the new version; <strong>unchecked paths</strong> "
        + "are <strong><u>copied</u></strong>."],
      ["settings", "More tools", "Reveals notes, comparison, Shared Resources, Sync Ignore, Sync Chain actions, and "
        + "the separate bare-v1 rename action when it applies."],
      ["note", "Project Markdown notes", "The note icon opens direct-child <code>.md</code> files for the selected "
        + "version. Write, Split, and Preview modes autosave raw Markdown while DOMPurify sanitizes rendered HTML."],
      ["sync", "Inline Sync Chain", "When Public Beta is configured, the inspector shows Local, Private Beta, and "
        + "Public Beta as a two-step rail. Configured Public adds Stage 3, its final action, and its checkbox."],
      ["trash", "Delete version", "The trashcan beside each version permanently deletes that exact folder after "
        + "an explicit confirmation. The deletion cannot be undone."],
      ["trash", "Remove from GitDesk", "The version-list trashcan reused below Category removes the "
        + "<strong><u>saved local project record</u></strong>. It <strong><u>does not</u></strong> delete the "
        + "folder from disk."]
    ],
    stepsTitle: "Local Project Path",
    steps: [
      "Switch the header mode to Local Mode.",
      "Open Local Mode from the toolbar.",
      "In User settings, turn on Create categories as folders if new project roots should live under category folders.",
      "Create or import a project.",
      "Choose a project from the compact ribbon, then select a feature and version in the connected workbench.",
      "Confirm the selected version's feature, project, and path in the inspector beside the version list.",
      "Use the visible create-version, folder, and editor actions; expand More tools for occasional work.",
      "Open Project Markdown notes to create or edit version-scoped Todo files with sanitized live preview.",
      "Use Create new version before risky work or when a feature reaches a checkpoint.",
      "Use the trashcan beside a version only when its complete folder should be permanently deleted.",
      "Configure the project's Private Beta stage in Sync Chain Setup.",
      "Select the exact version to release. A one-stage chain opens Private Beta Overview after sync; a two-stage "
        + "chain stays Local after Step 1; configured Public adds Step 3 and its checkbox to the same inline rail."
    ]
  },
  {
    id: "sync-chains",
    icon: "syncChain",
    title: "Project Sync Chains",
    kicker: "One-way folder promotion",
    lead: "A Sync Chain moves one saved Local Mode project forward through only the repository or local-folder "
      + "stages that project needs.",
    modes: [
      ["Choose the useful stopping point", "The complete path is <code>Local Mode project &rarr; Private Beta "
        + "&rarr; Public Beta &rarr; Public</code>, but any configured stage can be the final destination."],
      ["Repositories or folders", "Each stage may be a managed GitHub repository or an ordinary folder chosen "
        + "through the native picker. Local-folder stages do not require Git or a GitHub account."],
      ["Forward only", "Local versions can replace Private Beta, Private Beta can replace Public Beta, "
        + "and Public Beta can replace Public. Sync Chain controls do not copy a later stage backward."],
      ["Independent Git history", "GitDesk mirrors working files but excludes every source "
        + "<code>.git</code> entry and preserves the destination repository's own "
        + "<code>.git</code> metadata. Each repository keeps its own commits and remote."],
      ["Complete mirror", "By default, a sync replaces the destination working tree with the source snapshot. "
        + "Files no longer present in the source are removed from the destination, so this is not an "
        + "add-only copy."],
      ["Artifact-only terminal release", "When the last two configured stages are repositories, the checkbox on "
        + "the terminal stage copies only the source stage's latest release assets and leaves its checkout unchanged."]
    ],
    setup: {
      title: "Create And Configure A Chain",
      items: [
        ["Open Sync Chain Setup", "Click the Sync Chain icon in the toolbar. The page is available from "
          + "Repo Mode or Local Mode."],
        ["Choose the Local source", "Select a project already registered in Local Mode, then click "
          + "<strong>Create chain</strong>. Finder-only folders cannot be selected, and each Local Mode "
          + "project can own only one chain."],
        ["Configure Private Beta", "Choose a saved repository and click <strong>Save repository</strong>, create a "
          + "new repository, or check <strong>Use a local folder</strong> and choose an ordinary folder."],
        ["Configure later stages", "After Private Beta is assigned, configure Public Beta the same way. "
          + "After Public Beta is assigned, configure Public. GitDesk enforces this stage order."],
        ["Keep paths separate", "The Local project and every configured destination must be distinct and "
          + "non-nested. GitDesk rejects a stage that overlaps another chain folder."]
      ]
    },
    controls: [
      ["syncChain", "Sync Chain Setup", "Opens the saved-chain list and the three ordered repository "
        + "stage cards."],
      ["syncChain", "Saved chain status", "A gray chain icon means the first Local-to-Private-Beta sync has "
        + "not completed. It turns green only after that sync succeeds. The row also shows how many of "
        + "the three repository stages are configured."],
      ["settings", "Save repository", "Assigns the repository selected in a stage dropdown. The dropdown lists "
        + "repositories already managed by GitDesk and includes the owning GitHub account."],
      ["newProject", "Create and assign repository", "Creates a new GitHub repository and separate local "
        + "checkout, registers it in GitDesk, and assigns it to the current stage. Private Beta defaults "
        + "to private; review the privacy checkbox for every new stage."],
      ["folder", "Use a local folder", "Switches that stage away from repository setup. Choose folder opens the "
        + "native picker and saves only the folder returned by the operating system."],
      ["sync", "Sync to Private Beta", "Mirrors the selected Local version into Private Beta. If this is the only "
        + "repository stage, GitDesk opens its Repo Mode Overview after success."],
      ["sync", "Inline Step 1, Step 2, and Step 3", "Version Info shows every configured repository stage and sync "
        + "arrow. Public adds Step 3 after Public Beta. An unchecked mirror opens Public Overview; checked "
        + "artifact-only publication stays in Local Mode because it does not change or validate the Public checkout."],
      ["releases", "Built artifacts only", "Appears beside the terminal repository stage. In a two-stage chain it "
        + "belongs to Public Beta; after Public is configured it moves to Public. It copies the source stage's "
        + "latest release assets with the same tag and never mirrors source files."],
      ["sync", "Sync Public Beta to Public", "Appears after Public Beta and Public are configured. It either performs "
        + "the normal unconditional working-tree replacement or the enabled artifact-only release publication."],
      ["copy", "Last sync receipt", "Each stage records the last successful sync time and file count. If "
        + "the destination changes afterward, the next sync replaces those changes with the source snapshot. "
        + "Only destination <code>.git</code> metadata is retained."],
      ["trash", "Remove stage", "Removes that stage and every later stage from chain metadata after "
        + "confirmation. It does not delete repository folders."],
      ["trash", "Delete chain", "Opens an in-app confirmation, then deletes only the saved definition. Every "
        + "repository and local folder remains on disk."]
    ],
    stepsTitle: "Complete Local-To-Public Workflow",
    steps: [
      "Open Sync Chain Setup, create a chain for the saved Local Mode project, and configure Private Beta.",
      "In Local Mode, select the project, feature, and exact version that is ready for release.",
      "Run Step 1 in Version Info. If Private Beta is terminal, GitDesk opens its Overview. If Public Beta exists, "
        + "GitDesk stays Local and updates the inline receipt.",
      "Open Private Beta in Repo Mode, review and test the mirrored changes, then commit and push them. "
        + "Sync Chains never create commits or push to GitHub for you.",
      "When Public Beta is configured, run Step 2 from the same Version Info rail. Public Beta is replaced even "
        + "when its destination files changed after an earlier sync, then its Overview opens.",
      "Stop at Public Beta when it is the intended destination, or configure Public for one more stage.",
      "For a two-stage binary-only destination, publish a full Private Beta release, check Built artifacts only "
        + "beside Public Beta, then run Step 2.",
      "For a source-free public release, publish a full Public Beta release with its built assets, check Built "
        + "artifacts only in Setup or the Local Mode Public stage, then run Step 3. Public must have a release "
        + "target commit or matching tag.",
      "Leave the checkbox off when Public should receive the working tree, then review, commit, and push normally. "
        + "Every working-tree edge retains only destination <code>.git</code> metadata."
    ]
  },
  {
    id: "header",
    icon: "theme",
    title: "Header",
    kicker: "Always visible controls",
    lead: "The header owns account identity, theme, mode, repository selection, and repository refresh actions.",
    controls: [
      ["app", "GitDesk mark and account avatar", "The app mark is always visible. In Repo Mode, the GitHub avatar "
        + "appears after a saved token is active."],
      ["theme", "Theme", "Switches the UI between light and dark. This guide shows the app's shipped dark theme SVG."],
      ["local", "Repo Mode / Local Mode", "This switch is inserted into the header. Repo Mode opens repository "
        + "workflows. Local Mode opens local folder workflows."],
      ["overview", "Repository dropdown", "Lists saved repositories for the active GitHub account only. Choosing one "
        + "loads status and branches."],
      ["newProject", "Add", "Opens the Repositories dialog for Clone, Add Existing, and Create New."],
      ["overview", "Status", "Reloads the active repository status and updates changed files, diff state, and sync "
        + "warnings."]
    ],
    stepsTitle: "Header Routine",
    steps: [
      "Use the mode switch before choosing a page.",
      "In Repo Mode, select a repository before using Overview, Branches, Pages, Actions, or Releases.",
      "Use Pull when you want to merge remote changes. Use Fetch when GitDesk shows remote commits are available "
        + "and you need local state refreshed.",
      "Use Refresh to reload the GitHub repository catalog in the Repositories dialog."
    ]
  },
  {
    id: "toolbar",
    icon: "overview",
    title: "Toolbar",
    kicker: "Page icons under the header",
    lead: "The toolbar is a horizontal row of icon buttons. Clicking an icon changes the workspace page.",
    controls: [
      ["local", "Local Mode", "Opens Local Projects, including Projects, Features, Versions, and local folder "
        + "actions."],
      ["syncChain", "Sync Chain Setup", "Creates and manages one-way Local, Private Beta, Public Beta, "
        + "and Public promotion chains."],
      ["overview", "Overview", "Opens changed files, diffs, repository action buttons, commit, push, and History."],
      ["clone", "Clone", "Opens the direct clone form for a GitHub clone URL."],
      ["branches", "Branches", "Opens local branch refresh, creation, and checkout."],
      ["actions", "Actions", "Opens GitHub Actions workflow runs."],
      ["releases", "Releases", "Opens release list and publish form."],
      ["pages", "GitHub Pages", "Opens build-source settings and the latest Pages deployment result."],
      ["settings", "Settings", "Opens GitHub settings, User settings, and System settings."],
      ["debug", "DevTools", "Opens captured console events."],
      ["guide", "Guide", "Opens this HTML guide inside the GitDesk workspace."]
    ],
    stepsTitle: "Toolbar Navigation",
    steps: [
      "Click one toolbar icon to make that page the only active workspace page.",
      "Use the active toolbar highlight to confirm where you are.",
      "Most toolbar icons select a page. Local Mode also saves Local Mode, and Actions or Releases may refresh when "
        + "opened."
    ]
  },
];
