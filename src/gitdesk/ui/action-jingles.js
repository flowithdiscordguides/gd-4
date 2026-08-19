/*
  Repo Mode Actions terminal-run tracking, user-selected audio, and built-in success/failure melodies.
*/

// Keeps background audio and GitHub Settings controls separate from the Actions list renderer.
(() => {
const renderHelpers = window.GitDeskRender;

if (!renderHelpers) {
  throw new Error("GitDesk Actions jingle dependencies did not load.");
}

const { appendActivity, byId } = renderHelpers;
const JINGLE_KINDS = ["success", "failure"];
const MAX_TRACKED_RUNS = 500;
const DEFAULT_NOTES = Object.freeze({
  success: [
    { frequency: 523.25, offset: 0, duration: 0.22 },
    { frequency: 659.25, offset: 0.14, duration: 0.22 },
    { frequency: 783.99, offset: 0.28, duration: 0.3 },
  ],
  failure: [
    { frequency: 392, offset: 0, duration: 0.25 },
    { frequency: 311.13, offset: 0.18, duration: 0.28 },
    { frequency: 196, offset: 0.38, duration: 0.34 },
  ],
});
let runActionRef = null;
let audioContext = null;
let runTrackingReady = false;
let trackedRuns = new Map();
let playbackQueue = Promise.resolve();
let settings = {
  success: { custom: false, available: false, file_name: "" },
  failure: { custom: false, available: false, file_name: "" },
};

// Returns one Web Audio context so a user gesture can unlock both generated and selected-file playback.
function getAudioContext() {
  if (audioContext) return audioContext;
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return null;
  audioContext = new AudioContextClass();
  return audioContext;
}

// Resumes audio during normal user interaction; later background completion sounds reuse the running context.
function unlockAudio() {
  const context = getAudioContext();
  if (context && context.state === "suspended") {
    context.resume().catch((error) => {
      console.warn("Actions jingle audio could not be unlocked.", error);
    });
  }
}

// Returns a running context or rejects explicitly when this WebView cannot play completion audio.
async function runningAudioContext() {
  const context = getAudioContext();
  if (!context) {
    throw new Error("Web Audio is unavailable.");
  }
  if (context.state === "suspended") {
    await context.resume();
  }
  if (context.state !== "running") {
    throw new Error("Web Audio is not running.");
  }
  return context;
}

// Plays one short dependency-free melody and resolves after its last oscillator stops.
async function playDefaultJingle(kind) {
  const context = await runningAudioContext();
  const notes = DEFAULT_NOTES[kind] || DEFAULT_NOTES.failure;
  const startedAt = context.currentTime + 0.02;
  notes.forEach((note) => {
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    const noteStart = startedAt + note.offset;
    const noteEnd = noteStart + note.duration;
    oscillator.type = kind === "success" ? "sine" : "triangle";
    oscillator.frequency.setValueAtTime(note.frequency, noteStart);
    gain.gain.setValueAtTime(0.0001, noteStart);
    gain.gain.exponentialRampToValueAtTime(0.08, noteStart + 0.025);
    gain.gain.exponentialRampToValueAtTime(0.0001, noteEnd);
    oscillator.connect(gain);
    gain.connect(context.destination);
    oscillator.start(noteStart);
    oscillator.stop(noteEnd + 0.01);
  });
  const finalNote = notes[notes.length - 1];
  const totalMs = Math.ceil((finalNote.offset + finalNote.duration + 0.04) * 1000);
  await new Promise((resolve) => window.setTimeout(resolve, totalMs));
}

// Decodes a backend-validated data URL into the unlocked context and resolves at the audible end.
async function playCustomJingle(dataUrl) {
  const context = await runningAudioContext();
  const response = await window.fetch(dataUrl);
  const encodedAudio = await response.arrayBuffer();
  const audioBuffer = await context.decodeAudioData(encodedAudio);
  await new Promise((resolve, reject) => {
    const source = context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(context.destination);
    source.onended = resolve;
    try {
      source.start();
    } catch (error) {
      reject(error);
    }
  });
}

// Describes one saved choice without exposing the private absolute path returned only to Python storage.
function settingLabel(kind) {
  const choice = settings[kind];
  if (!choice.custom) {
    return `Built-in ${kind} jingle`;
  }
  if (!choice.available) {
    return `${choice.file_name || "Selected audio"} · unavailable; built-in jingle will play`;
  }
  return choice.file_name || `Custom ${kind} jingle`;
}

// Synchronizes both Settings rows with saved basename-only state.
function renderSettings() {
  JINGLE_KINDS.forEach((kind) => {
    const label = document.getElementById(`action-jingle-${kind}-file`);
    if (label) label.textContent = settingLabel(kind);
  });
}

// Accepts the bootstrap or replacement response and normalizes both required setting records.
function applySettings(value) {
  const source = value && typeof value === "object" ? value : {};
  JINGLE_KINDS.forEach((kind) => {
    const choice = source[kind] && typeof source[kind] === "object" ? source[kind] : {};
    settings[kind] = {
      custom: Boolean(choice.custom),
      available: Boolean(choice.available),
      file_name: String(choice.file_name || ""),
    };
  });
  renderSettings();
}

// Loads custom audio only at playback time and falls back to the matching built-in melody on any failure.
async function playConfiguredJingle(kind) {
  const choice = settings[kind];
  if (choice && choice.custom && runActionRef) {
    try {
      const payload = await runActionRef("actionJingleAudio", { kind }, "", { quiet: true });
      if (!payload.custom || !payload.data_url) {
        throw new Error("The configured jingle has no playable audio.");
      }
      await playCustomJingle(payload.data_url);
      return;
    } catch (error) {
      console.warn(`Custom ${kind} Actions jingle could not be played; using the built-in jingle.`, error);
    }
  }
  await playDefaultJingle(kind);
}

// Serializes terminal sounds so simultaneous workflow completions remain individually audible.
function enqueueJingle(kind) {
  playbackQueue = playbackQueue
    .then(() => playConfiguredJingle(kind))
    .catch((error) => {
      console.warn(`The ${kind} Actions jingle could not be played.`, error);
    });
}

// Maps GitHub's existing alert semantics onto the two requested audio outcomes.
function terminalKind(run) {
  if (!run || run.status !== "completed" || !run.conclusion) return "";
  return run.conclusion === "success" ? "success" : "failure";
}

// Observes each run once, seeding startup history silently and sounding only newly terminal results afterward.
function syncRuns(runList) {
  const runs = Array.isArray(runList) ? runList : [];
  runs.forEach((run) => {
    const runId = String(run && run.id || "");
    if (!runId) return;
    const kind = terminalKind(run);
    const previous = trackedRuns.get(runId);
    if (runTrackingReady && kind && (previous === "active" || previous === undefined)) {
      enqueueJingle(kind);
    }
    trackedRuns.set(runId, kind || "active");
  });
  while (trackedRuns.size > MAX_TRACKED_RUNS) {
    trackedRuns.delete(trackedRuns.keys().next().value);
  }
  runTrackingReady = true;
}

// Clears repository-scoped run identities so another repository's history seeds without false sounds.
function resetRuns() {
  runTrackingReady = false;
  trackedRuns = new Map();
}

// Replaces one jingle through the native picker while cancellation remains a quiet no-change result.
async function replaceJingle(kind) {
  const button = byId(`replace-action-jingle-${kind}`);
  const status = byId("action-jingle-status");
  button.disabled = true;
  status.textContent = `Choose a ${kind} audio file…`;
  try {
    const data = await runActionRef("replaceActionJingle", { kind }, "");
    applySettings(data.action_jingles);
    if (data.cancelled) {
      status.textContent = "Jingle selection cancelled; the current choice was kept.";
      return;
    }
    status.textContent = `${kind === "success" ? "Success" : "Failure"} jingle replaced.`;
    appendActivity(`${kind === "success" ? "Success" : "Failure"} Actions jingle replaced`);
  } catch (error) {
    status.textContent = error.message || "The jingle could not be replaced.";
    throw error;
  } finally {
    button.disabled = false;
  }
}

// Binds the two stable GitHub Settings controls after settings-tabs.js has injected their markup.
function bind(runAction) {
  runActionRef = runAction;
  JINGLE_KINDS.forEach((kind) => {
    byId(`replace-action-jingle-${kind}`).addEventListener("click", () => {
      replaceJingle(kind).catch(() => {});
    });
  });
  document.addEventListener("pointerdown", unlockAudio, { capture: true });
  document.addEventListener("keydown", unlockAudio, { capture: true });
  renderSettings();
}

window.GitDeskActionJingles = { applySettings, bind, resetRuns, syncRuns };
})();
