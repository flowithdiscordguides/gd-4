/* Local Workbench guide topic kept separate so the guide mirrors its progressive-disclosure workflow. */

window.GitDeskLocalGuideTopic = {
  id: "local-projects",
  icon: "local",
  title: "Local Projects",
  kicker: "Project ribbon and workbench",
  lead: "Local Mode keeps artwork, Project, Feature, and Category context in a compact ribbon, then gives Versions "
    + "and the selected-version inspector the connected workbench.",
  controls: [
    ["newProject", "New project", "Opens the Create Project and Import Project modal."],
    ["settings", "Maintenance", "Reveals Scan categories and Refresh projects without competing with the primary "
      + "New project action."],
    ["favorite", "Scan categories", "Scan a favorite parent's <code>categories</code> folder to repair matching "
      + "saved-project paths. The scan never registers or removes projects and never changes project contents."],
    ["local", "Project dropdown", "Opens below its trigger with five extra listings and reveals the selected project "
      + "once. It never recenters or repositions itself after opening; wheel, scrollbar, and keyboard navigation own "
      + "its list position. Only a mouse click selects or dismisses it. Categories and projects are alphabetized; "
      + "selection validates cached Feature and Version paths, changes the ribbon after acknowledgement, then "
      + "refreshes only that project's full tree. "
      + "Each editor button opens its latest version without selecting that project first."],
    ["folder", "All Projects", "The full-screen icon beside the Project dropdown opens category sections of "
      + "custom, latest-version app, or folder artwork tiles. Drag Icon size to change grid density; select a "
      + "project to return to its Local Projects workspace."],
    ["category", "Project ribbon", "Starts with priority-resolved artwork, then keeps the Project and Feature "
      + "dropdowns "
      + "together before Category, Edit project details, and Remove from GitDesk at the right."],
    ["image", "Project icon controls", "The image control saves a definitive in-project override. Use automatic "
      + "icon clears it so the latest version's media/app-icon.svg can appear; otherwise GitDesk uses its folder "
      + "placeholder."],
    ["settings", "Category-folder migration", "Review projects shows each legacy project name and metadata "
      + "category. Apply selected moves puts each checked complete project root into "
      + "<code>Parent/categories/Category/Project</code>."],
    ["newProject", "Feature dropdown", "Keeps Create new feature and its name field above the ordered feature choices. "
      + "Create starts from the selected or latest version without moving the menu during manual navigation."],
    ["newVersion", "Versions", "The full-width list selects a physical version; the inspector shows its order, "
      + "project, "
      + "feature, path, and tracked Shared Resource versions."],
    ["newVersion", "Core actions", "Create new version, Open version folder, and Open version in the preferred "
      + "editor stay visible beneath the selected-version information."],
    ["settings", "More tools", "Reveals occasional actions such as project notes, sync, Sync Ignore, Shared Resources, "
      + "comparison, and the separate v1 rename action when it applies."],
    ["note", "Project Markdown notes", "Creates and edits direct-child Markdown files in the selected version with "
      + "autosave, revision conflicts, and DOMPurify-sanitized preview."],
    ["sync", "Inline promotion rail", "Shows every configured repository stage and sync edge. Public adds Step 3 "
      + "plus the saved Built artifacts only checkbox. Step 1 stays green for the exact selected version until "
      + "Step 2 succeeds."],
    ["trash", "Delete version", "The trashcan beside a version permanently deletes that exact folder after "
      + "explicit confirmation. The deletion cannot be undone."]
  ],
  stepsTitle: "Local Work Path",
  steps: [
    "Create or import a local project.",
    "Choose the project from the Project value in the compact ribbon.",
    "Open All Projects when a visual category and artwork overview is more useful.",
    "Open Feature to create from the form at the top or select an existing feature below it.",
    "Select a version and confirm its project, feature, path, and Shared Resources in the inspector.",
    "Use Create new version, Open version folder, or the preferred editor directly from the core action row.",
    "Expand More tools for notes, sync, comparison, Sync Ignore, Shared Resources, or v1 renaming.",
    "Use the version-row trashcan only when its complete folder should be permanently deleted.",
    "When that exact version is ready, use sync for terminal Private Beta or a configured edge in the inline rail."
  ]
};
