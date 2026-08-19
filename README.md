# GitDesk 

## Required Terminal Commands

Run the commands for your operating system from the repository root.

The static promotional webpage has no installation, build, or server command. Open `promotional-site/index.html`
directly in a browser after obtaining the repository files.

### macOS and Linux

```bash
npm install
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python main.py
```

### Windows PowerShell

```powershell
npm install
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python main.py
```

## Command Explanations

1. `npm install` installs the pinned DOMPurify 3.4.13 and Marked 18.0.9 packages, then copies their official browser
   bundles into `src/gitdesk/ui`. GitDesk packages these local files and never loads them from a CDN.
2. `python3 -m venv .venv` or `py -3.10 -m venv .venv` creates an isolated Python environment in `.venv`.
3. The activation command selects that environment for the current terminal. Run it again in each new terminal session.
4. `python -m pip install --upgrade pip` updates the environment's package installer.
5. `python -m pip install -e .` reads `pyproject.toml`, installs the pinned runtime dependencies, and exposes the
   source checkout as an editable `gitdesk` package.
6. `python main.py` launches the GitDesk desktop window and remains running until the app closes.

## User Guide

### Theme colors

Open **Settings** > **Theme**, immediately to the right of **System settings**, to customize GitDesk without mixing
appearance controls into **User settings**. Choose **Dark** or **Light**, then select a swatch to open the continuous
color wheel for **Body text**, **Secondary text**, **Headings**, **Labels**, **Accent & focus**, **Primary actions**,
and **Selected controls**. **Notification glow** defaults to white and changes the halo surrounding any control, row,
or card with a green notification dot. The **Surfaces** group adds shared colors for the app background, navigation,
main panels, sections and cards, secondary surfaces, inputs and controls, modals and menus, and borders and dividers.
These roles update related divs across workspaces together instead of creating a picker for every component. Pick hue
and saturation directly on the wheel and use **Brightness** for lighter or darker results. Each picker shows its
hexadecimal value, and the visible app updates with every draft adjustment.

Choose **Apply colors** to save both appearance palettes for the next launch. **Reset current theme** restores every
role for only the selected Dark or Light appearance. Every valid wheel color can be applied; GitDesk never rejects or
blocks a color based on contrast. It derives visible text for primary and selected buttons without changing their
chosen fill colors. The Dark/Light selector and the topbar theme icon stay synchronized.

Every paintable color row also has a gradient icon immediately to the left of its swatch. Select it to open the visual
Gradient Studio for that semantic role. Choose **Linear** or **Radial**, adjust the angle or center, select a stop on
the large preview, then use the same continuous color wheel and position slider to shape it. Add up to eight stops or
remove a selected stop while keeping at least two. **Use gradient** previews that paint across every element sharing
the role; **Use solid color** removes only that role's custom gradient and returns it to its normal solid treatment.
Reopening a role restores its saved type, geometry, stops, positions, and colors. **Save favorite** adds the current
structured gradient to the reusable library, where it can be selected for another role or removed. Favorites and role
gradients remain drafts until **Apply colors** saves them with both appearance palettes. Notification glow stays
color-only because shadows cannot render a gradient. The editor never exposes a raw CSS field.

Use **Theme profiles** to keep an entire look together. Enter a name and choose **Save current** to store every Dark
and Light semantic color plus the gradients assigned to those roles. Saving the same name updates that profile without
creating a duplicate. Choose a saved profile and select **Preview** to load it as a draft, then use **Apply colors**
to make it active. **Export** opens the operating system's save dialog and writes a versioned `.gitdesk-theme.json`
file; **Delete** removes only the selected saved profile after confirmation. Gradient favorites remain a shared
library, so loading a profile does not erase reusable favorites.
### Preferred external editor

Open **Settings** > **User settings** > **External code editor** to choose **VS Code** or **VSCodium**. GitDesk checks
the system and user Applications folders for both macOS app bundles. On Windows and Linux, select **Browse** and point
GitDesk to the VSCodium executable before saving VSCodium; the selected file must be a recognized `codium` or
`vscodium` executable. GitDesk stores the path as a local non-secret preference and never evaluates it as a shell
command.

User and System settings use three card columns per desktop row and start a new row after the third card. They reduce
to two and then one column as the app window narrows, keeping every editor, metadata, and update control readable.

After **Save editor**, repository actions, each Project-dropdown version shortcut, the selected Version Info action,
Document Builder roots, and exact Document Builder files all open in the chosen editor. Their visible labels,
accessible names, hover tooltips, and activity messages change to **VS Code** or **VSCodium** together. Existing path
ownership and folder validation still run before either editor is launched.
### App updates

Open **Settings** > **System settings** to update GitDesk from the public
[xandlab/gd-public releases](https://github.com/xandlab/gd-public/releases) repository. **Check for updates** performs
only an anonymous public release lookup; it does not download an installer, begin installation, or read any saved
GitHub PAT. When GitDesk finds a newer release with an asset for the current platform, **Install update** becomes
available. On macOS, that second action downloads the exact release tag that was checked, verifies the release asset,
stages the existing app-replacement helper, and restarts GitDesk. If the latest release changes between checking and
installing, GitDesk refuses the stale request and requires another check. Automatic install and restart remain
macOS-only; other supported release targets report that manual installation is required.
### Promotional webpage

Open `promotional-site/index.html` directly in a browser to view the GitDesk promotional webpage. Use
**Transformation**, **Automation**, and **Inside GitDesk** in the header to move through the story, or select
**Product guide** to open the GitDesk Field Manual. Its grouped chapters add focused guideposts, practice, visible
proof, recovery, saved progress, adjacent navigation, and accessible screenshot inspection. After the opening, **Close
the window forest** sends browsers, folders, terminals, notes, release tools, and resources past the viewport. Large
documentation, reference, guide, and learning-site windows include browser chrome, navigation, hierarchy, and
examples rather than thumbnail-like snippets. The scene eases toward the current scroll position instead of jumping
between wheel increments. The Repo Mode and Local Mode tabs change the detailed product view; when a tab has keyboard
focus, the left and right arrow keys switch modes.

The page is a self-contained local HTML, CSS, and JavaScript experience. Its product graphics are constructed from
semantic interface elements and local styles, so it does not require a build, server, network connection, screenshot,
or separate media file. On smaller screens, the section navigation is hidden while the product-guide action,
scroll-driven story, and mode controls remain available. Reduced-motion preferences skip the flying-window sequence
and present the resolved GitDesk workspace directly.
### First use and GitHub sign-in

Open **Settings**, enter a GitHub personal access token plus the exact personal or organization **PAT resource owner**,
and save the profile. GitDesk validates the authenticated user and resource-owner identity, then stores the token in
the operating system credential store under that owner. The token is never written to settings JSON or returned to
the WebUI. A **Bad credentials** or rejected-PAT message occurs before storage and means GitHub did not accept that
submitted token value; generate a new PAT and paste its value rather than its display name.

For PATs saved with this version, GitDesk records GitHub's non-secret expiration timestamp and shows it beside the
active profile under **Settings** > **GitHub settings**. A future date appears as **Expires**; after that moment the
same row changes to **Expired**, the profile remains visible and removable, and GitDesk blocks it before opening the
credential-store item. Save a replacement PAT for the same Resource owner to restore access. Profiles saved by an
older GitDesk version have no recorded expiration date and continue to show their existing saved-token state until a
replacement PAT is saved; GitDesk does not read every Keychain item at startup merely to backfill that metadata.

The active token controls which repositories and organizations GitHub returns:

- A classic PAT can cover personal and organization repositories when it has suitable repository scopes, the
  organization permits classic PAT access, and any required SAML SSO authorization is complete.
- A fine-grained PAT is limited to one resource owner and its selected repositories. An organization-scoped token may
  therefore be necessary for that organization's repositories.
- GitDesk stores one independent PAT profile per resource owner. The same authenticated human can therefore keep
  separate `xander-haj`, `xandland`, and `matrixguides` profiles without any token overwriting another.
- Repository operations select the profile matching the repository's actual GitHub owner. A classic PAT may span
  owners when GitHub authorizes it; a fine-grained PAT is never silently sent to a different owner.

The GitDesk token setup button opens GitHub's fine-grained PAT form with the selected resource owner and these minimum
repository permissions: Metadata read, Actions read, Deployments read, Contents write, Pull requests write, Workflows
write, Pages write, and Administration write. Contents covers clone, fetch, pull, push, tags, and releases; Pull
requests covers creating, discussing, reviewing, and merging Pull Requests; Workflows covers pushes that modify
workflow files; Pages plus Administration covers Pages configuration and repository creation. Deployments read
connects a Pages environment result to its exact Actions run and published URL. GitHub does not currently allow
fine-grained PATs to call the Checks API, so Actions job annotations may be unavailable even though workflow runs,
jobs, artifacts, and deployment results remain readable through the supported permissions.
### Repo Mode repository workflow

The GitHub avatar in the header shows the active PAT profile. Select the arrow immediately to its right to switch
quickly between saved personal and organization profiles. The header and Settings selectors stay synchronized, and
switching profiles restores that profile's managed repository context. The arrow is disabled until another signed-in
profile is available.

The **Repository** dropdown selects a local repository already managed under the active PAT profile. **Add** sits
directly to the right of the dropdown and opens the repository dialog:

- **Clone** lists personal and organization repositories that the active PAT can read. Use the owner dropdown to show
  one personal account or organization, use the text field to filter the remaining rows, choose a destination, then
  select **Clone**. GitDesk uses the cloned repository owner's PAT profile rather than misfiling it under the catalog
  profile.
- **Add Existing** registers an existing local Git repository without cloning, moving, or rewriting it. After choosing
  a folder, GitDesk shows the GitHub owner/repository inferred from its `origin`, including organization-owned remotes.
  A folder without a supported GitHub origin is added as local-only.
- **Create New** creates a GitHub repository plus its matching local repository. Its owner dropdown comes from saved
  PAT profiles, and GitDesk routes creation through the selected owner's profile. GitHub still requires
  repository-creation permission for that owner.

If an organization or repository is absent, refresh the dialog and check the token's resource owner, repository
selection, scopes, organization PAT policy, approval state, and SSO authorization. GitDesk does not invent or bypass
access that GitHub did not grant.

**Status** validates the exact saved repository path. If an interrupted Sync Chain from an older GitDesk build left
an app-cloned folder without `.git`, Status first recovers an unfinished local transaction when possible. Otherwise,
it clones the exact saved GitHub origin into a temporary sibling and installs only its `.git` metadata. Existing
working-tree files are never replaced or uploaded by this repair; Status then retries against the restored repository.
### Local Mode project workspace

Choose **Local Mode** for physical project, feature, and version folders. The compact ribbon keeps artwork, Project,
Feature, Category, and project actions together. Switching Project validates its cached child paths, shows the
acknowledged context, then refreshes only that project's folders and resource metadata. Feature keeps **Create new
feature** above choices. The [Local Mode guide](docs/local-mode.md) covers Versions, artwork, and Sync Chain promotion.

Project artwork resolves in this order: the validated image selected in **Edit project details**, the latest
version's validated `media/app-icon.svg`, then GitDesk's generic folder placeholder. **Use automatic icon** clears
only the saved pencil override so the latest-version app icon can become visible automatically.
### Media Mode album workspace

Choose **Media Mode** in the header, then use **New album** to create an album folder. Enter the album name, choose
its parent with the native folder button, and select the star to save that parent as a Media favorite. The newest
favorite is prefilled the next time the dialog opens, and any saved parent can be restored from **Favorite parents**.
GitDesk creates the album as one direct child of that parent, registers it, and opens it immediately. Use
**Add existing** instead when an image or video folder already exists; GitDesk saves an owner-only reference without
moving, renaming, copying, or deleting its originals.

An open, connected album shows an **Album intake** tray above its contact sheet. Drag image files onto the tray, focus
the tray and paste clipboard images, or choose **Choose images** for a keyboard-accessible multi-file picker.
GitDesk accepts content-verified PNG, JPEG, GIF, WebP, BMP, ICO, and passive self-contained SVG files up to 32 MB
each. Files are imported sequentially as direct children of the open album. If a filename already exists, GitDesk
creates a numbered sibling such as `cover (2).png`; it never replaces the original. Unsupported, empty, oversized,
renamed non-image, or unsafe SVG content is rejected.

GitDesk scans only the selected album and displays a paged contact sheet with search, image/video filtering, and
name, newest, or size sorting. Select a tile to inspect its path, byte size, and modified time. Supported raster
previews are verified and loaded only as their tiles approach the viewport; large images, SVG files, and videos stay
metadata-only in the WebUI and open through the operating system when **Open original** is selected. After selecting
a tile, right-click its thumbnail and choose **Copy** to place the actual original image or video file on the desktop
clipboard. Paste it into Finder, File Explorer, or another application that accepts files.

The album dropdown and adjacent full-screen **All Albums** view switch between categorized saved albums.
**Open folder** reveals the selected album in the native file manager, and changing the album name updates only its
GitDesk label. **Forget album** removes only the private GitDesk reference: it does not delete the folder, its files,
or a Shared Resource previously published from it. A disconnected folder remains visible as unavailable so its saved
identity is not silently lost.

Enter a unique resource name and choose **Publish** to turn the selected album into a dedicated Shared Resource. The
resource installs beneath `media/Resource Name/` in a project, preserving the album's nested folder organization.
The first publish records `v1`; after images or videos are added, changed, renamed, or removed in the original album,
choose **Publish update** to mirror the current supported contents and record the next version only when content
changed. The resource name locks after first publication so later updates cannot drift into another resource.
### Shared Resources and Document Builder

Open **Settings** > **User settings** to create **Shared Resources**. Each resource is an editable folder containing
files at the same relative paths they should use inside a project. The checkout's
`Shared-Resources/categories` directory is read-only application content and is packaged under that same path.
Source and packaged runs materialize editable copies under GitDesk's operating-system user-data directory, never
inside the source repository. The retired `AI-Skills` directory is not read or packaged. The app derives a revision
from the resource's file paths and contents, but folder edits remain a working copy until an explicit release is
recorded. Creating a new resource records its empty `v1`. After adding, replacing, or removing files, return to
Settings and choose **Update** beside that resource to record the next numbered snapshot. A resource with no detected
numbered release is marked **Legacy**; record a `vN` release before expecting version tracking to work.

The **Shared Resources** checklist in **New Project** controls which resources are merged into the project's initial
version. Only recorded resources can be selected. The selected Local version inspector lists each tracked resource
and its installed `vN` directly below Location, with a newer available version called out beside older installs.
Select any version, expand **More tools**, then choose **Manage Shared Resources**:

- Check an available resource and choose **Apply changes** to add its files.
- Uncheck an installed resource and apply to remove only the paths recorded for that resource.
- Choose **Update** beside an outdated or incomplete resource to merge its current revision into matching paths.
- Choose **Merge vN** for a tracked Legacy installation to merge that numbered release and enable version tracking.

Files copied before this tracking system are deliberately not inferred as resource-owned. Checking and applying a
numbered resource merges it into the current version: matching resource paths receive the numbered snapshot, while
all differently named project files remain untouched. GitDesk records ownership only for the numbered snapshot paths
it actually merged, rather than claiming unrelated project-authored content.

These operations never replace the version folder. Updates copy recorded snapshot files to their matching relative
paths and leave every unrelated project file in place. Removal deletes only that resource's private installation
manifest paths and prunes directories only when they are empty, so project-specific progress histories, learned
histories, bugfix records, source files, and other resources are not removed merely because they share a parent folder.
If a tracked resource file was edited inside the project, removal preserves that changed file and drops only GitDesk's
ownership record for it. When a newer release omits a formerly managed path, Update retires that path only if its
current bytes still match the prior installed digest; a project-edited version remains in place.

### Sync Chains

Sync Chains accept managed repositories or native-picker folders and may stop after any configured stage. Their
terminal repository edge offers **Built artifacts only**; the [Local Mode guide](docs/local-mode.md) has full steps.

In **Document Builder**, select a saved file and choose **Add to Shared Resources**. Select the destination resource,
edit the project-relative path if needed, and add it. Document Builder removes its numeric sequence from the suggested
filename while leaving the field editable for nested paths such as `.codex/skills/user-laws.md`. Adding the file
changes the resource working copy; **Update Shared Resource** writes later edits to the same linked path and records
the resource's next numbered snapshot. Local Mode versions using an older snapshot then show an **Update** action in
the manager and keep displaying their installed version in Local Mode.
### Daily repository actions

After selecting a repository, **Status** refreshes changed files and **Fetch** reads remote updates. **Pull** becomes
available only when the active branch has a fetched matching branch on origin. A newly cloned empty GitHub repository
has no remote branch to pull yet: use **Commit and push** to create it, or use **Fetch** after someone creates it
elsewhere. The Overview workspace supports selecting changed paths, inspecting diffs, committing, and pushing.
Branches, Actions, Releases, Pages, and project workflows use the active repository and account context.

Open **Pull Requests** in Repo Mode to list the selected repository's open work. Select a row to inspect its changed
files and escaped patches, commits, requested reviewers, conversation, and submitted reviews. The page can create a
normal or draft Pull Request, add a conversation comment, submit Approve, Request changes, or Comment reviews, and
merge with a merge commit, squash, or rebase. Every request resolves the selected checkout's live GitHub `origin` and
uses the PAT profile for that exact repository owner.

GitDesk bounds freshness, staging, and the push child process. If push cannot settle within 105 seconds, controls
return and the local commit remains; refresh before retrying because the remote state may be ahead.

After **Commit and push** succeeds, Overview applies the final post-push working-tree status without repeating the
same full status scan. GitDesk also follows the pushed commit SHA with bounded Actions refreshes, so a workflow run
that GitHub creates after the push response appears in the open app without requiring a restart. Opening Actions or
choosing **Refresh** while another Actions request is finishing queues one follow-up refresh instead of dropping it.

In **Actions**, select a workflow run and then choose a job from the detail sidebar. Each reported job step is a
keyboard-accessible disclosure: select the step row to download the job log and reveal that step's full line-numbered
console output directly beneath it in the normal Actions page flow. GitDesk downloads the log only when first
requested and reuses it while that job remains cached in the current repository session. A step with no matching
output says so explicitly; expired or unavailable GitHub logs show a localized retry action without hiding job
status, warnings, errors, or artifacts. GitDesk queues a distinct built-in success or failure jingle once for every
newly completed run. In **Settings** > **GitHub settings**, replace either jingle with an AAC, FLAC, M4A, MP3, OGG,
or WAV file up to 10 MB. GitDesk saves its path in owner-only `action-jingles.json`; failures use the built-in jingle.

In **GitHub Pages**, choose **Deploy from a branch** to configure GitHub's legacy branch plus `/` or `/docs` source.
Choose **GitHub Actions** when the repository already contains a Pages workflow under `.github/workflows`. GitDesk
shows the local `.yml` and `.yaml` files for context, sets GitHub's Pages build type to `workflow`, and does not choose,
rewrite, or replace those repository-owned workflows. A successful latest Pages deployment shows a prominent green
**Visit deployed site** control with the complete published URL on the Pages setup screen and in the exact Actions
run's Summary, selected Job, and selected Artifact views. Every placement uses the same dimensions and interaction;
selecting it asks the operating system to open the URL in the user's default browser. A failed deployment shows
non-clickable text with a red X so an older successful site URL is not presented as the result of the failed run.
Existing fine-grained tokens created before this feature need Deployments read permission before GitDesk can match
deployment status to Actions.
### Backup Mode

Choose **Backup Mode**, then open **Choose folder** to save favorites and apply a local, USB, or external-drive target.
**Create first backup** reviews every registered Local, Repo, Media, and settings source. Check roots or individual
content and confirm; only checked content is copied. The Explorer-style dialog reports factual calculation, copying,
verification, item, data, speed, and time progress. **Cancel** removes staging and creates no version. Completion or
failure remains until dismissed. Item-local copy failures continue automatically: the completed dialog lists every
skipped item with **Open in Finder**, without printing its captured original location on screen.

Each dated `gitdesk backups YYYY-MM-DD HH-MM-SS/` folder contains the Local, Repo, Media, and settings groups.
Stable path hashes prevent name collisions.

After the first backup, use **Scan for changes** at any time. While GitDesk remains open, it also scans every 15
minutes and again when the app regains focus after a scan is due. GitDesk honors the saved last-scan time after a
restart and does not launch another automatic scan while detected changes are waiting for review; **Scan for
changes** remains available when you explicitly want to refresh them. Added, modified, deleted, or unavailable paths
appear on the Backup page; the Backup toolbar icon receives a notification dot until the state is current. **Sync
backup** reopens the required review with **Detected changes** above the normal source groups. Every available folder
that owns a detected change starts checked. The remaining Local, Repo, Media, and settings sources stay visible below
and start unchecked, so you can add individual folders or use **Select all** to include everything. Only the confirmed
checked scope enters that sync. GitDesk applies selection changes and deletions, verifies source and destination
content, then installs a dated version with a full manifest and `backup-log.json`. Prior versions remain unchanged. A
missing selected source, recursive or full/disconnected/read-only destination, or verification failure blocks the
transaction. A per-item collision, source change, read failure, link failure, or folder failure is excluded from the
installed manifest, recorded with its original location in `backup-log.json`, and kept as a detected change for the
next sync. Unsupported removable-drive metadata is logged without deleting verified content.

To consolidate dated versions without removing their history, select an older row under **Backup versions** as the
parent, then choose **Merge down**. GitDesk verifies the selected parent and every newer child, replays those children
oldest-to-newest into a staged copy of the parent, and replaces the parent only after the cumulative manifest passes
verification. A child's confirmed partial scope updates or deletes only that scope in the parent; excluded parent
content remains in place. Every child folder remains unchanged, and the newest child remains the normal baseline for
later scans and backups.

Loading and errors appear in the app status/DevTools surfaces. Disabled account or repository controls indicate that
GitDesk needs a signed-in account or active managed repository before that action can run.

## What It Manages

- Local projects with optional category folders, feature folders, and physical `vN` version folders.
- Folder-backed Media albums with paged contact sheets and explicit versioned Shared Resource publication.
- Version comparison, copy-forward, GitHub promotion, Pull Requests, Pages, Actions, and releases.
- Complete versioned Backup Mode snapshots, branch basics, Shared Resources, metadata backup, and project repair.

## Runtime Storage

GitDesk writes settings, repository records, Document Builder records, Media records, Shared Resource manifests,
Sync Ignore rules, Local Activity, and Backup state only beneath the operating system's per-user GitDesk
configuration directory. Editable Shared Resources use the operating system's per-user GitDesk data directory.
Atomic private writes reject any destination inside a GitDesk source checkout, including a repository-root
`local files` folder. Local projects, document roots, Media albums, managed repositories, and Backup destinations are
created or registered only at the external folders the user explicitly chooses; their private registry data remains
outside the checkout.

The repository contains only read-only application inputs needed to build GitDesk. Deleting obsolete `AI-Skills`
and `local files` directories does not remove a runtime dependency or change where GitDesk stores user data.

## Desktop Builds

Use `.github/workflows/build-app.yml` to produce desktop artifacts for macOS, Windows, and Linux. Tagged releases
attach separately labeled `GitDesk-macOS-arm64.dmg` and `GitDesk-macOS-x86_64.dmg` assets. Each macOS app contains
only its architecture's WebUI native runtime, and CI verifies the executable and runtime before creating the DMG.
The Intel job also preserves the exact x86_64 OpenSSL pair that successfully initializes cryptography before
packaging, replaces any older same-named PyInstaller copy before signing, and verifies the required SSL symbol in the
finished app before launching its non-UI packaged self-check.
Every target packages the canonical read-only `Shared-Resources/categories` catalog and has no `AI-Skills` input.

## Secret Storage

GitHub PATs are not written to source files, settings JSON, logs, browser storage, or repository folders.
GitDesk stores PATs under its stable `GitDesk` service in macOS Keychain, Windows Credential Locker, or the supported
Linux secret-service backend selected by `keyring`. Non-secret accounts, repositories, and UI preferences remain in
LocalApp metadata JSON. If a regressed build previously created `tokens.vault.json` and `tokens.key`, GitDesk migrates
every usable PAT into the system credential store before removing those obsolete local secret files.

LocalApp metadata records whether each PAT profile is configured and GitHub's non-secret expiration timestamp when
one was reported; launching GitDesk and rendering its account list do not read any credential item. GitDesk requests
only the selected profile's `GitDesk` / `github-token:<login>` item when a Git or GitHub operation actually needs that
PAT. After the operating system authorizes that read, GitDesk keeps the PAT only in volatile process memory for the
current app session, so later operations for the same profile do not reopen the prompt. Switching profiles can
request that other profile's item on its first use.

The operating system owns the Keychain password dialog and validates its password; GitDesk never receives the entered
password. A newly rebuilt ad-hoc-signed macOS app can require fresh approval for an item even when its bundle identifier
is unchanged. Closing GitDesk discards its session copy. Saving or removing a profile updates Keychain first and then
updates or clears the matching non-secret state; no PAT is written to LocalApp JSON.
