/* Saved Theme profile library for preview, reuse, deletion, and native JSON export. */

(() => {
const nativeBridge = window.GitDeskNativeBridge;
if (!nativeBridge) throw new Error("GitDesk theme profile dependencies did not load.");

const { callNative } = nativeBridge;
let profiles = [];
let selectedId = "";
let busy = false;
let options = null;

function markup() {
  return `
    <section class="theme-profile-manager" aria-labelledby="theme-profile-title">
      <header><div><span>Theme profiles</span><strong id="theme-profile-title">Save and reuse a complete look</strong>
        <p>Profiles keep all Dark and Light colors and role gradients together.</p></div></header>
      <div class="theme-profile-create">
        <label for="theme-profile-name">Profile name</label>
        <div><input id="theme-profile-name" maxlength="60" type="text" autocomplete="off"
          placeholder="My workspace"><button id="save-theme-profile" class="primary" type="button">
          Save current</button></div>
      </div>
      <div class="theme-profile-library">
        <label for="theme-profile-select">Saved profiles</label>
        <select id="theme-profile-select" aria-describedby="theme-profile-status"></select>
        <div><button id="load-theme-profile" type="button">Preview</button>
          <button id="export-theme-profile" type="button">Export</button>
          <button id="delete-theme-profile" type="button">Delete</button></div>
      </div>
      <p id="theme-profile-status" role="status" aria-live="polite"></p>
    </section>`;
}

function selectedProfile() {
  return profiles.find((profile) => profile.id === selectedId) || null;
}

function setStatus(message, isError = false) {
  const status = document.getElementById("theme-profile-status");
  if (!status) return;
  status.textContent = message;
  status.classList.toggle("danger", isError);
}

function render() {
  const select = document.getElementById("theme-profile-select");
  if (!select) return;
  const previous = selectedId;
  select.replaceChildren();
  if (!profiles.length) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No saved profiles";
    select.append(option);
    selectedId = "";
  } else {
    profiles.forEach((profile) => {
      const option = document.createElement("option");
      option.value = profile.id;
      option.textContent = profile.name;
      select.append(option);
    });
    selectedId = profiles.some((profile) => profile.id === previous) ? previous : profiles[0].id;
    select.value = selectedId;
  }
  const unavailable = busy || !selectedProfile();
  select.disabled = busy || !profiles.length;
  document.getElementById("save-theme-profile").disabled = busy;
  ["load", "export", "delete"].forEach((action) => {
    document.getElementById(`${action}-theme-profile`).disabled = unavailable;
  });
}

function applySettings(settings) {
  profiles = Array.isArray(settings && settings.theme_profiles) ? settings.theme_profiles : [];
  render();
}

async function saveProfile() {
  if (busy) return;
  const name = document.getElementById("theme-profile-name").value.trim();
  busy = true;
  render();
  setStatus("Saving theme profile…");
  try {
    const data = await callNative("saveThemeProfile", { name, ...options.snapshot() });
    applySettings(data.settings);
    const saved = profiles.find((profile) => profile.name.toLowerCase() === name.toLowerCase());
    if (saved) selectedId = saved.id;
    render();
    setStatus(`Saved ${saved ? saved.name : name}.`);
  } catch (error) {
    setStatus(error.message || "The theme profile could not be saved.", true);
  } finally {
    busy = false;
    render();
  }
}

function loadProfile() {
  const profile = selectedProfile();
  if (!profile) return;
  options.load(profile);
  setStatus(`${profile.name} is previewing. Apply colors to make it active.`);
}

async function exportProfile() {
  const profile = selectedProfile();
  if (!profile || busy) return;
  busy = true;
  render();
  setStatus(`Choose where to export ${profile.name}.`);
  try {
    const data = await callNative("exportThemeProfile", { profile_id: profile.id });
    setStatus(data.cancelled ? "Export cancelled." : `Exported ${profile.name}.`);
  } catch (error) {
    setStatus(error.message || "The theme profile could not be exported.", true);
  } finally {
    busy = false;
    render();
  }
}

async function deleteProfile() {
  const profile = selectedProfile();
  if (!profile || busy || !window.confirm(`Delete the theme profile “${profile.name}”?`)) return;
  busy = true;
  render();
  try {
    const data = await callNative("deleteThemeProfile", { profile_id: profile.id });
    applySettings(data.settings);
    setStatus(`Deleted ${profile.name}.`);
  } catch (error) {
    setStatus(error.message || "The theme profile could not be deleted.", true);
  } finally {
    busy = false;
    render();
  }
}

function handleClick(event) {
  if (event.target.closest("#save-theme-profile")) saveProfile();
  if (event.target.closest("#load-theme-profile")) loadProfile();
  if (event.target.closest("#export-theme-profile")) exportProfile();
  if (event.target.closest("#delete-theme-profile")) deleteProfile();
}

function bind(bindOptions) {
  options = bindOptions;
  const manager = document.querySelector(".theme-profile-manager");
  manager.addEventListener("click", handleClick);
  document.getElementById("theme-profile-select").addEventListener("change", (event) => {
    selectedId = event.target.value;
    render();
  });
  render();
}

window.GitDeskThemeProfileManager = { applySettings, bind, markup };
})();
