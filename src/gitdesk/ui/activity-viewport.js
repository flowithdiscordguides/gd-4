/*
  Pointer, wheel, and keyboard viewport controls for the Project Activity Atlas.
*/

// Publishes reusable atlas movement separately from factual activity rendering.
(() => {
// Zoom bounds keep commit artifacts legible while allowing a broad activity overview.
const MIN_VIEW_SCALE = 0.35;
const MAX_VIEW_SCALE = 2.5;
const ZOOM_IN_FACTOR = 0.88;
const ZOOM_OUT_FACTOR = 1.12;

// Returns the nearest delegated target without assuming every event target implements Element APIs.
function closestTarget(event, selector) {
  return event.target && typeof event.target.closest === "function" ? event.target.closest(selector) : null;
}

// Creates one controller for a rendered SVG container and its factual artifact-selection callback.
function createActivityViewport(container, onSelect) {
  const state = {
    view: null,
    drag: null,
    suppressClickUntil: 0,
  };

  // Applies the current view box after pointer, wheel, keyboard, or reset interaction changes it.
  function apply() {
    const svg = container.querySelector("svg");
    if (!svg || !state.view) return;
    const view = state.view;
    svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.width} ${view.height}`);
  }

  // Removes viewport dimensions when the selected range has no factual commit nodes.
  function clear() {
    state.view = null;
    state.drag = null;
  }

  // Sets complete atlas bounds while retaining a readable initial viewport for tall content.
  function setContentSize(width, height, initialHeight = height) {
    state.view = {
      x: 0,
      y: 0,
      width,
      height: initialHeight,
      initialWidth: width,
      initialHeight,
      contentWidth: width,
      contentHeight: height,
    };
    apply();
  }

  // Restores the atlas's readable starting viewport after the user pans or zooms it.
  function reset() {
    if (!state.view) return;
    state.view.x = 0;
    state.view.y = 0;
    state.view.width = state.view.initialWidth;
    state.view.height = state.view.initialHeight;
    apply();
  }

  // Zooms around a viewport-relative focal point so the inspected commit remains under the pointer.
  function zoomAt(factor, focalX = 0.5, focalY = 0.5) {
    if (!state.view) return;
    const view = state.view;
    const minWidth = view.contentWidth * MIN_VIEW_SCALE;
    const maxWidth = view.contentWidth * MAX_VIEW_SCALE;
    const nextWidth = Math.min(maxWidth, Math.max(minWidth, view.width * factor));
    const appliedFactor = nextWidth / view.width;
    const nextHeight = view.height * appliedFactor;
    view.x += (view.width - nextWidth) * focalX;
    view.y += (view.height - nextHeight) * focalY;
    view.width = nextWidth;
    view.height = nextHeight;
    constrainVerticalView();
    apply();
  }

  // Uses the same bounded center-point zoom for toolbar and keyboard controls.
  function zoomIn() {
    zoomAt(ZOOM_IN_FACTOR);
  }

  function zoomOut() {
    zoomAt(ZOOM_OUT_FACTOR);
  }

  // Keeps vertical navigation on factual atlas content, centering it when the complete height already fits.
  function constrainVerticalView() {
    if (!state.view) return;
    const view = state.view;
    if (view.height >= view.contentHeight) {
      view.y = (view.contentHeight - view.height) / 2;
      return;
    }
    view.y = Math.min(view.contentHeight - view.height, Math.max(0, view.y));
  }

  // Converts browser line and page wheel units before vertically panning the atlas viewport itself.
  function scrollAtlas(event, svg) {
    if (!state.view || !event.deltaY) return;
    const bounds = svg.getBoundingClientRect();
    const unit = event.deltaMode === WheelEvent.DOM_DELTA_LINE
      ? 16
      : event.deltaMode === WheelEvent.DOM_DELTA_PAGE ? bounds.height : 1;
    event.preventDefault();
    state.view.y += event.deltaY * unit * (state.view.height / bounds.height);
    constrainVerticalView();
    apply();
  }

  // Starts direct-manipulation panning from the atlas background or a commit artifact.
  function handlePointerDown(event) {
    const svg = closestTarget(event, "svg");
    if (!svg || event.button !== 0 || !state.view) return;
    state.drag = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      viewX: state.view.x,
      viewY: state.view.y,
      selectionTarget: closestTarget(event, "[data-activity-key]"),
      moved: false,
    };
    svg.setPointerCapture(event.pointerId);
  }

  // Moves the view box in SVG coordinates after pointer motion establishes a drag gesture.
  function handlePointerMove(event) {
    const svg = closestTarget(event, "svg");
    if (!svg || !state.drag || state.drag.pointerId !== event.pointerId || !state.view) return;
    const deltaX = event.clientX - state.drag.clientX;
    const deltaY = event.clientY - state.drag.clientY;
    if (Math.abs(deltaX) > 3 || Math.abs(deltaY) > 3) state.drag.moved = true;
    if (!state.drag.moved) return;
    const bounds = svg.getBoundingClientRect();
    state.view.x = state.drag.viewX - deltaX * (state.view.width / bounds.width);
    state.view.y = state.drag.viewY - deltaY * (state.view.height / bounds.height);
    constrainVerticalView();
    svg.classList.add("panning");
    apply();
  }

  // Ends capture, selects a click target explicitly, and suppresses the synthetic post-pointer click.
  function handlePointerEnd(event) {
    const svg = closestTarget(event, "svg");
    if (!svg || !state.drag || state.drag.pointerId !== event.pointerId) return;
    const selectionTarget = state.drag.selectionTarget;
    const shouldSelect = !state.drag.moved && event.type !== "pointercancel" && selectionTarget;
    state.suppressClickUntil = Date.now() + 250;
    state.drag = null;
    svg.classList.remove("panning");
    if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
    if (shouldSelect) onSelect(selectionTarget);
  }

  // Requires an explicit modifier before wheel movement can zoom the atlas under the pointer.
  function handleWheel(event) {
    if (closestTarget(event, "[data-activity-popover]")) return;
    const svg = container.querySelector("svg");
    if (!svg || !state.view) return;
    if (!event.ctrlKey && !event.metaKey) {
      scrollAtlas(event, svg);
      return;
    }
    event.preventDefault();
    const bounds = svg.getBoundingClientRect();
    const focalX = (event.clientX - bounds.left) / bounds.width;
    const focalY = (event.clientY - bounds.top) / bounds.height;
    zoomAt(event.deltaY > 0 ? ZOOM_OUT_FACTOR : ZOOM_IN_FACTOR, focalX, focalY);
  }

  // Selects factual artifacts for keyboard-generated clicks that do not pass through pointer capture.
  function handleClick(event) {
    if (Date.now() < state.suppressClickUntil) return;
    onSelect(closestTarget(event, "[data-activity-key]"));
  }

  // Adds keyboard selection, panning, zooming, and reset behavior to the interactive atlas.
  function handleKeydown(event) {
    const node = closestTarget(event, "[data-activity-key]");
    if ((event.key === "Enter" || event.key === " ") && node) {
      event.preventDefault();
      onSelect(node);
      return;
    }
    if (!state.view) return;
    const steps = { ArrowLeft: [-35, 0], ArrowRight: [35, 0], ArrowUp: [0, -35], ArrowDown: [0, 35] };
    if (steps[event.key]) {
      event.preventDefault();
      state.view.x += steps[event.key][0];
      state.view.y += steps[event.key][1];
      constrainVerticalView();
      apply();
    } else if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoomIn();
    } else if (event.key === "-" || event.key === "_") {
      event.preventDefault();
      zoomOut();
    } else if (event.key === "0") {
      event.preventDefault();
      reset();
    }
  }

  container.addEventListener("click", handleClick);
  container.addEventListener("pointerdown", handlePointerDown);
  container.addEventListener("pointermove", handlePointerMove);
  container.addEventListener("pointerup", handlePointerEnd);
  container.addEventListener("pointercancel", handlePointerEnd);
  container.addEventListener("wheel", handleWheel, { passive: false });
  container.addEventListener("keydown", handleKeydown);
  return { clear, reset, setContentSize, zoomIn, zoomOut };
}

window.GitDeskActivityViewport = { createActivityViewport };
})();
