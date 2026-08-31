// Device registration wizard.
"use strict";

const settingsPanel = document.getElementById("settings-panel");
const settingsStatus = document.getElementById("settings-status");
const serverHostInput = document.getElementById("server-host");

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

function log(message, kind = "info") {
  const line = document.createElement("p");
  line.className = `log-${kind}`;
  line.textContent = message;
  logElement.appendChild(line);
  line.scrollIntoView();
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
}

function markStep(stepName, stateClass) {
  const item = document.querySelector(`#steps li[data-step="${stepName}"]`);
  item.className = stateClass;
}

function hideFailureActions() {
  failureActions.hidden = true;
  retryButton.hidden = true;
  backButton.hidden = true;
}

function fail(error, recovery) {
  markStep(recovery.step, "failed");
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
    settingsPanel.open = true;
    throw new Error("Set the server host under Server settings first.");
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

async function fetchCredentials() {
  // Failing fast here falls back to the cached credentials.
  const config = await serverRequest("/api/setup/config", { timeoutMs: 5000 });
  if (config.server_host && config.server_host !== serverHost()) {
    localStorage.setItem("serverHost", config.server_host);
    serverHostInput.value = config.server_host;
  }
  if (!config.wifi_ssid) {
    throw new Error("No Wi-Fi network saved on the server — set one on its Setup page.");
  }
  const credentials = { ssid: config.wifi_ssid, password: config.wifi_password, host: serverHost() };
  localStorage.setItem(CREDENTIALS_KEY, JSON.stringify(credentials));
  return credentials;
}

// Credentials are cached per server host, so switching hosts triggers a
// refetch but re-running the wizard against the same server does not.
function savedCredentials() {
  try {
    return JSON.parse(localStorage.getItem(CREDENTIALS_KEY));
  } catch {
    return null;
  }
}

function cachedCredentialsForCurrentHost() {
  const cached = savedCredentials();
  return cached && cached.host === serverHost() ? cached : null;
}

// Wizard steps.

async function stepCredentials() {
  markStep("credentials", "active");
  const cached = cachedCredentialsForCurrentHost();
  if (cached) {
    state.credentials = cached;
    log(`Using saved credentials for "${state.credentials.ssid}".`);
  } else {
    log("Fetching Wi-Fi credentials from the server…");
    try {
      state.credentials = await fetchCredentials();
      log(`Got credentials for "${state.credentials.ssid}".`);
    } catch (error) {
      state.credentials = savedCredentials();
      if (!state.credentials) {
        throw error;
      }
      log(`${error.message}`, "warn");
      log(`Using saved credentials for "${state.credentials.ssid}" (from a different server).`);
      logDetail(error.detail);
    }
  }
  markStep("credentials", "done");
  markStep("switch", "active");
  showPanel("switch");
}

async function stepConfigure() {
  markStep("switch", "done");
  markStep("configure", "active");
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
  if (result.status === "1") {
    log("Device reports it joined your network.");
  } else {
    log(`Device reports: ${result.label}. It may still join within a minute.`, "warn");
    logDetail(result.detail);
  }
  markStep("configure", "done");
  markStep("verify", "active");
  showPanel("verify");
}

async function stepVerify() {
  markStep("verify", "active");
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
      markStep("verify", "done");
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

function runCredentials() {
  return attempt(stepCredentials, {
    step: "credentials",
    retryLabel: "Retry fetching credentials",
    retry: runCredentials,
  });
}

function runConfigure() {
  return attempt(stepConfigure, {
    step: "configure",
    retryLabel: "Retry sending Wi-Fi details",
    retry: runConfigure,
    backLabel: "I'm not on the device's Wi-Fi yet",
    back: () => {
      hideFailureActions();
      markStep("configure", "");
      markStep("switch", "active");
      showPanel("switch");
    },
  });
}

function runVerify() {
  return attempt(stepVerify, {
    step: "verify",
    retryLabel: "Retry verification",
    retry: runVerify,
    backLabel: "Re-send Wi-Fi details to the device",
    back: () => {
      hideFailureActions();
      markStep("verify", "");
      runConfigure();
    },
  });
}

// Settings.

document.getElementById("settings-save").addEventListener("click", async () => {
  const typed = normalizeHost(serverHostInput.value);
  serverHostInput.value = typed;
  localStorage.setItem("serverHost", typed);
  settingsStatus.textContent = "Checking…";
  try {
    const credentials = await fetchCredentials();
    const resolved = serverHost();
    settingsStatus.textContent =
      resolved === typed
        ? `Connected. Server has credentials for "${credentials.ssid}".`
        : `Connected as ${resolved}. Server has credentials for "${credentials.ssid}".`;
    settingsPanel.open = false;
  } catch (error) {
    settingsStatus.textContent = error.message;
  }
});

// Event handlers.

document.getElementById("start-button").addEventListener("click", () => {
  logElement.replaceChildren();
  state.device = null;
  state.ap = null;
  runCredentials();
});

document.getElementById("joined-button").addEventListener("click", runConfigure);
document.getElementById("back-home-button").addEventListener("click", runVerify);
resetButton.addEventListener("click", () => window.location.reload());

serverHostInput.value = serverHost();
settingsPanel.open = !serverHost();
showPanel("start");
