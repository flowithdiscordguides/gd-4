/*
  Continuous hue, saturation, and brightness picker for the Settings Theme tab.
*/

// Owns the custom color-wheel popover while the Theme controller owns persisted semantic colors.
(() => {
let activeTrigger = null;
let changeCallback = null;
let bound = false;
let pointerId = null;
let state = { hue: 0, saturation: 0, value: 100 };

// Keeps one numeric color channel inside its legal range.
function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

// Converts a safe six-digit hexadecimal color to red, green, and blue channels.
function hexToRgb(color) {
  return [1, 3, 5].map((start) => Number.parseInt(color.slice(start, start + 2), 16));
}

// Converts a validated hexadecimal color into hue, saturation, and value percentages.
function hexToHsv(color) {
  const [red, green, blue] = hexToRgb(color).map((channel) => channel / 255);
  const maximum = Math.max(red, green, blue);
  const minimum = Math.min(red, green, blue);
  const difference = maximum - minimum;
  let hue = 0;
  if (difference && maximum === red) hue = 60 * (((green - blue) / difference) % 6);
  if (difference && maximum === green) hue = 60 * (((blue - red) / difference) + 2);
  if (difference && maximum === blue) hue = 60 * (((red - green) / difference) + 4);
  return {
    hue: Math.round((hue + 360) % 360) % 360,
    saturation: maximum ? Math.round((difference / maximum) * 100) : 0,
    value: Math.round(maximum * 100),
  };
}

// Converts one hue, saturation, and value selection into a six-digit hexadecimal color.
function hsvToHex(colorState) {
  const hueSector = colorState.hue / 60;
  const chroma = (colorState.value / 100) * (colorState.saturation / 100);
  const secondary = chroma * (1 - Math.abs((hueSector % 2) - 1));
  const minimum = (colorState.value / 100) - chroma;
  const sectors = [
    [chroma, secondary, 0],
    [secondary, chroma, 0],
    [0, chroma, secondary],
    [0, secondary, chroma],
    [secondary, 0, chroma],
    [chroma, 0, secondary],
  ];
  const channels = sectors[Math.floor(hueSector) % 6].map((channel) => {
    return Math.round((channel + minimum) * 255).toString(16).padStart(2, "0");
  });
  return `#${channels.join("")}`;
}

// Returns the reusable picker markup without relying on a browser-native preset palette.
function markup() {
  return `
    <div id="theme-color-wheel-popover" class="theme-color-wheel-popover" role="dialog"
      aria-labelledby="theme-color-wheel-title" hidden>
      <header class="theme-color-wheel-header">
        <div><span>Color wheel</span><strong id="theme-color-wheel-title"></strong></div>
        <button id="close-theme-color-wheel" type="button" aria-label="Close color wheel">×</button>
      </header>
      <div id="theme-hs-wheel" class="theme-hs-wheel" tabindex="0" role="slider"
        aria-label="Hue and saturation color wheel" aria-valuemin="0" aria-valuemax="359">
        <span id="theme-wheel-thumb" class="theme-wheel-thumb" aria-hidden="true"></span>
      </div>
      <label class="theme-brightness-label" for="theme-color-brightness">
        <span>Brightness</span><output id="theme-brightness-value"></output>
      </label>
      <input id="theme-color-brightness" class="theme-brightness-slider" type="range"
        min="0" max="100" step="1">
      <footer class="theme-color-wheel-footer">
        <span id="theme-wheel-preview" class="theme-wheel-preview" aria-hidden="true"></span>
        <output id="theme-wheel-hex"></output>
        <button id="done-theme-color-wheel" class="primary" type="button">Done</button>
      </footer>
    </div>
  `;
}

// Returns one required picker element after the Theme controller has injected the markup.
function element(id) {
  return document.getElementById(id);
}

// Places the picker beside its swatch while keeping the complete wheel inside the viewport.
function placePopover() {
  const popover = element("theme-color-wheel-popover");
  const triggerBox = activeTrigger.getBoundingClientRect();
  const gap = 10;
  const edge = 12;
  let left = triggerBox.right + gap;
  if (left + popover.offsetWidth > window.innerWidth - edge) {
    left = triggerBox.left - popover.offsetWidth - gap;
  }
  left = clamp(left, edge, window.innerWidth - popover.offsetWidth - edge);
  const top = clamp(triggerBox.top - 16, edge, window.innerHeight - popover.offsetHeight - edge);
  popover.style.left = `${Math.round(left)}px`;
  popover.style.top = `${Math.round(top)}px`;
}

// Renders the selector position and continuous brightness gradient from the current HSV state.
function render(emitChange = false) {
  const wheel = element("theme-hs-wheel");
  const angle = ((state.hue - 90) * Math.PI) / 180;
  const radius = state.saturation / 2;
  const color = hsvToHex(state);
  const brightest = hsvToHex({ hue: state.hue, saturation: state.saturation, value: 100 });
  element("theme-wheel-thumb").style.left = `${50 + (Math.cos(angle) * radius)}%`;
  element("theme-wheel-thumb").style.top = `${50 + (Math.sin(angle) * radius)}%`;
  element("theme-color-brightness").value = String(state.value);
  element("theme-brightness-value").textContent = `${state.value}%`;
  element("theme-wheel-preview").style.background = color;
  element("theme-wheel-hex").textContent = color.toUpperCase();
  element("theme-color-brightness").style.setProperty("--theme-brightest-color", brightest);
  wheel.setAttribute("aria-valuetext", `Hue ${state.hue}°, saturation ${state.saturation}%`);
  wheel.setAttribute("aria-valuenow", String(state.hue));
  if (emitChange && changeCallback) changeCallback(color);
}

// Updates hue and saturation from one pointer position on the continuous wheel.
function selectWheelPosition(clientX, clientY) {
  const box = element("theme-hs-wheel").getBoundingClientRect();
  const horizontal = clientX - (box.left + (box.width / 2));
  const vertical = clientY - (box.top + (box.height / 2));
  const radius = Math.min(box.width, box.height) / 2;
  state.hue = Math.round((Math.atan2(vertical, horizontal) * 180 / Math.PI + 450) % 360);
  state.saturation = Math.round(clamp(Math.hypot(horizontal, vertical) / radius, 0, 1) * 100);
  render(true);
}

// Closes the picker and optionally restores focus to the swatch that opened it.
function close(returnFocus = false) {
  const popover = element("theme-color-wheel-popover");
  if (!popover || popover.hidden) return;
  popover.hidden = true;
  if (activeTrigger) activeTrigger.setAttribute("aria-expanded", "false");
  if (returnFocus && activeTrigger) activeTrigger.focus();
  activeTrigger = null;
  changeCallback = null;
  pointerId = null;
}

// Opens the continuous picker from one semantic color swatch.
function open(trigger, color, label, onChange) {
  if (!bound) return;
  close(false);
  activeTrigger = trigger;
  changeCallback = onChange;
  state = hexToHsv(color);
  element("theme-color-wheel-title").textContent = label;
  element("theme-color-wheel-popover").hidden = false;
  activeTrigger.setAttribute("aria-expanded", "true");
  render(false);
  placePopover();
  element("theme-hs-wheel").focus();
}

// Gives keyboard users the same continuous hue and saturation adjustments as pointer users.
function handleWheelKeydown(event) {
  const amount = event.shiftKey ? 10 : 2;
  if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
  event.preventDefault();
  if (event.key === "ArrowLeft") state.hue = (state.hue - amount + 360) % 360;
  if (event.key === "ArrowRight") state.hue = (state.hue + amount) % 360;
  if (event.key === "ArrowUp") state.saturation = clamp(state.saturation + amount, 0, 100);
  if (event.key === "ArrowDown") state.saturation = clamp(state.saturation - amount, 0, 100);
  render(true);
}

// Binds the singleton picker after its markup is available in the Theme card.
function bind() {
  if (bound) return;
  const wheel = element("theme-hs-wheel");
  if (!wheel) return;
  bound = true;
  wheel.addEventListener("pointerdown", (event) => {
    pointerId = event.pointerId;
    wheel.setPointerCapture(pointerId);
    selectWheelPosition(event.clientX, event.clientY);
  });
  wheel.addEventListener("pointermove", (event) => {
    if (event.pointerId === pointerId) selectWheelPosition(event.clientX, event.clientY);
  });
  wheel.addEventListener("pointerup", (event) => {
    if (event.pointerId === pointerId) pointerId = null;
  });
  wheel.addEventListener("pointercancel", () => {
    pointerId = null;
  });
  wheel.addEventListener("keydown", handleWheelKeydown);
  element("theme-color-brightness").addEventListener("input", (event) => {
    state.value = Number(event.target.value);
    render(true);
  });
  element("close-theme-color-wheel").addEventListener("click", () => close(true));
  element("done-theme-color-wheel").addEventListener("click", () => close(true));
  document.addEventListener("pointerdown", (event) => {
    const popover = element("theme-color-wheel-popover");
    if (!popover.hidden && !popover.contains(event.target) && !activeTrigger.contains(event.target)) close(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close(true);
  });
  window.addEventListener("resize", () => close(false));
}

window.GitDeskColorWheel = { bind, close, markup, open };
})();
