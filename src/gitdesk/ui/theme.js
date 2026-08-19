/*
  Theme controller for GitDesk. It applies light or dark mode before the main app controller starts.
*/

// Keeps theme state separate from backend settings because no privileged data is involved.
(() => {
const THEME_KEY = "gitdesk.theme";
const DARK_THEME = "dark";
const LIGHT_THEME = "light";

// Reads the saved theme from browser storage while tolerating restricted WebView storage.
function readSavedTheme() {
  try {
    const value = window.localStorage.getItem(THEME_KEY);
    if (value === DARK_THEME || value === LIGHT_THEME) {
      return value;
    }
  } catch (error) {
    console.warn("Theme preference could not be read.", error);
  }
  return "";
}

// Saves the selected theme so the desktop UI opens in the same mode next time.
function saveTheme(theme) {
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch (error) {
    console.warn("Theme preference could not be saved.", error);
  }
}

// Opens in GitDesk's dark glass theme unless the user explicitly saved another theme.
function preferredTheme() {
  return DARK_THEME;
}

// Reads the currently applied theme from the document root.
function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === DARK_THEME ? DARK_THEME : LIGHT_THEME;
}

// Updates the icon button label so assistive tech always describes the next action.
function updateThemeButton(theme) {
  const button = document.getElementById("toggle-theme");
  if (!button) {
    return;
  }

  const label = theme === DARK_THEME ? "Switch to light theme" : "Switch to dark theme";
  button.setAttribute("aria-label", label);
  button.setAttribute("title", label);
  button.classList.toggle("is-dark", theme === DARK_THEME);
}

// Applies the requested visual theme and notifies semantic color consumers without persisting it.
function applyTheme(theme) {
  const nextTheme = theme === LIGHT_THEME ? LIGHT_THEME : DARK_THEME;
  document.documentElement.setAttribute("data-theme", nextTheme);
  updateThemeButton(nextTheme);
  window.dispatchEvent(new CustomEvent("gitdesk:theme-changed", { detail: { theme: nextTheme } }));
}

// Applies and persists one explicit appearance choice from either the topbar or Theme settings.
function selectTheme(theme) {
  const nextTheme = theme === LIGHT_THEME ? LIGHT_THEME : DARK_THEME;
  applyTheme(nextTheme);
  saveTheme(nextTheme);
}

// Flips between light and dark mode from the topbar icon button.
function toggleTheme() {
  const nextTheme = currentTheme() === DARK_THEME ? LIGHT_THEME : DARK_THEME;
  selectTheme(nextTheme);
}

// Binds the topbar theme toggle after the DOM exists.
function bindThemeToggle() {
  const button = document.getElementById("toggle-theme");
  if (!button) {
    return;
  }
  button.addEventListener("click", toggleTheme);
  updateThemeButton(currentTheme());
}

// Runs a callback immediately when the document is parsed, or waits for parsing to finish.
function onDocumentReady(callback) {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", callback);
    return;
  }
  callback();
}

window.GitDeskTheme = { currentTheme, selectTheme };

applyTheme(readSavedTheme() || preferredTheme());
onDocumentReady(bindThemeToggle);
})();
