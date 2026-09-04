// Device registration wizard.
"use strict";

const settingsPanel = document.getElementById("settings-panel");
const settingsStatus = document.getElementById("settings-status");
const serverHostInput = document.getElementById("server-host");
const sendLogButton = document.getElementById("send-log-button");
const logSendStatus = document.getElementById("log-send-status");

const wifiSsidInput = document.getElementById("wifi-ssid");
const wifiPasswordInput = document.getElementById("wifi-password");
const wifiSsidSource = document.getElementById("wifi-ssid-source");
const wifiPasswordSource = document.getElementById("wifi-password-source");

document.querySelectorAll("[data-reveal]").forEach((button) => {
  const input = document.getElementById(button.dataset.reveal);
  button.addEventListener("click", () => {
    const revealed = input.type === "text";
    input.type = revealed ? "password" : "text";
    button.textContent = revealed ? "Reveal" : "Hide";
  });
});

const panels = {
  start: document.getElementById("panel-start"),
  switch: document.getElementById("panel-switch"),
  verify: document.getElementById("panel-verify"),
};
const logElement = document.getElementById("log");
const failureActions = document.getElementById("failure-actions");
const retryButton = document.getElementById("retry-button");
const backButton = document.getElementById("back-button");
const resetButton = document.getElementById("reset-button");

const state = {
  credentials: null,
  device: null,
  ap: null,
};

const SERVER_PORT = 8000;
const CREDENTIALS_KEY = "credentials";
const LOG_KEY = "wemo-setup-log";
let logBuffer = [];

function serverHost() {
  return localStorage.getItem("serverHost") || "";
}

// Accepts a bare host or a pasted URL.
function normalizeHost(value) {
  return value
    .trim()
    .replace(/^[a-z]+:\/\//i, "")
    .replace(/\/.*$/, "")
    .replace(/:\d+$/, "");
}

function showPanel(name) {
  Object.entries(panels).forEach(([key, el]) => (el.hidden = key !== name));
}

function persistLog() {
  localStorage.setItem(LOG_KEY, logBuffer.join("\n"));
  updateSendLogButton();
}

function log(message, kind = "info") {
  const line = document.createElement("p");
  line.className = `log-${kind}`;
  line.textContent = message;
  logElement.appendChild(line);
  line.scrollIntoView();
  logBuffer.push(message);
  persistLog();
}

function logDetail(detail) {
  if (!detail) return;
  const block = document.createElement("details");
  block.className = "log-detail";
  const summary = document.createElement("summary");
  summary.textContent = "Technical detail";
  const pre = document.createElement("pre");
  pre.textContent = detail;
  block.append(summary, pre);
  logElement.appendChild(block);
  block.scrollIntoView();
  logBuffer.push(detail);
  persistLog();
}

function updateSendLogButton() {
  sendLogButton.disabled = !(localStorage.getItem(LOG_KEY) && serverHost());
}

function hideFailureActions() {
  failureActions.hidden = true;
  retryButton.hidden = true;
  backButton.hidden = true;
}

function fail(error, recovery) {
  log(error.message || String(error), "error");
  logDetail(error.detail);
  showPanel(null);

  retryButton.hidden = false;
  retryButton.textContent = recovery.retryLabel;
  retryButton.onclick = recovery.retry;

  backButton.hidden = !recovery.back;
  if (recovery.back) {
    backButton.textContent = recovery.backLabel;
    backButton.onclick = recovery.back;
  }
  failureActions.hidden = false;
}

// Each step reruns on its own after a failure.
function attempt(task, recovery) {
  hideFailureActions();
  return task().catch((error) => fail(error, recovery));
}

async function serverRequest(path, options = {}) {
  const host = serverHost();
  const method = options.method || "GET";
  if (!host) {
    throw new Error("No server host is set.");
  }
  const base = `http://${host}:${SERVER_PORT}`;
  const response = await httpRequest({
    url: base + path,
    method,
    headers: options.data ? { "Content-Type": "application/json" } : {},
    data: options.data ? JSON.stringify(options.data) : undefined,
    timeoutMs: options.timeoutMs || 15000,
  });
  let body;
  try {
    body = JSON.parse(response.body);
  } catch {
    body = null;
  }
  if (response.status < 200 || response.status >= 300) {
    const detail = body && body.detail ? body.detail : `HTTP ${response.status}`;
    throw protocolError(
      `Server: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`,
      `${method} ${base}${path}\n\n--- response (HTTP ${response.status}) ---\n${response.body}`
    );
  }
  return body;
}

function savedCredentials() {
  try {
    return JSON.parse(localStorage.getItem(CREDENTIALS_KEY));
  } catch {
    return null;
  }
}

function setCredentialSource(text) {
  wifiSsidSource.textContent = text;
  wifiPasswordSource.textContent = text;
}

// Fills the Wi-Fi fields per precedence: saved credentials, then a
// best-effort server fetch (only if a host is set), else left blank.
async function prefillCredentials() {
  const cached = savedCredentials();
  if (cached && (cached.ssid || cached.password)) {
    wifiSsidInput.value = cached.ssid || "";
    wifiPasswordInput.value = cached.password || "";
    setCredentialSource("Saved");
    return;
  }
  if (!serverHost()) return;
  try {
    const config = await serverRequest("/api/setup/config", { timeoutMs: 5000 });
    if (config.wifi_ssid) {
      wifiSsidInput.value = config.wifi_ssid;
      wifiPasswordInput.value = config.wifi_password || "";
      setCredentialSource("From server");
    }
  } catch {
    // Best-effort — leave the fields blank.
  }
}

// Editing a field means the user is overriding whatever it was prefilled with.
wifiSsidInput.addEventListener("input", () => setCredentialSource(""));
wifiPasswordInput.addEventListener("input", () => setCredentialSource(""));

// Wizard steps. Credential resolution happens by simply reading the fields
// at start time — the fields already hold typed/saved/server-fetched values
// in that order of precedence, so there is no separate resolution step.

async function stepConfigure() {
  showPanel(null);
  log("Looking for the device at 10.22.22.1…");
  state.device = await findSetupDevice();
  log(`Found "${state.device.name}" (${state.device.udn}).`);

  log(`Asking the device to scan for "${state.credentials.ssid}"…`);
  state.ap = await findHomeAp(state.device, state.credentials.ssid);
  log(`Device sees it on channel ${state.ap.channel} (${state.ap.authMode}/${state.ap.encryption}).`);

  const result = await connectDeviceToHome(
    state.device,
    state.credentials.ssid,
    state.credentials.password,
    state.ap,
    (message) => log(message)
  );
  if (result.status === "2") {
    throw protocolError(
      "The device rejected the password as too short (minimum 8 characters).",
      result.detail
    );
  }
  if (result.status === "1" && result.closeStatus === "success") {
    log("Device reports it joined your network and setup closed cleanly.");
  } else if (result.status === "1") {
    log(
      `Device reports it joined your network, but setup didn't close cleanly `
        + `(CloseSetup: ${result.closeStatus}) — it may not stick. Verifying anyway.`,
      "warn"
    );
    logDetail(result.detail);
  } else {
    log(`Device reports: ${result.label}. It may still join within a minute.`, "warn");
    logDetail(result.detail);
  }

  if (!serverHost()) {
    log(
      "No server host is set, so registration can't be confirmed automatically. "
        + "Once the device is reachable on your network, register it from the web UI.",
      "success"
    );
    failureActions.hidden = false;
    return;
  }
  showPanel("verify");
}

async function stepVerify() {
  showPanel(null);
  log("Checking with the server (this scans your network; give it a minute)…");
  const { network } = await serverRequest("/api/devices/default-network");
  let lastSeen = [];
  for (let attemptNumber = 1; attemptNumber <= 4; attemptNumber++) {
    const result = await serverRequest("/api/devices/detect", {
      method: "POST",
      data: { target: network, timeout: 2.0 },
      timeoutMs: 120000,
    });
    lastSeen = result.devices;
    const found = lastSeen.find((d) => d.udn === state.device.udn);
    if (found) {
      await serverRequest("/api/devices/detect/commit", {
        method: "POST",
        data: { udns: [found.udn] },
      });
      log(`Registered "${found.name}" at ${found.host}. All done!`, "success");
      failureActions.hidden = false;
      return;
    }
    log(`Not visible yet (scan ${attemptNumber}/4)…`);
    await sleep(10000);
  }
  throw protocolError(
    "The device never appeared on your network. Its light shows whether it joined; "
      + "if it's still blinking, go back a step and send the credentials again.",
    `scanned ${network} four times\nlooking for UDN: ${state.device.udn}\n\n`
      + `last scan found ${lastSeen.length} device(s):\n`
      + (lastSeen.map((d) => `  ${d.name} — ${d.host} — ${d.udn}`).join("\n") || "  (none)")
  );
}

// Step runners, each retryable in place.

function runConfigure() {
  return attempt(stepConfigure, {
    retryLabel: "Retry sending Wi-Fi details",
    retry: runConfigure,
    backLabel: "I'm not on the device's Wi-Fi yet",
    back: () => {
      hideFailureActions();
      showPanel("switch");
    },
  });
}

function runVerify() {
  return attempt(stepVerify, {
    retryLabel: "Retry verification",
    retry: runVerify,
    backLabel: "Re-send Wi-Fi details to the device",
    back: () => {
      hideFailureActions();
      runConfigure();
    },
  });
}

// Settings.

document.getElementById("settings-save").addEventListener("click", async () => {
  const typed = normalizeHost(serverHostInput.value);
  serverHostInput.value = typed;
  localStorage.setItem("serverHost", typed);
  updateSendLogButton();
  if (!typed) {
    settingsStatus.textContent = "Server host cleared.";
    return;
  }
  settingsStatus.textContent = "Checking…";
  try {
    const config = await serverRequest("/api/setup/config", { timeoutMs: 5000 });
    settingsStatus.textContent = config.wifi_ssid
      ? `Connected. Server has credentials for "${config.wifi_ssid}".`
      : "Connected. No Wi-Fi network saved on the server yet.";
    if (!wifiSsidInput.value && !wifiPasswordInput.value && config.wifi_ssid) {
      wifiSsidInput.value = config.wifi_ssid;
      wifiPasswordInput.value = config.wifi_password || "";
      setCredentialSource("From server");
    }
    settingsPanel.open = false;
  } catch (error) {
    settingsStatus.textContent = error.message;
  }
});

sendLogButton.addEventListener("click", async () => {
  logSendStatus.textContent = "Sending…";
  try {
    await serverRequest("/api/setup/logs", { data: { text: localStorage.getItem(LOG_KEY) || "" }, method: "POST" });
    logSendStatus.textContent = "Log sent.";
  } catch (error) {
    logSendStatus.textContent = error.message;
  }
});

// Event handlers.

document.getElementById("start-button").addEventListener("click", () => {
  const ssid = wifiSsidInput.value.trim();
  const password = wifiPasswordInput.value;
  if (!ssid) {
    wifiSsidInput.focus();
    return;
  }
  logElement.replaceChildren();
  logBuffer = [];
  persistLog();
  hideFailureActions();
  state.credentials = { ssid, password, host: serverHost() };
  state.device = null;
  state.ap = null;
  localStorage.setItem(CREDENTIALS_KEY, JSON.stringify(state.credentials));
  log(`Using Wi-Fi network "${ssid}".`);
  showPanel("switch");
});

document.getElementById("joined-button").addEventListener("click", runConfigure);
document.getElementById("back-home-button").addEventListener("click", runVerify);
resetButton.addEventListener("click", () => window.location.reload());

serverHostInput.value = serverHost();
settingsPanel.open = !serverHost();
updateSendLogButton();
prefillCredentials();
showPanel("start");
