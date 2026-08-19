/* Remaining ordered GitDesk Guide topics.
 * Local Projects is supplied by gitdesk-guide-topics-local.js before this file appends its registry entry.
 */
window.GitDeskGuideTopics.push(
  {
    id: "repositories",
    icon: "clone",
    title: "Add Repositories",
    kicker: "Clone, add, or create",
    lead: "The Add button in the header opens the Repositories dialog. That dialog is PAT-profile scoped.",
    setup: {
      title: "First-time organization setup",
      items: [
        ["Open GitHub settings", "In GitDesk Settings, select the <code>GitHub settings</code> tab and open "
          + "<code>How to get PAT</code>."],
        ["Set PAT resource owner", "Enter the organization's exact GitHub login in "
          + "<code>PAT resource owner</code>. Use the login from its GitHub URL, not a display name."],
        ["Open the prefilled setup", "Click <code>Open prefilled GitDesk token setup</code>. On GitHub, confirm "
          + "the organization is selected as the Resource owner and choose the repositories GitDesk may manage."],
        ["Create and save the PAT", "Generate the token after any organization approval or policy checks, copy "
          + "the token value, paste it into <code>Add PAT</code>, and click <code>Save PAT profile</code>. "
          + "GitDesk keeps the PAT in the operating system credential keyring."],
        ["Open Repo Mode", "Switch GitDesk to <code>Repo Mode</code>, then click <code>Add</code> beside the "
          + "repository dropdown."],
        ["Select the organization", "In <code>Clone</code> or <code>Create New</code>, choose the organization in "
          + "the Owner dropdown. Clone lists only repositories the active PAT can access."],
        ["Add Existing", "For <code>Add Existing</code>, choose the local repository folder. GitDesk reads the "
          + "organization from that repository's GitHub origin instead of changing it from an Owner dropdown."],
        ["Independent owner profiles", "Personal and organization PATs are stored separately by Resource owner, "
          + "even when GitHub authenticates them as the same human user."],
        ["Owner-routed Git", "Clone, push, publish, and Sync Chains use the PAT profile matching the repository's "
          + "actual owner. Fine-grained PATs are not silently reused across owners."]
      ]
    },
    controls: [
      ["clone", "Clone tab", "Loads GitHub repositories visible to the active account. Choose a destination folder "
        + "and click Clone on a catalog row."],
      ["folder", "Folder picker", "Fills destination, existing repository, or parent folder paths through the "
        + "native folder dialog."],
      ["folder", "Add Existing tab", "Registers an existing local Git repository without moving the folder."],
      ["newProject", "Create New tab", "Creates a GitHub repository and matching local folder. Private, category, "
        + "and AI "
        + "starter files are chosen here."],
      ["category", "Category fields", "Group saved repositories so the header dropdown stays organized."],
      ["trash", "Remove saved repository", "Removes GitDesk's saved record. It does not delete local repository files."]
    ],
    stepsTitle: "Repository Intake",
    steps: [
      "For an organization, create the PAT with that organization selected as its Resource owner.",
      "Paste the generated token value into Add PAT and save the account.",
      "Switch to Repo Mode and click Add beside the repository dropdown.",
      "Choose the organization from the Owner dropdown in Clone or Create New.",
      "Use Clone for an existing GitHub repo, Add Existing for a local Git folder, or Create New for a new GitHub "
        + "repo plus local checkout.",
      "After the dialog registers the repository, open it from the header repository dropdown."
    ]
  },
  {
    id: "overview",
    icon: "overview",
    title: "Overview",
    kicker: "Commit and inspect changes",
    lead: "Overview is the main Repo Mode work page. It shows changed files on the left and the selected diff or "
      + "repository actions on the right.",
    controls: [
      ["folder", "Changed file tree", "Folders can be collapsed. File checkboxes choose what goes into the next "
        + "commit."],
      ["overview", "File row", "Click a file row to load its unified diff in the right pane."],
      ["ignore", "git ignore", "Switches checkboxes into ignore checkboxes. Selecting a path writes it to "
        + "<code>.gitignore</code>."],
      ["overview", "Commit", "Commits selected files. One selected file can use an automatic <code>Update path</code> "
        + "message. Multiple files require a message."],
      ["sync", "Commit and push", "Commits selected files and pushes the active branch in one action."],
      ["group", "History Section", [
        ["newTag", "Tags", "Open History after repository settings and commits are available. Each commit row shows "
          + "the current tag label; tagged commits show their tag, and untagged commits show <code>No tag</code>."],
        ["newTag", "New tag icon", "Click the New Tag icon on an untagged commit. GitDesk opens the tag dialog, "
          + "suggests the next version tag from local and remote tags, fills the tag/message fields, and pushes "
          + "that tag for the selected commit."],
        ["actions", "Green dot flow", "After the tag is pushed, GitDesk marks Actions with a notification dot while "
          + "the tag workflow starts. When the workflow succeeds, Actions shows success and Releases gets the ready "
          + "dot so the user follows tag, then Actions, then Releases."]
      ]]
    ],
    stepsTitle: "Commit Routine",
    steps: [
      "Click Status in the header.",
      "Review the changed file tree.",
      "Click a file to read the diff.",
      "Select only the files that belong together.",
      "Write a commit message when more than one file is selected.",
      "Click Commit for a local commit or Commit and push when the branch should go to GitHub.",
      "If push reaches its 105-second safety boundary, refresh before retrying. The local commit remains intact."
    ]
  },
  {
    id: "repo-pages",
    icon: "pages",
    title: "Branches and Pages",
    kicker: "Repo support pages",
    lead: "Branches changes the local branch. GitHub Pages configures either branch publishing or the repository's "
      + "existing GitHub Actions workflows.",
    controls: [
      ["branches", "Refresh branches", "Reloads local branch metadata and shows the current branch."],
      ["branches", "Create branch", "Creates a branch from the current HEAD and checks it out. The first commit must "
        + "exist before branch creation is enabled."],
      ["branches", "Checkout", "Switches to a listed local branch and refreshes repository status."],
      ["pages", "Pages source", "Chooses <code>Deploy from a branch</code> or <code>GitHub Actions</code>."],
      ["folder", "Branch and folder", "For branch publishing, chooses the repository branch plus root or "
        + "<code>/docs</code>."],
      ["actions", "Repository workflows", "For Actions publishing, lists local <code>.yml</code> and "
        + "<code>.yaml</code> files without selecting, rewriting, or replacing them."],
      ["pages", "Published site", "Shows a green button with the full URL after success and opens it in the default "
        + "browser. A failed latest Pages action shows non-clickable text with a red X."],
      ["newTag", "Create tag", "In History, an untagged commit row shows the app's New Tag icon. The tag dialog "
        + "pushes the tag through GitHub."]
    ],
    stepsTitle: "Branch And Page Sequence",
    steps: [
      "Use Branches when you need a new local branch or need to switch branches.",
      "For branch publishing, choose a committed branch plus root or /docs, then save the Pages source.",
      "For Actions publishing, confirm the repository already contains the intended Pages YAML workflow, then save.",
      "Push workflow or site changes normally; GitDesk never replaces repository-owned workflow YAML.",
      "Use the Pages result or the exact Actions run detail to open a successfully deployed site.",
      "Use History when an untagged commit should become a release tag."
    ]
  },
  {
    id: "automation",
    icon: "actions",
    title: "Actions and Releases",
    kicker: "GitHub automation",
    lead: "Actions reads workflow runs. Releases reads and publishes GitHub releases for the saved owner/repository "
      + "pair.",
    controls: [
      ["actions", "Actions list", "Refresh loads recent workflow runs. Running rows show a spinner, elapsed time, "
        + "branch, event, run number, and status."],
      ["actions", "Completion jingles", "Each newly terminal run queues the saved success or failure jingle. Missing "
        + "or unplayable custom audio uses the matching built-in melody."],
      ["actions", "Run detail", "Click a run to open Summary, Jobs, and Artifacts. A successful Pages deployment shows "
        + "a green URL button that opens the default browser; failure shows a red X."],
      ["releases", "Releases list", "Refresh loads releases. Click a release row to edit it in the form."],
      ["newTag", "New", "Clears the release form so the next publish creates a new release."],
      ["releases", "Publish release", "Creates a release or updates the selected draft using the visible tag, title, "
        + "target, body, label, notes, and assets fields."]
    ],
    stepsTitle: "Build And Release Review",
    steps: [
      "Open Actions after pushing commits, workflows, or tags.",
      "Click a run if the list says building, failure, or warning.",
      "Use GitHub settings to replace the success or failure jingle with a supported audio file.",
      "Open Releases after the build output or release tag exists.",
      "Review the visible release form before publishing."
    ]
  },
  window.GitDeskLocalGuideTopic,
  {
    id: "media",
    icon: "folder",
    title: "Media Albums",
    kicker: "Images, videos, reusable releases",
    lead: "Media Mode creates or registers folder-backed albums, accepts images through one collision-safe intake "
      + "tray, and publishes chosen albums as versioned Shared Resources.",
    controls: [
      ["newProject", "New album", "Creates one album folder directly under the chosen parent and opens it for "
        + "image intake. The name must be portable and cannot replace an existing path."],
      ["folder", "Parent picker", "Chooses where the album folder will be created. The star saves that path as a "
        + "Media favorite; Favorite parents restores any of the 12 newest saved paths."],
      ["folder", "Add existing", "Chooses an existing folder. GitDesk saves a private reference and never moves or "
        + "deletes its original files."],
      ["folder", "Album picker and All Albums", "Switches the only album currently scanned through categorized "
        + "dropdown or full-screen tiles. Unavailable folders remain listed instead of losing their saved identity."],
      ["image", "Album intake", "Drop images, paste clipboard images outside editable fields, or use Choose images. "
        + "Each file is verified, limited to 32 MB, and imported sequentially into the open album."],
      ["copy", "Collision-safe names", "An existing filename is preserved. The imported image receives a numbered "
        + "sibling name such as <code>cover (2).png</code>."],
      ["overview", "Search, type, sort", "Filters the selected album and keeps large libraries bounded to one page."],
      ["image", "Contact sheet", "Shows images and videos as metadata tiles. Right-click a tile and choose Copy to "
        + "copy its actual original file; verified previews remain bounded inside the WebUI."],
      ["image", "Lightbox inspector", "Shows the selected item's relative path, exact bytes, modified time, and "
        + "Open original action."],
      ["resources", "Publish", "Creates a dedicated Shared Resource under <code>media/Resource Name/</code> and "
        + "records "
        + "its first numbered release."],
      ["sync", "Publish update", "Mirrors supported album additions, changes, renames, and removals into the same "
        + "locked resource name, then records the next version only when contents changed."],
      ["trash", "Forget album", "Removes only GitDesk's private album reference. The folder, originals, and any "
        + "published resource remain untouched."]
    ],
    stepsTitle: "Album To Shared Resource",
    steps: [
      "Choose Media Mode, then select New album.",
      "Enter a portable album name and choose its parent folder.",
      "Select the star when that parent should be reused, then choose Create album.",
      "For a folder that already exists, use Add existing instead.",
      "Drag images onto Album intake, focus the tray and paste clipboard images, or use Choose images.",
      "Confirm the intake result; repeated filenames receive numbered siblings and never replace originals.",
      "Use search, type, sort, and page controls to find an item.",
      "Select a tile to inspect it; right-click its thumbnail and choose Copy to paste the actual file elsewhere.",
      "Enter a unique Shared Resource name and choose Publish.",
      "Add the recorded resource to a Local version or repository through the existing Shared Resources workflow.",
      "After the original album changes, return to it and choose Publish update.",
      "Use Update in a project's Shared Resources manager when that project should receive the new release."
    ]
  },
  {
    id: "versions",
    icon: "newVersion",
    title: "Version Workflow",
    kicker: "Copy and move deliberately",
    lead: "Create new version copies the selected version folder and lets you decide which paths move forward "
      + "instead of staying copied.",
    controls: [
      ["newVersion", "Create new version", "Opens the duplicate dialog for the selected local version."],
      ["folder", "Cleanup tree", "Lists files and folders in the source version. Directory rows can represent an "
        + "entire folder."],
      ["sync", "Checked paths", "Checked files and folders move into the new version."],
      ["copy", "Unchecked paths", "Unchecked files and folders are copied and remain in the source version."],
      ["folder", "Open folder", "Opens the selected version folder in the native file manager."],
      ["note", "Project notes", "Opens the selected version's Markdown workspace. Raw Markdown autosaves; preview "
        + "HTML is parsed by Marked and sanitized by DOMPurify."],
      ["sync", "Sync to Private Beta", "Mirrors the selected local version into this project's "
        + "configured Private Beta repository while preserving the destination's Git history. Terminal Private "
        + "Beta opens Overview; later configured repositories remain available in the inline rail."]
    ],
    stepsTitle: "Version Creation Flow",
    steps: [
      "Select the source version in Local Mode.",
      "Click Create new version.",
      "Enter the version label.",
      "Check only the files or folders that should move forward.",
      "Create the version, then select the new version before opening it or syncing it to Private Beta.",
      "Use Project notes when Todo Markdown should live directly inside that selected version."
    ]
  },
  {
    id: "settings",
    icon: "settings",
    title: "Settings",
    kicker: "Accounts, user files, updates",
    lead: "Settings is split into GitHub settings, User settings, System settings, and Theme.",
    controls: [
      ["settings", "GitHub settings", "Add PAT, open PAT help, choose Active PAT Profile, remove token, and save "
        + "GitHub "
        + "owner/repo. It also replaces the success and failure Actions jingles."],
      ["settings", "How to get PAT", "Shows the resource-owner field, permission summary, and prefilled token action."],
      ["settings", "PAT resource owner", "Enter the exact personal or organization login that owns the repositories "
        + "this fine-grained PAT should access."],
      ["settings", "Open prefilled GitDesk token setup", "Opens GitHub with GitDesk's supported repository permissions "
        + "and the entered resource owner preselected."],
      ["settings", "User settings", "Creates Shared Resources, opens editable working folders, and records their "
        + "updates. It also controls category folders, project migration, and the VS Code or VSCodium preference."],
      ["category", "Create categories as folders", "Requires a category for future projects and creates them at "
        + "<code>Parent/categories/Category/Project</code>. The toggle never moves existing projects by itself."],
      ["overview", "Review projects", "Opens the existing-project modal. Each row shows only the project name and its "
        + "metadata category, with a square selection checkbox at left."],
      ["sync", "Apply selected", "Moves every checked complete project folder after validating all destinations. "
        + "Projects without a valid destination remain visible but unavailable for selection."],
      ["resources", "Legacy resource", "Means no numbered version was detected. Record a vN release before relying on "
        + "version tracking."],
      ["resources", "Manage Shared Resources", "In Overview, chooses default reusable files and can merge one resource "
        + "into the active repository."],
      ["settings", "System settings", "Shows GitDesk updates. Check and install asks the backend to find a newer "
        + "matching GitHub release and install it when supported."],
      ["theme", "Theme", "Opens the Color Studio to edit Dark and Light Body text, Secondary text, Headings, "
        + "Labels, shared surfaces, controls, modals, borders, and the notification glow around alerted elements. "
        + "Paintable roles include gradient editors. Profiles save and export the complete look."],
      ["theme", "Reset current theme", "Restores the complete default role map for only the selected appearance. "
        + "Apply colors saves both appearances without rejecting any valid wheel color."]
    ],
    stepsTitle: "Settings Setup",
    steps: [
      "Open GitHub settings and select How to get PAT.",
      "For an organization PAT, set PAT resource owner to the organization's exact GitHub login.",
      "Open the prefilled setup, confirm the Resource owner on GitHub, and generate the token.",
      "Paste the token value into Add PAT and save the account.",
      "Select the active account.",
      "Save GitHub owner and repository when Pages, Actions, Releases, or History need that pair.",
      "Turn on Create categories as folders if future Local Mode projects should use category directories.",
      "Open Review projects, check only the project names to reorganize, then choose Apply selected.",
      "In User settings, choose VS Code or VSCodium; outside macOS, browse to the VSCodium executable before saving.",
      "Use System settings for GitDesk updates.",
      "Open Theme, edit colors or gradients, optionally save or export a profile, then choose Apply colors."
    ]
  },
  {
    id: "activity",
    icon: "debug",
    title: "Activity and DevTools",
    kicker: "Diagnostics",
    lead: "Activity is the bottom console. DevTools is the in-app console capture page.",
    controls: [
      ["copy", "Copy Activity", "Copies visible status, Activity entries, and DevTools entries."],
      ["debug", "DevTools toolbar icon", "Opens captured console calls, uncaught errors, and unhandled promise "
        + "rejections."],
      ["debug", "DevTools button in Activity", "Opens the same diagnostics page from the bottom console."],
      ["trash", "Clear", "Clears captured DevTools entries. It does not clear the Activity log."],
      ["sync", "Busy / Idle", "Shows whether a foreground operation is running."]
    ],
    stepsTitle: "Troubleshooting Flow",
    steps: [
      "Read Activity after an operation succeeds or fails.",
      "Open DevTools when Activity does not explain a UI error.",
      "Use Copy Activity before sharing a failure report.",
      "Clear DevTools only after the captured error is no longer needed."
    ]
  },
  {
    id: "icons",
    icon: "settings",
    title: "Icon Reference",
    kicker: "Sourced from the app",
    lead: "These samples are rendered from the same app markup, app assets, or toolbar icon replacement script used "
      + "by GitDesk.",
    controls: [
      ["app", "App mark", "Loaded from <code>src/gitdesk/ui/app-icon.svg</code>."],
      ["theme", "Theme", "Loaded from <code>darktheme-icon.svg</code>."],
      ["local", "Local Mode", "Copied from <code>local-render.js</code>."],
      ["syncChain", "Sync Chain Setup", "Loaded from <code>sync-chain-icon.svg</code>."],
      ["overview", "Overview", "Copied from <code>index.html</code>."],
      ["clone", "Clone", "Installed by <code>toolbar-icons.js</code> from the app's Clone path."],
      ["branches", "Branches", "Installed by <code>toolbar-icons.js</code> from the app's Branch path."],
      ["actions", "Actions", "Copied from <code>index.html</code>."],
      ["releases", "Releases", "Copied from <code>index.html</code>."],
      ["pages", "GitHub Pages", "Copied from <code>pages-deployment.js</code>."],
      ["settings", "Settings", "Installed by <code>toolbar-icons.js</code> from the app's settings markup."],
      ["debug", "DevTools", "Copied from <code>index.html</code>."],
      ["guide", "Guide", "Loaded from <code>guide-icon.svg</code>."],
      ["folder", "Folder picker", "Copied from the app's native folder picker buttons."],
      ["image", "Project or media image", "Loaded from <code>window.GitDeskIcons.image</code>."],
      ["note", "Project notes", "Loaded from <code>window.GitDeskIcons.note</code>."],
      ["sync", "Sync or move forward", "Loaded from <code>window.GitDeskIcons.sync</code>."],
      ["compare", "Compare versions", "Loaded from <code>window.GitDeskIcons.compare</code>."],
      ["ignore", "Sync Ignore", "Loaded from <code>window.GitDeskIcons.ignore</code>."],
      ["resources", "Shared Resources", "Loaded from <code>window.GitDeskIcons.resources</code>."],
      ["vscode", "Open in editor", "Loaded from <code>window.GitDeskIcons.vscode</code>."],
      ["newProject", "New project", "Loaded from <code>newproject-icon.svg</code>."],
      ["newVersion", "Create new version", "Loaded from <code>window.GitDeskIcons.newVersion</code> in "
        + "<code>toolbar-icons.js</code>."],
      ["rename", "Rename", "Loaded from <code>window.GitDeskIcons.rename</code> in <code>toolbar-icons.js</code>."],
      ["newTag", "New tag", "Loaded from <code>newtag-icon.svg</code>."],
      ["category", "Category", "Used by repository and Local Mode category fields."],
      ["favorite", "Favorite parent", "Copied from <code>local-parent-favorites.js</code>."],
      ["trash", "Remove", "Copied from repository and local project remove buttons."],
      ["copy", "Copy Activity", "Copied from <code>index.html</code>."]
    ],
    stepsTitle: "Icon Source Rules",
    steps: [
      "The guide does not define replacement icon art.",
      "If an app icon changes in the source templates, update the matching source template or asset, then this "
        + "guide has one clear source to mirror.",
      "Text buttons such as Pull, Fetch, Add, Refresh, Status, Commit, Checkout, Publish release, and Check and "
        + "install are intentionally text buttons in the app."
    ]
  }
);
