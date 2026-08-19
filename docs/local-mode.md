# Local Mode Project Workspace

Use this guide to select a saved project, work through its physical feature/version hierarchy, and understand
which project artwork GitDesk displays. The UI labels below match the current Local Mode source.


Choose **Local Mode** in the header to work with physical project, feature, and version folders. The Local Projects
page puts project artwork, **Project**, **Feature**, and Category context in a compact ribbon, then connects
**Versions** and the selected-version inspector in one workbench. Use the **Project** value in the ribbon to switch
saved projects and **Feature** to change the active feature. **New project** remains
the primary page action; **Maintenance** reveals **Scan categories** and **Refresh projects** when needed. GitDesk
presents an acknowledged project from its cached Feature and Version context before refreshing that project's full
folder, Shared Resource, and artwork state. The Project control is briefly unavailable during the validated
acknowledgement, and a late refresh from an older selection cannot replace the project currently shown. GitDesk
presents the cached Local workspace as soon as the mode control is pressed, shows **Opening Local Mode…** while it
verifies real folder access, and then reconciles the
returned filesystem snapshot in place. A failed authorization restores the prior mode and opens the visible diagnostics
instead of leaving the control unresponsive. The Project menu alphabetizes category headings and the projects
inside each category, opens below the Project trigger, and provides room for five additional project listings when
window space and the saved project count permit. It reveals the selected project once when opened, then never
recenters or repositions itself. Wheel, scrollbar, and keyboard navigation own its list position; state refreshes and
window resizing leave that position unchanged. Only a mouse click on its trigger, a project or editor listing, or
another app control dismisses it. Arrow, Home, and End keys move through projects; Enter or Space selects without
dismissing the menu. Every project listing
has its own selected-editor button immediately to the right. That button opens the latest physical version in the
project's latest feature without first selecting the project; it is disabled only when that listed project has no
version. Select the full-screen icon immediately to the
right of the closed Project dropdown to open **All Projects**. This page groups saved projects under their category
headers and shows each project with the same validated custom, latest-version app, or folder artwork used by the
project ribbon, with the project name underneath. Drag
the **Icon size** slider to change how many project tiles fit in each row. Single-click a tile to select that project
through the same Local Mode action as the dropdown and return to its project workspace. Use the back arrow or Escape
to return without changing projects. The project ribbon presents the Project picker, Feature picker, and Category as
compact context without showing the project path. Its compact action dock contains the pencil for **Edit project
details** and the same trashcan used beside version listings to remove the project from GitDesk. The editor can change
the project name, category, custom icon, or any combination of those
details. Its image and folder controls are icons with fast hover labels rather than text buttons. Name and category
changes are applied with **Save changes**; icon choices save immediately so the preview and project card stay current.
Removing a project only removes its saved GitDesk record; it does not delete the project folder.

Open **Settings** > **User settings** and turn on **Create categories as folders** when Local Mode projects should use
`Parent/categories/Category/Project` on disk instead of `Parent/Project`. The literal `categories` folder contains
every category-label folder. A category is required when creating a project while this setting is on. Existing and
imported projects are never moved by the toggle alone: the same settings card lists each project that still needs
physical organization through the **Review projects** button. That action opens a focused modal whose rows show only
the project name and its metadata category, with a square checkbox at left. Select the projects to migrate, then
choose **Apply selected**. GitDesk preflights the complete selection and moves each entire project root—including root
files, feature folders, version folders, artwork, and any Git-enabled content—into its category folder below the
`categories` container. Projects without a valid destination remain visible but unavailable for selection. Saved
Local Mode selections, icons, permission records, Project Hub history, managed repository paths, Sync Chains, Shared
Resource installations, and Local Activity paths follow a successful move.

The **New Project** parent-folder row can save a chosen parent as a favorite. The **Scan categories** metadata-repair
action is under **Maintenance** in the **Local Projects** header. It opens the native folder picker at the first saved
favorite when available so you can choose its literal `categories` folder. GitDesk reads direct category and
project folders only to find new locations for projects already registered in Local Mode. It never imports an
unregistered discovered folder and never removes an unmatched saved project. A uniquely matched saved project receives
the path and category of its detected folder, and that root change follows through Local selections, icons,
permissions, Project Hub history, managed repositories, Sync Chains, Shared Resource installations, and Local
Activity metadata. Ambiguous names stop the scan instead of guessing. The scan writes only GitDesk's private metadata
files: it never creates, edits, moves, renames, or deletes anything inside the selected `categories` folder or its
projects.

Project artwork follows one priority order. A validated image selected through **Edit project details** is the
definitive source. Without that saved override, GitDesk checks `media/app-icon.svg` inside the latest physical
version of the latest ordered feature that contains versions. If neither source supplies a usable image, the
generic folder icon remains visible. **All Projects** uses the same order.

The project ribbon places this priority-resolved artwork at the far left, then keeps compact Project and Feature
dropdowns together before Category and the existing edit and remove controls at the far right.

Select the metadata editor's image icon to pick a PNG, JPEG, GIF, WebP, BMP, ICO, or SVG file no larger than
5 MB from somewhere inside the active project folder. GitDesk validates the content, rejects scriptable or
externally linked SVG artwork, and saves only the image's absolute path in the owner-only LocalApp metadata
registry. The image remains in the project folder and is not copied, edited, or added to a version folder by
GitDesk. Selecting another file replaces the saved path. The folder-shaped **Use automatic icon** action clears
that custom path and restores latest-version app-icon discovery. A saved custom path remains authoritative; if
it is moved, deleted, or becomes invalid, the page safely uses the folder placeholder until the user replaces or
clears it. An absent or invalid automatic app icon also falls back to the folder without blocking the project.

Open **Feature** in the ribbon to load another feature's physical versions. The dropdown keeps **Create new feature**
at the top, above the independently scrollable choices. Enter a **Feature name** and use **Create** to start from the
current project state. Feature choices show their version counts and legacy state. Opening the menu reveals the
selected feature once; after that, wheel, scrollbar, and keyboard navigation own its position through state refreshes.
The Versions region uses the reclaimed workbench width for its selectable list and an inspector containing the
selected version's sequence, project, feature, physical path, and Shared Resources. The core
action row keeps **Create new version**, **Open version folder**, and the preferred editor visible. Expand **More
tools** for rename-v1, project notes, comparison, Shared Resources, Sync Ignore, and configured Sync Chain actions.
Hover or focus an icon to read its accessible action label within 0.2 seconds. Every version listing has a trashcan
immediately to its right. After an explicit confirmation, that action permanently deletes that version folder and
everything inside it, removes its
live Shared Resources and Local Activity snapshot metadata, and cannot be undone. If the deleted version was active,
GitDesk selects the latest remaining version in that feature; an empty feature remains selected when no versions are
left. Version listings keep uniform content-sized rows even when only one item is present or the section is
collapsed. The Versions list scrolls independently and keeps the selected version visible. Empty and disabled
controls indicate that a project, feature, version, or required Sync Chain has not yet been selected.

Every stage can be a managed GitHub repository or an ordinary folder. In Sync Chain Setup, check **Use a local
folder**, then choose the destination through the native picker. That stage does not require Git metadata or a GitHub
account. Repository and folder stages may be combined, but the Local project and every destination must be separate,
non-nested folders. Working-tree sync remains a forward-only exact mirror; it retains destination `.git` metadata
when present and never opens a local-folder destination in Repo Mode.

Only configure the stages the project needs. With Private Beta alone, syncing the selected version stops there. Add
Public Beta for the visible `Selected version → Private Beta → Public Beta` rail, and add Public only when a third
destination is useful. After Step 1 succeeds for the exact selected version, its arrow stays solid green until Step 2
succeeds. One module-owned pending state disables the complete rail until the active edge settles.

**Built artifacts only** follows the terminal configured repository stage. In a two-stage chain, it appears beside
Public Beta and makes Step 2 relay only Private Beta's latest full release assets. After Public is configured, the
option moves beside Public and applies to Step 3 instead. Both source and destination must be managed repositories;
local-folder edges always use the working-tree mirror. Artifact delivery creates or resumes a destination draft with
the same tag, title, and notes, verifies its exact asset set, and publishes it as latest without copying source files
or opening the unchanged destination checkout. Independent owner-routed PATs need Contents read on the source and
Contents plus Workflows write on the destination. A conflicting published release remains untouched.

**Remove stage** and **Delete chain** open GitDesk-owned confirmation dialogs that work inside the desktop WebView.
They remove only saved setup metadata. Every repository and ordinary local folder remains on disk.

Expand **More tools** and use the sync-warning icon to open **Sync Ignore**. You can also open **Sync Chain
Setup**, select a project from **Saved chains**, choose its exact Local source version, and select **Sync Ignore**.
Both entry points open the same project-scoped editor. Its file tree contains every selectable non-`.git` file and
folder without a display cutoff, and full names remain visible. Every folder starts collapsed; select a folder row to
expand or collapse its contents, and use its checkbox to include or remove that complete folder subtree. A partially
selected folder shows an indeterminate checkbox even while its contents are collapsed. Select individual files as
needed, then choose **Apply** at the top. These version-relative paths stay out of the Local-to-Private-Beta edge.
Rules are stored per Local project in the owner-only
`sync-ignore.json` metadata file. The next exact mirror omits those paths and removes any older destination copies;
later repository-to-repository edges remain exact mirrors of their source stage. Open **Settings** > **System
settings** > **Project metadata files** to view any allowlisted non-secret JSON or reveal GitDesk's metadata folder.

Expand **More tools** and select the note icon to open that version's Markdown workspace. Create direct-child `.md`
files, choose a note from the sidebar, and use **Write**, **Split**, or **Preview**. Typing updates the preview
immediately and autosaves the raw UTF-8 Markdown. `Cmd+S` or `Ctrl+S` flushes a pending save. GitDesk checks the
content revision before replacement, so an edit made in the selected external editor produces a visible conflict
instead of being silently overwritten. Preview HTML is never saved: Marked parses the Markdown, DOMPurify sanitizes
the result, and only the sanitized HTML reaches the preview. Embedded active content and non-HTTP links cannot
navigate the WebView.
