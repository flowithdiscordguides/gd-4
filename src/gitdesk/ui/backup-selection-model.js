/*
  Pure Backup selection rules and detected-change review grouping for the modal controller.
*/

// Keeps selection math independent from DOM rendering and native transfer ownership.
(() => {
// Returns one source's editable rules, creating an excluded scope when none exists.
function sourceRules(rulesBySource, sourceId) {
  if (!rulesBySource[sourceId]) rulesBySource[sourceId] = {};
  return rulesBySource[sourceId];
}

// Returns the nearest include or exclude rule for one source-relative path.
function pathIncluded(rulesBySource, sourceId, path) {
  const rules = sourceRules(rulesBySource, sourceId);
  let included = Boolean(rules[""]);
  if (!path) return included;
  const parts = path.split("/");
  parts.forEach((part, index) => {
    const candidate = parts.slice(0, index + 1).join("/");
    // A deeper explicit decision overrides the inherited source or parent decision.
    if (Object.prototype.hasOwnProperty.call(rules, candidate)) included = rules[candidate];
  });
  return included;
}

// Reports whether a loaded row contains a deeper rule with a different effective state.
function pathMixed(rulesBySource, sourceId, path) {
  const rules = sourceRules(rulesBySource, sourceId);
  const included = pathIncluded(rulesBySource, sourceId, path);
  const prefix = path ? `${path}/` : "";
  return Object.entries(rules).some(([rulePath, value]) => {
    return rulePath !== path && rulePath.startsWith(prefix) && value !== included;
  });
}

// Replaces one subtree decision while retaining only the rule needed against its parent.
function setPathRule(rulesBySource, sourceId, path, included) {
  const rules = sourceRules(rulesBySource, sourceId);
  const prefix = path ? `${path}/` : "";
  Object.keys(rules).forEach((rulePath) => {
    const insideSubtree = prefix && rulePath.startsWith(prefix);
    // A new subtree decision supersedes every prior decision inside that same subtree.
    if (rulePath === path || insideSubtree || (!path && rulePath)) delete rules[rulePath];
  });
  const parent = path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
  const parentIncluded = path ? pathIncluded(rulesBySource, sourceId, parent) : false;
  // Equal child and parent decisions are inherited and do not need a redundant stored rule.
  if (included !== parentIncluded) rules[path] = included;
}

// Returns only source records containing at least one effective include rule.
function serializedSelection(rulesBySource) {
  return Object.entries(rulesBySource)
    .filter(([, rules]) => Object.values(rules).some(Boolean))
    .map(([sourceId, rules]) => ({ source_id: sourceId, rules: { ...rules } }));
}

// Converts one canonical backend selection into an editable rules mapping.
function rulesFromSelection(selection) {
  const rulesBySource = {};
  (Array.isArray(selection) ? selection : []).forEach((item) => {
    const sourceId = String(item && item.source_id || "");
    // Empty identifiers never become editable selection owners.
    if (sourceId) rulesBySource[sourceId] = { ...(item.rules || {}) };
  });
  return rulesBySource;
}

// Returns root rules for every available source across detected and optional groups.
function selectAll(tree) {
  const rulesBySource = {};
  tree.forEach((group) => group.children.forEach((node) => {
    // Unavailable roots remain visible but cannot be promised as copied content.
    if (node.available !== false) rulesBySource[node.source_id] = { "": true };
  }));
  return rulesBySource;
}

// Moves detected roots into one first section while retaining every other group below it.
function groupSyncTree(tree, changedSourceIds, isSync) {
  const normalizedTree = tree.map((group) => ({ ...group, children: [...group.children] }));
  // First-backup review keeps the established complete inventory hierarchy unchanged.
  if (!isSync) return normalizedTree;
  const changedIds = new Set(changedSourceIds.map((sourceId) => String(sourceId || "")));
  const detectedChildren = [];
  const remainingGroups = normalizedTree.map((group) => {
    const remainingChildren = [];
    group.children.forEach((node) => {
      // Each changed root moves rather than duplicates, so one checkbox owns one decision.
      if (changedIds.has(node.source_id)) detectedChildren.push(node);
      else remainingChildren.push(node);
    });
    return { ...group, kind: "optional-sources", children: remainingChildren };
  });
  return [{
    category: "detected changes",
    label: "Detected changes",
    kind: "detected-changes",
    children: detectedChildren,
  }, ...remainingGroups];
}

// Normalizes one bridge payload into the tree and rules consumed by the modal controller.
function reviewData(data) {
  const payload = data && typeof data === "object" ? data : {};
  const tree = Array.isArray(payload.tree) ? payload.tree : [];
  const changedSourceIds = Array.isArray(payload.changed_source_ids) ? payload.changed_source_ids : [];
  return {
    tree: groupSyncTree(tree, changedSourceIds, payload.is_sync === true),
    rules: rulesFromSelection(payload.selection),
  };
}

window.GitDeskBackupSelectionModel = {
  pathIncluded,
  pathMixed,
  reviewData,
  selectAll,
  serializedSelection,
  setPathRule,
};
})();
