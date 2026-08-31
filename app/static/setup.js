// Setup page UI.

const form = document.getElementById("setup-form");
const ssidInput = document.getElementById("wifi-ssid");
const passwordInput = document.getElementById("wifi-password");
const saveStatus = document.getElementById("save-status");

function renderConfig(config) {
  ssidInput.value = config.wifi_ssid;
  passwordInput.value = config.wifi_password;
  document.getElementById("server-host").textContent = config.server_host || location.hostname;

  document.getElementById("apk-missing").hidden = config.apk_available;
  document.getElementById("apk-available").hidden = !config.apk_available;
}

async function loadConfig() {
  const response = await fetch("/api/setup/config");
  renderConfig(await response.json());
}

document.querySelectorAll("[data-reveal]").forEach((button) => {
  const input = document.getElementById(button.dataset.reveal);
  button.addEventListener("click", () => {
    const revealed = input.type === "text";
    input.type = revealed ? "password" : "text";
    button.textContent = revealed ? "Reveal" : "Hide";
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    wifi_ssid: ssidInput.value,
    wifi_password: passwordInput.value,
  };

  saveStatus.textContent = "Saving…";
  const response = await fetch("/api/setup/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (response.ok) {
    renderConfig(await response.json());
    saveStatus.textContent = "Saved.";
  } else {
    const detail = (await response.json()).detail;
    saveStatus.textContent = `Save failed: ${JSON.stringify(detail)}`;
  }
});

loadConfig();
