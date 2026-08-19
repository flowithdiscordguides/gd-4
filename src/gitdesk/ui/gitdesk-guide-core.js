/*
 * Shared state, trusted icon helpers, topic primitives, and screenshot viewer operations for the GitDesk Guide.
 * Event orchestration and final topic rendering live in gitdesk-guide-interactions.js.
 */
const TOPICS = window.GitDeskGuideTopics;
const TOPIC_CONTRACTS = window.GitDeskGuideContracts || {};
const ui = {
  brandIcon: document.getElementById("guide-brand-icon"),
  rail: document.querySelector(".rail"),
  tabs: document.getElementById("guide-tabs"),
  navToggle: document.getElementById("guide-nav-toggle"),
  themeToggle: document.getElementById("guide-theme-toggle"),
  progress: document.getElementById("guide-progress"),
  progressText: document.getElementById("guide-progress-text"),
  main: document.getElementById("guide-main"),
  kicker: document.getElementById("kicker"),
  title: document.getElementById("title"),
  lead: document.getElementById("lead"),
  content: document.getElementById("content"),
  status: document.getElementById("guide-status"),
  viewer: document.getElementById("image-viewer"),
  viewerClose: document.getElementById("image-viewer-close"),
  viewerStage: document.getElementById("image-viewer-stage"),
  viewerImage: document.getElementById("image-viewer-image"),
  viewerZoom: document.getElementById("image-viewer-zoom")
};

const imageViewerState = {
  open: false,
  scale: 1,
  x: 0,
  y: 0,
  dragging: false,
  dragX: 0,
  dragY: 0,
  originX: 0,
  originY: 0,
  trigger: null
};

// Escapes user-facing labels before inserting them into guide HTML templates.
function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[character]));
}

// Builds one decorative image element from a trusted packaged UI asset name.
function appAsset(name, className = "") {
  return `<img class="${className}" src="${ASSET_BASE}${name}" alt="" draggable="false">`;
}

// Returns the app-owned icon markup that the guide mirrors for one control.
function sourceMarkup(name) {
  if (name === "app") {
    return appAsset("app-icon.svg");
  }
  if (name === "theme") {
    return appAsset("darktheme-icon.svg");
  }
  if (name === "newProject") {
    return appAsset("newproject-icon.svg");
  }
  if (name === "newTag") {
    return appAsset("newtag-icon.svg");
  }
  if (name === "guide") {
    return appAsset("guide-icon.svg");
  }
  if (name === "syncChain") {
    return appAsset("sync-chain-icon.svg");
  }
  if (window.GitDeskIcons && window.GitDeskIcons[name]) {
    return window.GitDeskIcons[name];
  }
  const source = document.querySelector(`[data-icon-source="${name}"]`);
  return source ? source.innerHTML : "";
}

// Wraps one mirrored app icon in the guide's accessible presentation container.
function icon(name, className = "") {
  if (name === "none") {
    return "";
  }
  const assetIcons = ["app", "theme", "newProject", "newTag", "guide", "syncChain"];
  const assetClass = assetIcons.indexOf(name) >= 0 ? " asset" : "";
  return `<span class="${className}${assetClass}" aria-hidden="true">${sourceMarkup(name)}</span>`;
}

// Builds topic navigation from the ordered guide topic registry.
function renderTabs() {
  ui.brandIcon.innerHTML = sourceMarkup("app");
  const groups = [];
  TOPICS.forEach((topic) => {
    const contract = TOPIC_CONTRACTS[topic.id] || {};
    const groupName = contract.group || "Guide";
    let group = groups[groups.length - 1];
    if (!group || group.name !== groupName) {
      group = { name: groupName, topics: [] };
      groups.push(group);
    }
    group.topics.push(topic);
  });
  ui.tabs.innerHTML = groups.map((group, groupIndex) => `
    <section class="guide-group" aria-labelledby="guide-group-${groupIndex}">
      <p id="guide-group-${groupIndex}" class="guide-group-label">${escapeHtml(group.name)}</p>
      ${group.topics.map((topic) => `
        <button class="guide-tab" type="button" data-topic="${topic.id}" aria-current="false">
          ${icon(topic.icon, "nav-icon")}
          <span>${escapeHtml(topic.title)}</span>
        </button>
      `).join("")}
    </section>
  `).join("");
}

// Renders a screen-order map when the selected topic provides one.
function renderMap(items) {
  if (!items) return "";
  return `
    <section class="topic-section">
      <h3>Screen order</h3>
      <div class="layout-map">
        ${items.map((item) => `
          <div class="map-step">
            <strong>${escapeHtml(item[0])}</strong>
            <span>${item[1]}</span>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

// Renders the paired mode rules supplied by a topic.
function renderModes(items) {
  if (!items) return "";
  return `
    <section class="topic-section">
      <h3>Mode rule</h3>
      <div class="mode-grid">
        ${items.map((item) => `
          <div class="mode-panel">
            <h4>${escapeHtml(item[0])}</h4>
            <p>${item[1]}</p>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

// Renders a named setup checklist before the general control reference.
function renderSetup(section) {
  if (!section || !section.items) return "";
  return `
    <section class="topic-section">
      <h3>${escapeHtml(section.title)}</h3>
      <div class="setup-list">
        ${section.items.map((item) => `
          <div class="setup-row">
            <strong>${escapeHtml(item[0])}</strong>
            <span>${item[1]}</span>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

// Renders the matching Start Here screenshot without embedding image bytes in JavaScript.
function renderQuickPreview(index) {
  const media = START_HERE_MEDIA[index];
  if (!media) {
    return "";
  }
  return `
    <figure class="quick-media">
      <button class="quick-media-frame" type="button" aria-label="Enlarge ${escapeHtml(media.alt)}">
        <img src="${media.src}" alt="${escapeHtml(media.alt)}" draggable="false">
      </button>
      <figcaption>Select the image to open keyboard and pointer zoom controls.</figcaption>
    </figure>
  `;
}

// Pairs each Start Here instruction with its matching screenshot.
function renderQuickStart(topic) {
  return `
    <section class="quick-start-guide">
      ${topic.map.map((item, index) => `
        <article class="quick-start-row">
          <div class="quick-start-copy">
            <h3>${escapeHtml(item[0])}</h3>
            <p>${item[1]}</p>
          </div>
          ${renderQuickPreview(index)}
        </article>
      `).join("")}
    </section>
  `;
}

// Returns the required teaching contract for one topic, with safe empty values for incomplete source data.
function topicContract(topic) {
  return TOPIC_CONTRACTS[topic.id] || {
    time: "Self-paced",
    sectionTitle: "What matters here",
    goals: [],
    guideposts: [],
    prerequisite: "No additional prerequisite recorded.",
    practice: "Review the documented workflow.",
    proof: "Confirm the visible result described by the workflow.",
    recovery: "Use Activity and DevTools when the visible result does not match."
  };
}

// Orients the reader with time, prerequisites, and observable learning objectives.
function renderLessonOrientation(contract) {
  return `
    <section class="lesson-orientation" aria-label="Chapter orientation">
      <div class="lesson-objectives">
        <h3>What you will be able to do</h3>
        <ul>${contract.goals.map((goal) => `<li>${escapeHtml(goal)}</li>`).join("")}</ul>
      </div>
      <div class="lesson-meta">
        <span class="lesson-meta-label">Plan your pass</span>
        <p><strong>${escapeHtml(contract.time)}</strong></p>
        <p>${escapeHtml(contract.prerequisite)}</p>
      </div>
    </section>
  `;
}

// Gives every chapter a content-specific teaching section instead of a repeated generic label.
function renderGuideposts(contract) {
  return `
    <section class="topic-section">
      <h3>${escapeHtml(contract.sectionTitle)}</h3>
      <div class="guidepost-grid">
        ${contract.guideposts.map((item) => `
          <div class="guidepost">
            <h4>${escapeHtml(item[0])}</h4>
            <p>${escapeHtml(item[1])}</p>
          </div>
        `).join("")}
      </div>
    </section>
  `;
}

// Closes the lesson with practice, visible proof, recovery, completion, and adjacent destinations.
function renderLessonCheckpoint(topic, contract, completed) {
  const topicIndex = TOPICS.findIndex((item) => item.id === topic.id);
  const previousTopic = TOPICS[topicIndex - 1];
  const nextTopic = TOPICS[topicIndex + 1];
  return `
    <section class="topic-section">
      <h3>Practice and verify</h3>
      <div class="lesson-checkpoint">
        <div class="checkpoint-item">
          <h4>Try it</h4>
          <p>${escapeHtml(contract.practice)}</p>
        </div>
        <div class="checkpoint-item proof">
          <h4>You are finished when</h4>
          <p>${escapeHtml(contract.proof)}</p>
        </div>
        <div class="checkpoint-item">
          <h4>If the result differs</h4>
          <p>${escapeHtml(contract.recovery)}</p>
        </div>
      </div>
      <div class="lesson-footer">
        <button
          class="lesson-complete${completed ? " completed" : ""}"
          type="button"
          data-complete-topic="${topic.id}"
          aria-pressed="${completed}"
        >
          ${completed ? "Completed — mark incomplete" : "Mark chapter complete"}
        </button>
        <nav class="adjacent-nav" aria-label="Adjacent guide chapters">
          ${previousTopic ? `
            <button type="button" data-adjacent-topic="${previousTopic.id}">
              ← ${escapeHtml(previousTopic.title)}
            </button>
          ` : ""}
          ${nextTopic ? `
            <button type="button" data-adjacent-topic="${nextTopic.id}">
              ${escapeHtml(nextTopic.title)} →
            </button>
          ` : ""}
        </nav>
      </div>
    </section>
  `;
}

// Prevents a zoomed screenshot from being dragged completely beyond the visible inspector stage.
function clampViewerPosition() {
  const scaledWidth = ui.viewerImage.offsetWidth * imageViewerState.scale;
  const scaledHeight = ui.viewerImage.offsetHeight * imageViewerState.scale;
  const maxX = Math.max(0, (scaledWidth - ui.viewerStage.clientWidth) / 2);
  const maxY = Math.max(0, (scaledHeight - ui.viewerStage.clientHeight) / 2);
  imageViewerState.x = Math.min(maxX, Math.max(-maxX, imageViewerState.x));
  imageViewerState.y = Math.min(maxY, Math.max(-maxY, imageViewerState.y));
}

// Applies the current pan and zoom state to the enlarged screenshot.
function updateViewerTransform() {
  clampViewerPosition();
  const translation = [
    `translate(calc(-50% + ${imageViewerState.x}px),`,
    `calc(-50% + ${imageViewerState.y}px))`
  ].join(" ");
  ui.viewerImage.style.transform = `${translation} scale(${imageViewerState.scale})`;
  ui.viewerZoom.textContent = `${Math.round(imageViewerState.scale * 100)}%`;
}

// Constrains screenshot zoom to the usable viewer range.
function clampViewerScale(value) {
  return Math.min(6, Math.max(0.5, value));
}

// Opens one screenshot in the keyboard- and pointer-accessible image viewer.
function openImageViewer(image) {
  imageViewerState.open = true;
  imageViewerState.scale = 1;
  imageViewerState.x = 0;
  imageViewerState.y = 0;
  imageViewerState.dragging = false;
  imageViewerState.trigger = image.closest("button");
  ui.viewerImage.src = image.currentSrc || image.src;
  ui.viewerImage.alt = image.alt || "";
  ui.viewer.classList.add("open");
  ui.viewer.setAttribute("aria-hidden", "false");
  updateViewerTransform();
  ui.viewerClose.focus({ preventScroll: true });
}

// Closes the image viewer and removes its active image reference.
function closeImageViewer() {
  const trigger = imageViewerState.trigger;
  imageViewerState.open = false;
  imageViewerState.dragging = false;
  imageViewerState.trigger = null;
  ui.viewer.classList.remove("open", "dragging");
  ui.viewer.setAttribute("aria-hidden", "true");
  ui.viewerImage.removeAttribute("src");
  if (trigger) {
    trigger.focus({ preventScroll: true });
  }
}

// Changes screenshot scale while preserving the configured zoom limits.
function zoomImageViewer(delta) {
  const previousScale = imageViewerState.scale;
  const nextScale = clampViewerScale(previousScale * delta);
  if (nextScale === previousScale) {
    return;
  }
  imageViewerState.scale = nextScale;
  updateViewerTransform();
}

// Restores the screenshot to its initial centered scale and position.
function resetImageViewer() {
  imageViewerState.scale = 1;
  imageViewerState.x = 0;
  imageViewerState.y = 0;
  updateViewerTransform();
}

// Moves the enlarged screenshot by the supplied horizontal and vertical deltas.
function panImageViewer(deltaX, deltaY) {
  imageViewerState.x += deltaX;
  imageViewerState.y += deltaY;
  updateViewerTransform();
}
