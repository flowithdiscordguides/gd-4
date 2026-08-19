/*
  Promise-based WebUI bridge wrapper. Secrets are never stored here; token values are sent once to Python.
*/

// Keeps classic-script variables private while exposing only the native bridge API.
(() => {
const REQUEST_TIMEOUT_MS = 120000;
const SYNC_REQUEST_TIMEOUT_MS = 1800000;
const BRIDGE_WAIT_MS = 10000;
const BRIDGE_POLL_MS = 50;

// Creates an opaque request id used to pair Python responses with JavaScript promises.
function createRequestId() {
  const randomPart = Math.random().toString(36).slice(2);
  return `${Date.now()}-${randomPart}`;
}

// Converts backend error payloads into JavaScript Error instances with a stable code field.
function toError(errorPayload) {
  const payload = errorPayload || {};
  const error = new Error(payload.message || "Native request failed.");
  error.code = payload.code || "NATIVE_REQUEST_FAILED";
  error.details = payload.details || {};
  return error;
}

// Converts a JSON response string from Python into the envelope shape used by the frontend.
function parseResponse(rawResponse) {
  if (typeof rawResponse !== "string") {
    return rawResponse;
  }

  try {
    return JSON.parse(rawResponse);
  } catch (error) {
    throw new Error("Native bridge returned invalid JSON.");
  }
}

// Applies a timeout to native calls so a hung Git operation does not leave the UI waiting forever.
function withTimeout(promise, action) {
  let timeoutId;
  const timeout = new Promise((resolve, reject) => {
    timeoutId = window.setTimeout(() => {
      reject(new Error(`Native action timed out: ${action}`));
    }, action.indexOf("syncChain") === 0 || action.indexOf("Backup") >= 0
      || action === "syncLocalVersionToPrivateBeta"
      ? SYNC_REQUEST_TIMEOUT_MS : REQUEST_TIMEOUT_MS);
  });

  return Promise.race([promise, timeout]).then((result) => {
    window.clearTimeout(timeoutId);
    return result;
  }, (error) => {
    window.clearTimeout(timeoutId);
    throw error;
  });
}

// Returns the native function created by webui.js after Python binds nativeInvoke.
function getNativeInvoke() {
  const globalScope = typeof globalThis === "undefined" ? window : globalThis;
  if (typeof window.nativeInvoke === "function") {
    return window.nativeInvoke;
  }
  if (typeof globalScope.nativeInvoke === "function") {
    return globalScope.nativeInvoke;
  }
  return null;
}

// Waits for WebUI to install the bound native function before declaring startup failure.
function waitForNativeInvoke() {
  const startedAt = Date.now();

  return new Promise((resolve, reject) => {
    function checkBridge() {
      const nativeInvoke = getNativeInvoke();
      if (nativeInvoke) {
        resolve(nativeInvoke);
        return;
      }
      if (Date.now() - startedAt >= BRIDGE_WAIT_MS) {
        reject(new Error("The WebUI native bridge is not available."));
        return;
      }
      window.setTimeout(checkBridge, BRIDGE_POLL_MS);
    }

    checkBridge();
  });
}

// Lets synchronous click, status, and loading feedback paint before native work can occupy the bridge turn.
function waitForUiPaint() {
  if (document.hidden || typeof window.requestAnimationFrame !== "function") {
    return new Promise((resolve) => window.setTimeout(resolve, 0));
  }
  return new Promise((resolve) => {
    window.requestAnimationFrame(() => window.setTimeout(resolve, 0));
  });
}

// Sends an action to Python through webui.js and resolves with Python's direct response.
function callNative(action, payload = {}) {
  return Promise.all([waitForNativeInvoke(), waitForUiPaint()]).then(([nativeInvoke]) => {
    return invokeNativeFunction(nativeInvoke, action, payload);
  });
}

// Invokes WebUI's generated function after bridge availability has been confirmed.
function invokeNativeFunction(nativeInvoke, action, payload) {
  const requestId = createRequestId();
  const request = { requestId, action, payload };

  let nativePromise;
  try {
    nativePromise = Promise.resolve(nativeInvoke(JSON.stringify(request))).then(parseResponse);
  } catch (error) {
    return Promise.reject(error);
  }

  return withTimeout(nativePromise, action).then((response) => {
    const responsePayload = response || {};
    if (responsePayload.ok) {
      return responsePayload.data;
    }
    throw toError(responsePayload.error);
  });
}

// Publishes the bridge API for classic WebView script loading, avoiding fragile ES module support.
window.GitDeskNativeBridge = {
  callNative,
};
})();
