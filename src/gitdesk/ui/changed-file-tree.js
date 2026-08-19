/*
  Changed-file tree renderer for Overview, including foldable folders and ignore controls.
*/

// Builds static HTML for the changed-file tree while Overview owns state and events.
(() => {
// Escapes path and label text before inserting status-derived values into markup.
function escapeHtml(value) {
  return String(value == null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Normalizes Git paths so folders split consistently across platforms.
function normalizedPath(pathValue) {
  return String(pathValue || "").replace(/\\/g, "/");
}

// Returns a selection without an ignored target or any path contained by that target.
function withoutIgnoredPath(selectedPaths, ignoredPathValue) {
  const ignoredPath = normalizedPath(ignoredPathValue).replace(/\/+$/g, "");
  return new Set(Array.from(selectedPaths).filter((selectedPath) => {
    const normalized = normalizedPath(selectedPath).replace(/\/+$/g, "");
    return normalized !== ignoredPath && !normalized.startsWith(`${ignoredPath}/`);
  }));
}

// Creates a mutable folder node used only during tree construction.
function createFolderNode(name, path) {
  return {
    name,
    path,
    folders: new Map(),
    files: [],
  };
}

// Inserts one status file into the matching folder node.
function insertFile(rootNode, file) {
  const safePath = normalizedPath(file.path);
  const parts = safePath.split("/").filter(Boolean);
  if (!parts.length) return;

  let currentNode = rootNode;
  parts.slice(0, -1).forEach((part, index) => {
    const folderPath = parts.slice(0, index + 1).join("/");
    if (!currentNode.folders.has(part)) {
      currentNode.folders.set(part, createFolderNode(part, folderPath));
    }
    currentNode = currentNode.folders.get(part);
  });
  currentNode.files.push(Object.assign({}, file, { path: safePath }));
}

// Builds a nested folder tree from Git's flat status file list.
function buildTree(files) {
  const rootNode = createFolderNode("", "");
  files.forEach((file) => insertFile(rootNode, file));
  return rootNode;
}

// Sorts tree peers by display name so folders remain easy to scan.
function sortByName(left, right) {
  return left.name.localeCompare(right.name);
}

// Returns all folder paths currently represented by changed files.
function folderPaths(files) {
  const paths = new Set();
  files.forEach((file) => {
    const parts = normalizedPath(file.path).split("/").filter(Boolean);
    parts.slice(0, -1).forEach((part, index) => {
      paths.add(parts.slice(0, index + 1).join("/"));
    });
  });
  return paths;
}

// Produces a CSS variable that indents a row according to its tree depth.
function indentStyle(level) {
  return `style="--tree-indent: ${level * 18}px;"`;
}

// Renders the extra ignore checkbox when Overview has ignore mode enabled.
function renderIgnoreCheckbox(path, label, ignoreMode) {
  if (!ignoreMode || !canIgnorePath(path)) return "";

  return `
    <input
      type="checkbox"
      class="ignore-checkbox"
      value="${escapeHtml(path)}"
      aria-label="Ignore ${escapeHtml(label)}"
    >
  `;
}

// Protects exactly the three repository-relative targets reserved by the ignore policy.
function canIgnorePath(path) {
  const safePath = normalizedPath(path).replace(/\/+$/g, "");
  return safePath.length > 0 && ![".gitignore", ".git", ".github"].includes(safePath);
}

// Converts backend status labels into safe class names for semantic row color.
function statusClass(file) {
  if (file.conflict) return "conflict";

  const label = String(file.label || "changed").toLowerCase();
  const slug = label.replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return slug || "changed";
}

// Renders a folder row and its children unless that folder is collapsed.
function renderFolder(node, options, level) {
  const collapsed = options.collapsedFolders.has(node.path);
  const rowMode = options.ignoreMode ? " ignore-mode" : "";
  const ariaExpanded = collapsed ? "false" : "true";
  const caret = collapsed ? ">" : "v";
  const ignoreInput = renderIgnoreCheckbox(`${node.path}/`, `${node.path}/`, options.ignoreMode);
  const children = collapsed ? "" : renderChildren(node, options, level + 1);

  return `
    <div class="file-tree-folder-row${rowMode}" ${indentStyle(level)}>
      ${ignoreInput}
      <button
        class="folder-toggle"
        type="button"
        data-path="${escapeHtml(node.path)}"
        aria-expanded="${ariaExpanded}"
      >
        <span class="folder-caret" aria-hidden="true">${caret}</span>
        <span class="folder-name">${escapeHtml(node.name)}</span>
      </button>
    </div>
    ${children}
  `;
}

// Renders one changed file row with the existing commit and diff controls.
function renderFile(file, options, level) {
  const checked = options.selectedFiles.has(file.path) ? "checked" : "";
  const active = file.path === options.selectedDiffPath ? " active" : "";
  const pillClass = file.conflict ? "danger" : file.untracked ? "warning" : "";
  const rowStatus = statusClass(file);
  const canIgnore = canIgnorePath(file.path);
  const rowMode = options.ignoreMode ? ` ignore-mode${canIgnore ? " has-ignore" : ""}` : "";
  const ignoreInput = renderIgnoreCheckbox(file.path, file.path, options.ignoreMode);
  const commitInput = options.ignoreMode ? "" : `
      <input class="file-checkbox" type="checkbox" value="${escapeHtml(file.path)}" ${checked}>`;
  const original = file.original_path
    ? `<div class="row-meta">from ${escapeHtml(file.original_path)}</div>`
    : "";

  return `
    <div class="file-row status-${rowStatus}${active}${rowMode}" ${indentStyle(level)}>
      ${ignoreInput}
      ${commitInput}
      <button class="file-diff-button" type="button" data-path="${escapeHtml(file.path)}">
        <span class="file-path">${escapeHtml(file.path)}</span>
        ${original}
      </button>
      <span class="status-pill ${pillClass} file-status-${rowStatus}">${escapeHtml(file.label)}</span>
    </div>
  `;
}

// Renders folders before files at each level, matching normal file-tree behavior.
function renderChildren(node, options, level) {
  const folders = Array.from(node.folders.values()).sort(sortByName);
  const files = node.files.slice().sort((left, right) => left.path.localeCompare(right.path));
  return folders.map((folder) => renderFolder(folder, options, level))
    .concat(files.map((file) => renderFile(file, options, level)))
    .join("");
}

// Public renderer consumed by Overview whenever status or tree UI state changes.
function renderChangedFileTree(options) {
  const tree = buildTree(options.files || []);
  return renderChildren(tree, options, 0);
}

window.GitDeskChangedFileTree = {
  folderPaths,
  renderChangedFileTree,
  withoutIgnoredPath,
};
})();
