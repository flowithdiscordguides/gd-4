/*
 * User interaction handlers and final topic rendering for the GitDesk Guide.
 * It runs after media, topic, toolbar-icon, and core guide modules are available.
 */
// Opens a Start Here screenshot from its semantic preview button.
function handleGuidePreviewClick(event) {
  const image = event.target.closest(".quick-media-frame img");
  if (image) {
    openImageViewer(image);
  }
}

// Uses modified mouse-wheel input for deliberate screenshot zooming.
function handleViewerWheel(event) {
  if (!imageViewerState.open || !(event.metaKey || event.altKey)) {
    return;
  }
  event.preventDefault();
  zoomImageViewer(event.deltaY < 0 ? 1.12 : 0.89);
}

// Begins pointer-driven screenshot panning from the current offset.
function handleViewerPointerDown(event) {
  if (!imageViewerState.open || event.button !== 0) {
    return;
  }
  imageViewerState.dragging = true;
  imageViewerState.dragX = event.clientX;
  imageViewerState.dragY = event.clientY;
  imageViewerState.originX = imageViewerState.x;
  imageViewerState.originY = imageViewerState.y;
  ui.viewer.classList.add("dragging");
  ui.viewerStage.setPointerCapture(event.pointerId);
}

// Updates screenshot position while an active pointer drag is in progress.
function handleViewerPointerMove(event) {
  if (!imageViewerState.dragging) {
    return;
  }
  imageViewerState.x = imageViewerState.originX + event.clientX - imageViewerState.dragX;
  imageViewerState.y = imageViewerState.originY + event.clientY - imageViewerState.dragY;
  updateViewerTransform();
}

// Ends pointer panning and releases the captured pointer when necessary.
function stopViewerDrag(event) {
  if (!imageViewerState.dragging) {
    return;
  }
  imageViewerState.dragging = false;
  ui.viewer.classList.remove("dragging");
  if (event && typeof event.pointerId === "number" && ui.viewerStage.hasPointerCapture(event.pointerId)) {
    ui.viewerStage.releasePointerCapture(event.pointerId);
  }
}

// Supports Escape, arrow keys, and WASD navigation inside the screenshot viewer.
function handleViewerKeydown(event) {
  if (!imageViewerState.open) {
    return;
  }
  const panStep = event.shiftKey ? 90 : 36;
  const key = event.key.toLowerCase();
  if (key === "tab") {
    const controls = Array.from(ui.viewer.querySelectorAll("button"));
    const currentIndex = controls.indexOf(document.activeElement);
    const boundaryReached = event.shiftKey ? currentIndex <= 0 : currentIndex === controls.length - 1;
    if (boundaryReached) {
      event.preventDefault();
      controls[event.shiftKey ? controls.length - 1 : 0].focus();
    }
    return;
  }
  if (key === "escape") {
    event.preventDefault();
    closeImageViewer();
    return;
  }
  if (key === "arrowleft" || key === "a") {
    event.preventDefault();
    panImageViewer(-panStep, 0);
  } else if (key === "arrowright" || key === "d") {
    event.preventDefault();
    panImageViewer(panStep, 0);
  } else if (key === "arrowup" || key === "w") {
    event.preventDefault();
    panImageViewer(0, -panStep);
  } else if (key === "arrowdown" || key === "s") {
    event.preventDefault();
    panImageViewer(0, panStep);
  }
}

// Maps visible screenshot controls to the same bounded zoom state used by wheel and keyboard input.
function handleViewerToolbarClick(event) {
  const button = event.target.closest("[data-viewer-action]");
  if (!button) {
    return;
  }
  const action = button.dataset.viewerAction;
  if (action === "zoom-in") {
    zoomImageViewer(1.25);
  } else if (action === "zoom-out") {
    zoomImageViewer(0.8);
  } else if (action === "reset") {
    resetImageViewer();
  }
}

// Closes the viewer only when the backdrop itself is selected.
function handleViewerClick(event) {
  if (event.target === ui.viewer) {
    closeImageViewer();
  }
}

// Handles the explicit close button without allowing its default action.
function handleViewerCloseClick(event) {
  event.preventDefault();
  closeImageViewer();
}

// Connects guide and viewer controls to their pointer, wheel, and keyboard handlers.
function bindImageViewer() {
  ui.content.addEventListener("click", handleGuidePreviewClick);
  ui.viewer.addEventListener("wheel", handleViewerWheel, { passive: false });
  ui.viewer.addEventListener("keydown", handleViewerKeydown);
  ui.viewer.addEventListener("click", handleViewerClick);
  ui.viewer.addEventListener("click", handleViewerToolbarClick);
  ui.viewerClose.addEventListener("click", handleViewerCloseClick);
  ui.viewerStage.addEventListener("pointerdown", handleViewerPointerDown);
  ui.viewerStage.addEventListener("pointermove", handleViewerPointerMove);
  ui.viewerStage.addEventListener("pointerup", stopViewerDrag);
  ui.viewerStage.addEventListener("pointercancel", stopViewerDrag);
  ui.viewerImage.addEventListener("load", updateViewerTransform);
}

const GUIDE_STATE_KEY = "gitdesk-guide-learning-v1";

// Loads only valid topic identifiers and known theme values from optional local learning state.
function loadGuideState() {
  const fallbackTheme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
  const fallback = { completed: [], lastTopic: TOPICS[0].id, theme: fallbackTheme };
  try {
    const stored = JSON.parse(window.localStorage.getItem(GUIDE_STATE_KEY) || "null");
    if (!stored || typeof stored !== "object") {
      return fallback;
    }
    const topicIds = new Set(TOPICS.map((topic) => topic.id));
    return {
      completed: Array.isArray(stored.completed)
        ? stored.completed.filter((topicId) => topicIds.has(topicId))
        : [],
      lastTopic: topicIds.has(stored.lastTopic) ? stored.lastTopic : fallback.lastTopic,
      theme: stored.theme === "dark" ? "dark" : "light"
    };
  } catch (error) {
    return fallback;
  }
}

let guideState = loadGuideState();

// Persists useful learning state locally without making the Guide depend on storage availability.
function saveGuideState() {
  try {
    window.localStorage.setItem(GUIDE_STATE_KEY, JSON.stringify(guideState));
  } catch (error) {
    ui.status.textContent = "Progress is available for this session but could not be saved locally.";
  }
}

// Synchronizes the progress meter, completed chapter marks, and theme control with canonical state.
function refreshGuideStatePresentation() {
  const completedIds = new Set(guideState.completed);
  ui.progress.max = TOPICS.length;
  ui.progress.value = completedIds.size;
  ui.progress.textContent = `${completedIds.size} of ${TOPICS.length} complete`;
  ui.progressText.textContent = `${completedIds.size} of ${TOPICS.length} complete`;
  document.querySelectorAll(".guide-tab").forEach((button) => {
    const completed = completedIds.has(button.dataset.topic);
    button.classList.toggle("completed", completed);
    button.setAttribute("aria-label", `${button.textContent.trim()}${completed ? ", completed" : ""}`);
  });
  document.documentElement.dataset.guideTheme = guideState.theme;
  ui.themeToggle.textContent = guideState.theme === "dark" ? "Light theme" : "Dark theme";
}

// Marks or unmarks one chapter and immediately rebuilds its completion control.
function toggleTopicCompletion(topicId) {
  const completedIds = new Set(guideState.completed);
  if (completedIds.has(topicId)) {
    completedIds.delete(topicId);
  } else {
    completedIds.add(topicId);
  }
  guideState.completed = TOPICS.map((topic) => topic.id).filter((id) => completedIds.has(id));
  saveGuideState();
  renderTopic(topicId);
  refreshGuideStatePresentation();
  const completionButton = ui.content.querySelector("[data-complete-topic]");
  if (completionButton) {
    completionButton.focus({ preventScroll: true });
  }
  ui.status.textContent = completedIds.has(topicId)
    ? "Chapter marked complete."
    : "Chapter marked incomplete.";
}

// Resolves a direct chapter hash only when it names a registered topic.
function topicIdFromHash() {
  try {
    const topicId = decodeURIComponent(window.location.hash.replace(/^#/, ""));
    return TOPICS.some((topic) => topic.id === topicId) ? topicId : "";
  } catch (error) {
    return "";
  }
}

// Renders one documented control with its mirrored icon, label, and behavior.
function renderControlRow(item) {
  return `
    <div class="control-row">
      ${item[0] === "none"
    ? '<span class="control-icon-spacer" aria-hidden="true"></span>'
    : icon(item[0], "control-icon")}
      <strong>${escapeHtml(item[1])}</strong>
      <span class="control-detail">${item[2]}</span>
    </div>
  `;
}

// Renders normal and grouped control-reference rows for a topic.
function renderControls(items) {
  return `
    <section class="topic-section">
      <h3>Controls</h3>
      <div class="controls">
        ${items.map((item) => item[0] === "group" ? `
          <div class="control-group">
            <h4>${escapeHtml(item[1])}</h4>
            ${item[2].map(renderControlRow).join("")}
          </div>
        ` : renderControlRow(item)).join("")}
      </div>
    </section>
  `;
}

// Renders an ordered workflow using the topic's supplied heading.
function renderSteps(items, title) {
  return `
    <section class="topic-section">
      <h3>${escapeHtml(title || "Workflow")}</h3>
      <ol class="steps">
        ${items.map((item) => `<li>${item}</li>`).join("")}
      </ol>
    </section>
  `;
}

// Replaces the workspace content and navigation state for one selected topic.
function renderTopic(topicId) {
  const topic = TOPICS.find((item) => item.id === topicId) || TOPICS[0];
  const contract = topicContract(topic);
  const completed = guideState.completed.indexOf(topic.id) >= 0;
  ui.kicker.textContent = topic.kicker;
  ui.kicker.hidden = !topic.kicker;
  ui.title.textContent = topic.title;
  ui.lead.textContent = topic.lead;
  ui.lead.hidden = !topic.lead;
  ui.content.innerHTML = topic.quickStart
    ? [
      renderLessonOrientation(contract),
      renderGuideposts(contract),
      renderQuickStart(topic),
      renderLessonCheckpoint(topic, contract, completed)
    ].join("")
    : [
      renderLessonOrientation(contract),
      renderGuideposts(contract),
      renderMap(topic.map),
      renderModes(topic.modes),
      renderSetup(topic.setup),
      renderControls(topic.controls || []),
      renderSteps(topic.steps || [], topic.stepsTitle),
      renderLessonCheckpoint(topic, contract, completed)
    ].join("");
  document.querySelectorAll(".guide-tab").forEach((button) => {
    const active = button.dataset.topic === topic.id;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
}

// Moves to one chapter, records resume state, updates the direct hash, and optionally orients keyboard focus.
function navigateToTopic(topicId, focusHeading = false, updateHash = true) {
  const topic = TOPICS.find((item) => item.id === topicId) || TOPICS[0];
  guideState.lastTopic = topic.id;
  saveGuideState();
  renderTopic(topic.id);
  refreshGuideStatePresentation();
  if (updateHash) {
    window.history.replaceState(null, "", `#${encodeURIComponent(topic.id)}`);
  }
  ui.rail.classList.remove("mobile-open");
  ui.navToggle.setAttribute("aria-expanded", "false");
  ui.status.textContent = `${topic.title} chapter opened.`;
  if (focusHeading) {
    ui.title.focus({ preventScroll: true });
    ui.main.scrollIntoView({ block: "start" });
  }
}

// Routes a navigation-button click to its topic without binding every button separately.
function handleGuideClick(event) {
  const completeButton = event.target.closest("[data-complete-topic]");
  if (completeButton) {
    toggleTopicCompletion(completeButton.dataset.completeTopic);
    return;
  }
  const button = event.target.closest("[data-topic], [data-adjacent-topic]");
  if (button) {
    navigateToTopic(button.dataset.topic || button.dataset.adjacentTopic, true);
  }
}

// Opens or closes the compact mobile chapter list without affecting the desktop rail.
function handleGuideNavToggle() {
  const expanded = !ui.rail.classList.contains("mobile-open");
  ui.rail.classList.toggle("mobile-open", expanded);
  ui.navToggle.setAttribute("aria-expanded", String(expanded));
}

// Switches between independently designed Guide palettes and saves the reader's choice locally.
function handleGuideThemeToggle() {
  guideState.theme = guideState.theme === "dark" ? "light" : "dark";
  saveGuideState();
  refreshGuideStatePresentation();
  ui.status.textContent = `${guideState.theme === "dark" ? "Dark" : "Light"} guide theme applied.`;
}

// Initializes navigation, screenshot interactions, and the first guide topic.
function initGuide() {
  document.documentElement.classList.add("guide-ready");
  renderTabs();
  ui.tabs.addEventListener("click", handleGuideClick);
  ui.content.addEventListener("click", handleGuideClick);
  ui.navToggle.addEventListener("click", handleGuideNavToggle);
  ui.themeToggle.addEventListener("click", handleGuideThemeToggle);
  bindImageViewer();
  const initialTopic = topicIdFromHash() || guideState.lastTopic;
  navigateToTopic(initialTopic, false, Boolean(window.location.hash));
  window.addEventListener("hashchange", () => {
    const topicId = topicIdFromHash();
    if (topicId) {
      navigateToTopic(topicId, true, false);
    }
  });
  window.addEventListener("resize", () => {
    if (imageViewerState.open) {
      updateViewerTransform();
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initGuide);
} else {
  initGuide();
}
