/*
  Marked-to-DOMPurify rendering boundary for project-note preview.
*/

// Keeps the only Markdown HTML sanitizer configuration separate from editor state.
(() => {
const markdownRenderer = window.marked;
const purifier = window.DOMPurify;

if (!markdownRenderer || !purifier) {
  throw new Error("GitDesk Markdown sanitizer dependencies did not load.");
}

// Retains Marked task-list checkboxes while making every allowed checkbox non-interactive.
purifier.addHook("uponSanitizeElement", (node, hookEvent) => {
  if (hookEvent.tagName === "input" && node.getAttribute("type") !== "checkbox") {
    node.remove();
  }
});

purifier.addHook("afterSanitizeAttributes", (node) => {
  if (node.tagName === "INPUT") {
    node.setAttribute("disabled", "");
    node.removeAttribute("autofocus");
    node.removeAttribute("form");
    node.removeAttribute("name");
  }
});

// Parses Markdown, sanitizes the complete result, and returns only safe preview HTML.
function render(source) {
  const parsedHtml = markdownRenderer.parse(String(source || ""), {
    async: false,
    breaks: false,
    gfm: true,
  });
  return purifier.sanitize(parsedHtml, {
    ALLOW_DATA_ATTR: false,
    FORBID_ATTR: ["style"],
    FORBID_TAGS: [
      "script", "style", "iframe", "object", "embed", "form", "button",
      "select", "textarea", "video", "audio", "canvas", "img",
    ],
    USE_PROFILES: { html: true },
  });
}

window.GitDeskMarkdownSanitizer = { render };
})();
