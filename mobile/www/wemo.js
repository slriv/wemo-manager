// WeMo access-point setup protocol.
"use strict";

const WEMO_AP_HOST = "10.22.22.1";
const SETUP_PORTS = [49152, 49153, 49154];
// Appended to the key material for method-2 (RTOS, non-IoT) devices.
const METHOD2_KEY_SUFFIX = "b3{8t;80dIN{ra83eC1s?M70?683@2Yf";

// Other codes have no confirmed meaning and are reported verbatim.
const NETWORK_STATUS_LABELS = {
  "0": "still connecting",
  "1": "connected",
  "2": "password rejected as too short",
  "3": "still connecting",
};

function protocolError(message, detail) {
  const error = new Error(message);
  error.detail = detail;
  return error;
}

function nativeHttp() {
  const cap = window.Capacitor;
  return cap && cap.Plugins && cap.Plugins.CapacitorHttp ? cap.Plugins.CapacitorHttp : null;
}

// Native HTTP bypasses the WebView's CORS and cleartext limits.
async function httpRequest({ url, method = "GET", headers = {}, data, timeoutMs = 10000 }) {
  const plugin = nativeHttp();
  const transport = plugin ? "native" : "fetch";
  try {
    if (plugin) {
      const response = await plugin.request({
        url,
        method,
        headers,
        data,
        connectTimeout: timeoutMs,
        readTimeout: timeoutMs,
        responseType: "text",
      });
      const body =
        typeof response.data === "string" ? response.data : JSON.stringify(response.data);
      return { status: response.status, body };
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        method,
        headers,
        body: data,
        signal: controller.signal,
      });
      return { status: response.status, body: await response.text() };
    } finally {
      clearTimeout(timer);
    }
  } catch (cause) {
    const reason = (cause && cause.message) || String(cause);
    throw protocolError(
      `${method} ${url} failed: ${reason}`,
      `${method} ${url}\ntransport: ${transport}\ntimeout: ${timeoutMs} ms\nerror: ${reason}`
    );
  }
}

function parseXml(text) {
  const doc = new DOMParser().parseFromString(text, "text/xml");
  if (doc.querySelector("parsererror")) {
    throw protocolError("Unparseable XML from device", text);
  }
  return doc;
}

function xmlText(doc, tagName) {
  const nodes = doc.getElementsByTagName(tagName);
  return nodes.length ? nodes[0].textContent.trim() : "";
}

function escapeXml(value) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function soapCall(baseUrl, service, action, args = {}) {
  const argXml = Object.entries(args)
    .map(([name, value]) => `<${name}>${escapeXml(String(value))}</${name}>`)
    .join("");
  const envelope =
    '<?xml version="1.0" encoding="utf-8"?>' +
    '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" ' +
    's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">' +
    `<s:Body><u:${action} xmlns:u="urn:Belkin:service:${service}:1">${argXml}</u:${action}>` +
    "</s:Body></s:Envelope>";

  const { status, body } = await httpRequest({
    url: `${baseUrl}/upnp/control/${service}1`,
    method: "POST",
    headers: {
      "Content-Type": 'text/xml; charset="utf-8"',
      SOAPACTION: `"urn:Belkin:service:${service}:1#${action}"`,
      // The device's httpd doesn't support keep-alive; reusing a pooled
      // connection from a prior call aborts the write ("Software caused
      // connection abort").
      Connection: "close",
    },
    data: envelope,
  });
  if (status < 200 || status >= 300) {
    throw protocolError(
      `${action} failed with HTTP ${status}`,
      `POST ${baseUrl}/upnp/control/${service}1\n`
        + `SOAPACTION: "urn:Belkin:service:${service}:1#${action}"\n\n`
        + `--- request ---\n${envelope}\n\n--- response (HTTP ${status}) ---\n${body}`
    );
  }
  return parseXml(body);
}

async function findSetupDevice() {
  const attempts = [];
  for (const port of SETUP_PORTS) {
    const baseUrl = `http://${WEMO_AP_HOST}:${port}`;
    let body;
    try {
      ({ body } = await httpRequest({ url: `${baseUrl}/setup.xml`, timeoutMs: 4000 }));
    } catch (error) {
      attempts.push(`port ${port}: ${error.message}`);
      continue;
    }
    let doc;
    try {
      doc = parseXml(body);
    } catch {
      attempts.push(`port ${port}: replied but the XML did not parse:\n${body}`);
      continue;
    }
    const manufacturer = xmlText(doc, "manufacturer");
    if (!manufacturer.startsWith("Belkin")) {
      attempts.push(`port ${port}: replied, but manufacturer is "${manufacturer}", not Belkin`);
      continue;
    }
    return {
      baseUrl,
      name: xmlText(doc, "friendlyName"),
      udn: xmlText(doc, "UDN"),
      mac: xmlText(doc, "macAddress"),
      serial: xmlText(doc, "serialNumber"),
      rtos: xmlText(doc, "rtos") === "1",
      iot: xmlText(doc, "iot") === "1",
    };
  }
  throw protocolError(
    `No WeMo found at ${WEMO_AP_HOST} — check that this phone is on the device's Wemo.* network.`,
    attempts.join("\n\n")
  );
}

// Read key material with setup metadata fallback.
async function getKeyMaterial(device) {
  let metaError = "GetMetaInfo not attempted";
  try {
    const doc = await soapCall(device.baseUrl, "metainfo", "GetMetaInfo");
    const [mac, serial] = xmlText(doc, "MetaInfo").split("|");
    if (mac && serial) return { mac, serial };
    metaError = `GetMetaInfo returned an unusable MetaInfo field: "${xmlText(doc, "MetaInfo")}"`;
  } catch (error) {
    metaError = `GetMetaInfo failed: ${error.message}\n${error.detail || ""}`;
  }
  if (device.mac && device.serial) return { mac: device.mac, serial: device.serial };
  throw protocolError(
    "Device did not reveal its MAC/serial (needed for password encryption)",
    `${metaError}\n\nsetup.xml fallback: macAddress="${device.mac}" serialNumber="${device.serial}"`
  );
}

// Find the requested access point.
async function findHomeAp(device, ssid) {
  const doc = await soapCall(device.baseUrl, "WiFiSetup", "GetApList");
  const apList = xmlText(doc, "ApList");
  const lines = apList.split("\n").slice(1);
  for (let line of lines) {
    line = line.trim().replace(/,$/, "");
    if (!line || !line.includes("|") || !line.startsWith(`${ssid}|`)) continue;
    const columns = line.split("|");
    const channel = columns[1].trim();
    const authString = columns[columns.length - 1].trim();
    if (authString === "Unknown") {
      throw protocolError(
        `The device reports "${ssid}" with an unknown authorization mode (WPA3-only?)`,
        `matched scan entry:\n${line}`
      );
    }
    const [authMode, encryption] = authString.split("/");
    if (!["NONE", "AES", "TKIPAES"].includes(encryption)) {
      throw protocolError(
        `Unsupported Wi-Fi encryption ${encryption} on "${ssid}"`,
        `matched scan entry:\n${line}`
      );
    }
    return { channel, authMode, encryption };
  }
  throw protocolError(
    `The device can't see the network "${ssid}" — move it closer to your router and retry.`,
    `networks the device did see:\n${apList.trim() || "(the scan came back empty)"}`
  );
}

// Derive the device-specific AES key.
async function encryptWifiPassword(password, { mac, serial }, { rtos, iot }) {
  const method = rtos && !iot ? 2 : 1;
  const addLengths = method === 1;

  let keydata = mac.slice(0, 6) + serial + mac.slice(6, 12);
  if (method === 2) keydata += METHOD2_KEY_SUFFIX;
  const salt = keydata.slice(0, 8);
  const iv = keydata.slice(0, 16);

  const encoder = new TextEncoder();
  const derivedKey = md5Bytes(encoder.encode(keydata + salt)).slice(0, 16);
  const cryptoKey = await crypto.subtle.importKey("raw", derivedKey, "AES-CBC", false, [
    "encrypt",
  ]);
  const cipherBuf = await crypto.subtle.encrypt(
    { name: "AES-CBC", iv: encoder.encode(iv) },
    cryptoKey,
    encoder.encode(password)
  );
  let encrypted = btoa(String.fromCharCode(...new Uint8Array(cipherBuf)));

  if (encrypted.length > 255 || password.length > 255) {
    throw protocolError(
      "Wi-Fi password too long for WeMo (255 char limit after encryption)",
      `password length ${password.length}, ciphertext length ${encrypted.length}`
    );
  }
  if (addLengths) {
    encrypted += encrypted.length.toString(16).padStart(2, "0");
    encrypted += password.length.toString(16).padStart(2, "0");
  }
  return encrypted;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Connect the device to Wi-Fi.
async function connectDeviceToHome(device, ssid, password, ap, onProgress) {
  let auth = ap.authMode;
  let encryptedPassword = "";
  if (ap.encryption === "NONE") {
    auth = "OPEN";
  } else {
    const keyMaterial = await getKeyMaterial(device);
    encryptedPassword = await encryptWifiPassword(password, keyMaterial, device);
  }

  // Firmware drops or aborts the first request often enough to need a retry.
  onProgress("Sending Wi-Fi credentials to the device…");
  let sendError = null;
  for (let i = 0; i < 2; i++) {
    try {
      await soapCall(device.baseUrl, "WiFiSetup", "ConnectHomeNetwork", {
        ssid,
        auth,
        password: encryptedPassword,
        encrypt: ap.encryption,
        channel: ap.channel,
      });
      sendError = null;
    } catch (error) {
      sendError = error;
    }
    if (i === 0) await sleep(100);
  }
  if (sendError) throw sendError;

  onProgress("Waiting for the device to join your network…");
  let status = "";
  const polled = [];
  const deadline = Date.now() + 25000;
  while (Date.now() < deadline && !["1", "2"].includes(status)) {
    await sleep(1000);
    const doc = await soapCall(device.baseUrl, "WiFiSetup", "GetNetworkStatus");
    status = xmlText(doc, "NetworkStatus");
    polled.push(status);
  }
  for (let i = 0; i < 3 && status === "3"; i++) {
    await sleep(1000);
    const doc = await soapCall(device.baseUrl, "WiFiSetup", "GetNetworkStatus");
    status = xmlText(doc, "NetworkStatus");
    polled.push(status);
  }

  let closeStatus;
  try {
    const doc = await soapCall(device.baseUrl, "WiFiSetup", "CloseSetup");
    closeStatus = xmlText(doc, "status") || "(no status in response)";
  } catch (error) {
    closeStatus = `failed: ${error.message}`;
  }

  // Without this, the device can report a successful join but never fully
  // commit it or leave setup mode — it "accepts" the credentials but the
  // connection doesn't stick.
  let setupDoneStatus = "(not attempted — status/close didn't indicate success)";
  if (status === "1" && closeStatus === "success") {
    try {
      await soapCall(device.baseUrl, "basicevent", "SetSetupDoneStatus");
      setupDoneStatus = "sent";
    } catch (error) {
      setupDoneStatus = `failed: ${error.message}`;
    }
  }

  return {
    status,
    closeStatus,
    label: NETWORK_STATUS_LABELS[status] || `unrecognized status code "${status}"`,
    detail:
      `ssid: ${ssid}\nauth: ${auth}\nencryption: ${ap.encryption}\nchannel: ${ap.channel}\n`
      + `GetNetworkStatus poll sequence: ${polled.join(" → ") || "(no reply)"}\n`
      + `CloseSetup status: ${closeStatus}\n`
      + `SetSetupDoneStatus: ${setupDoneStatus}`,
  };
}
