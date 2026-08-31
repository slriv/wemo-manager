// Dashboard UI.

function imageCell(row) {
  const image = document.createElement("span");
  image.className = "device-image";
  image.title = row.model_name ?? "";
  image.textContent = (row.model_name || row.model || "?").charAt(0).toUpperCase();
  return image;
}

function nameCell(row) {
  const link = document.createElement("a");
  link.href = `/devices/${row.id}`;
  link.textContent = row.name;
  return link;
}

const MODEL_ABBREVIATIONS = {
  LightSwitch: "Switch",
  Humidifier: "Humid.",
  CoffeeMaker: "Coffee",
  CrockPot: "Crock",
};

function modelCell(row) {
  return MODEL_ABBREVIATIONS[row.model_name] || row.model_name || "";
}

function relativeTime(isoString) {
  if (!isoString) return "—";
  // Stored timestamps are UTC without a zone suffix.
  const diffMs = Date.now() - new Date(`${isoString}Z`).getTime();
  const diffSec = Math.round(diffMs / 1000);
  if (diffSec < 5) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHour = Math.round(diffMin / 60);
  if (diffHour < 24) return `${diffHour}h ago`;
  return `${Math.round(diffHour / 24)}d ago`;
}

function lastSeenCell(row) {
  return relativeTime(row.last_seen_at);
}

function isDimmer(row) {
  return (row.device_type || "").includes("Dimmer");
}

async function setDeviceState(deviceId, body) {
  try {
    const res = await fetch(`/api/devices/${deviceId}/state`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) console.error("Failed to set device state", await res.text());
  } catch (err) {
    console.error("Failed to set device state", err);
  } finally {
    refreshTable();
  }
}

function controlCell(row) {
  const isOn = !!row.binary_state;
  const disabled = row.status !== "online";

  const wrapper = document.createElement("div");
  wrapper.className = "control-cell";

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = `toggle-switch ${isOn ? "toggle-on" : "toggle-off"}`;
  toggle.disabled = disabled;
  toggle.title = isOn ? "On — click to turn off" : "Off — click to turn on";
  toggle.addEventListener("click", () => {
    toggle.disabled = true;
    setDeviceState(row.id, { on: !isOn });
  });
  wrapper.appendChild(toggle);

  if (isDimmer(row)) {
    const level = row.brightness ?? 1;
    const brightnessControl = document.createElement("div");
    brightnessControl.className = "brightness-control";

    const label = document.createElement("span");
    label.className = "brightness-label";
    label.textContent = `${level}%`;

    const slider = document.createElement("input");
    slider.type = "range";
    slider.min = 1;
    slider.max = 100;
    slider.value = level;
    slider.className = "brightness-slider";
    slider.disabled = disabled;
    slider.addEventListener("input", () => {
      label.textContent = `${slider.value}%`;
    });
    slider.addEventListener("change", () => {
      setDeviceState(row.id, { level: parseInt(slider.value, 10) });
    });

    brightnessControl.append(slider, label);
    wrapper.appendChild(brightnessControl);
  }

  return wrapper;
}

// Mobile device tiles.

function tileToggle(row, button) {
  const isOn = !!row.binary_state;
  button.disabled = true;
  setDeviceState(row.id, { on: !isOn });
}

function buildTile(row) {
  const online = row.status === "online";
  const isOn = !!row.binary_state;
  const dimmer = isDimmer(row);
  const level = row.brightness ?? 1;

  const tile = document.createElement("div");
  tile.className = `device-tile ${dimmer ? "tile-dimmer" : ""} ${isOn ? "tile-on" : ""} ${online ? "" : "tile-offline"}`.trim();
  if (dimmer) tile.style.setProperty("--brightness-fill", `${isOn ? level : 0}%`);

  const main = document.createElement("div");
  main.className = "tile-main";

  const top = document.createElement("div");
  top.className = "tile-top";
  const dot = document.createElement("span");
  dot.className = `status-dot status-${row.status}`;
  top.appendChild(dot);
  top.append(MODEL_ABBREVIATIONS[row.model_name] || row.model_name || row.model || "");

  const name = document.createElement("div");
  name.className = "tile-name";
  name.textContent = row.name;

  const state = document.createElement("div");
  state.className = "tile-state";
  if (!online) state.textContent = "Offline";
  else if (dimmer && isOn) state.textContent = `On · ${level}%`;
  else state.textContent = isOn ? "On" : "Off";

  main.append(top, name, state);
  if (dimmer) {
    const slider = document.createElement("input");
    slider.type = "range";
    slider.className = "tile-brightness";
    slider.min = 1;
    slider.max = 100;
    slider.value = level;
    slider.disabled = !online;
    slider.setAttribute("aria-label", `Brightness for ${row.name}`);
    slider.addEventListener("input", () => {
      const brightness = slider.value;
      state.textContent = `On · ${brightness}%`;
      tile.style.setProperty("--brightness-fill", `${brightness}%`);
    });
    slider.addEventListener("change", () => {
      setDeviceState(row.id, { level: parseInt(slider.value, 10) });
    });
    main.appendChild(slider);
  }

  const toggleRow = document.createElement("div");
  toggleRow.className = "tile-toggle-row";
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = `toggle-switch ${isOn ? "toggle-on" : "toggle-off"}`;
  toggle.disabled = !online;
  toggle.title = isOn ? "On — click to turn off" : "Off — click to turn on";
  toggle.addEventListener("click", () => tileToggle(row, toggle));
  toggleRow.appendChild(toggle);

  const details = document.createElement("a");
  details.className = "tile-details";
  details.href = `/devices/${row.id}`;
  details.textContent = "Details";

  tile.append(main, toggleRow, details);
  return tile;
}

function renderGrid(rows) {
  const grid = document.getElementById("device-grid");
  if (!grid) return;
  grid.replaceChildren();
  if (rows.length === 0) {
    const empty = document.createElement("p");
    empty.className = "grid-placeholder";
    empty.textContent = EMPTY_MESSAGE;
    grid.appendChild(empty);
    return;
  }
  rows.forEach((row) => grid.appendChild(buildTile(row)));
}

const EMPTY_MESSAGE = "No known devices yet — use Detect to find some.";
const SORT_PREFERENCE_KEY = "wemo-manager:sort";
let [sortField, sortDirection] = loadSortPreference();

let devices = [];
let visibleDevices = [];

const COLUMNS = [
  { field: "model", title: "", cell: imageCell, sortable: false },
  { field: "name", title: "Name", cell: nameCell, required: true },
  { field: "model_name", title: "Model", cell: modelCell },
  { field: "binary_state", title: "Control", cell: controlCell, required: true },
  { field: "last_seen_at", title: "Last Seen", cell: lastSeenCell },
  { field: "host", title: "Host", cell: (row) => row.host },
];

function loadSortPreference() {
  try {
    const [field, direction] = (localStorage.getItem(SORT_PREFERENCE_KEY) || "name:asc").split(":");
    return direction === "asc" || direction === "desc" ? [field, direction] : ["name", "asc"];
  } catch {
    return ["name", "asc"];
  }
}

function saveSortPreference() {
  try {
    localStorage.setItem(SORT_PREFERENCE_KEY, `${sortField}:${sortDirection}`);
  } catch {
    // Ignore unavailable storage.
  }
}

function sortDevices(rows) {
  return rows.slice().sort((a, b) => {
    const first = String(a[sortField] ?? "");
    const second = String(b[sortField] ?? "");
    const comparison = first.localeCompare(second, undefined, { numeric: true });
    return sortDirection === "asc" ? comparison : -comparison;
  });
}

function visibleColumns() {
  return COLUMNS.filter(
    (column) => !column.title || column.required || columnVisibility[column.field] !== false
  );
}

function sortBy(field) {
  if (field === sortField) sortDirection = sortDirection === "asc" ? "desc" : "asc";
  else [sortField, sortDirection] = [field, "asc"];
  saveSortPreference();
  const select = document.getElementById("device-sort");
  if (select) select.value = `${sortField}:${sortDirection}`;
  render();
}

function headerCell(column) {
  const th = document.createElement("th");
  if (column.sortable === false) {
    th.textContent = column.title;
    return th;
  }
  const button = document.createElement("button");
  button.type = "button";
  button.className = "column-sort";
  button.textContent = column.title;
  if (column.field === sortField) {
    button.classList.add("sorted");
    button.append(sortDirection === "asc" ? " \u25B2" : " \u25BC");
  }
  button.addEventListener("click", () => sortBy(column.field));
  th.appendChild(button);
  return th;
}

function renderTable(rows) {
  const container = document.getElementById("device-table");
  if (!container) return;
  container.replaceChildren();
  if (rows.length === 0) {
    const empty = document.createElement("p");
    empty.className = "table-placeholder";
    empty.textContent = EMPTY_MESSAGE;
    container.appendChild(empty);
    return;
  }

  const columns = visibleColumns();
  const table = document.createElement("table");
  table.className = "device-table";

  const head = document.createElement("tr");
  columns.forEach((column) => head.appendChild(headerCell(column)));
  const thead = document.createElement("thead");
  thead.appendChild(head);

  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    if (row.status !== "online") tr.classList.add("row-offline");
    tr.addEventListener("click", (event) => {
      if (event.target.closest("a, button, input")) return;
      window.location.href = `/devices/${row.id}`;
    });
    columns.forEach((column) => {
      const td = document.createElement("td");
      const content = column.cell(row);
      if (content instanceof Node) td.appendChild(content);
      else td.textContent = content ?? "";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  table.append(thead, tbody);
  container.appendChild(table);
}

function renderDeviceSummary() {
  const summary = document.getElementById("device-summary");
  if (!summary) return;
  const shown = visibleDevices.length;
  if (!shown) {
    summary.textContent = "";
    return;
  }
  const onlineDevices = visibleDevices.filter((device) => device.status === "online");
  const on = onlineDevices.filter((device) => !!device.binary_state).length;
  const off = onlineDevices.length - on;
  const offline = shown - onlineDevices.length;
  const count = shown === devices.length ? `${shown} device${shown === 1 ? "" : "s"}` : `${shown} of ${devices.length} devices`;
  summary.textContent = `${count} — ${on} on, ${off} off, ${offline} offline`;
}

function render() {
  visibleDevices = sortDevices(devices.filter(matchesDeviceFilters));
  renderTable(visibleDevices);
  renderGrid(visibleDevices);
  renderDeviceSummary();
}

async function loadDevices() {
  const response = await fetch("/api/devices");
  if (!response.ok) return;
  devices = await response.json();
  initNetworkFilter();
  render();
}

async function refreshTable() {
  // Preserve scroll position across the row replacement.
  const scrollX = window.scrollX;
  const scrollY = window.scrollY;
  try {
    await loadDevices();
  } finally {
    requestAnimationFrame(() => window.scrollTo(scrollX, scrollY));
  }
}

// Dropdown menus.

function wireDropdownToggle(toggleId, menuId) {
  const button = document.getElementById(toggleId);
  const menu = document.getElementById(menuId);
  if (!button || !menu) return;
  button.addEventListener("click", () => {
    const opening = menu.hidden;
    document.querySelectorAll(".dropdown-menu").forEach((m) => (m.hidden = true));
    menu.hidden = !opening;
  });
}

document.addEventListener("click", (event) => {
  if (event.target.closest(".dropdown")) return;
  document.querySelectorAll(".dropdown-menu").forEach((m) => (m.hidden = true));
});

// Column preferences.

const COLUMN_VISIBILITY_KEY = "wemo-manager:column-visibility";
let columnVisibility = loadColumnVisibility();

function loadColumnVisibility() {
  try {
    return JSON.parse(localStorage.getItem(COLUMN_VISIBILITY_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveColumnVisibility() {
  try {
    localStorage.setItem(COLUMN_VISIBILITY_KEY, JSON.stringify(columnVisibility));
  } catch {
    // Ignore unavailable storage.
  }
}

function initColumnPicker() {
  const menu = document.getElementById("column-picker-menu");
  if (!menu) return;

  menu.replaceChildren();
  COLUMNS.filter((column) => column.title && !column.required).forEach((column) => {
    const label = document.createElement("label");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = columnVisibility[column.field] !== false;
    checkbox.addEventListener("change", () => {
      columnVisibility[column.field] = checkbox.checked;
      saveColumnVisibility();
      render();
    });
    label.appendChild(checkbox);
    label.append(` ${column.title}`);
    menu.appendChild(label);
  });

  wireDropdownToggle("column-picker-toggle", "column-picker-menu");
}

// Search, sorting, and network filtering.

const NETWORK_FILTER_KEY = "wemo-manager:network-filter";
let networkFilter = null; // "all" or a /24 prefix.
let searchQuery = "";

function matchesDeviceFilters(data) {
  const matchesNetwork =
    networkFilter === "all" || !networkFilter || subnetOf(data.host) === networkFilter;
  const searchable = [data.name, data.model_name, data.model, data.host]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase();
  return matchesNetwork && searchable.includes(searchQuery);
}

function subnetOf(host) {
  const parts = (host || "").split(".");
  return parts.length === 4 ? parts.slice(0, 3).join(".") : null;
}

function networkLabel(subnet) {
  return subnet === "all" ? "All networks" : `${subnet}.x`;
}

function knownSubnets() {
  return [...new Set(devices.map((device) => subnetOf(device.host)).filter(Boolean))].sort();
}

function initListControls() {
  const search = document.getElementById("device-search");
  const sort = document.getElementById("device-sort");
  sort.value = `${sortField}:${sortDirection}`;
  search.addEventListener("input", () => {
    searchQuery = search.value.trim().toLocaleLowerCase();
    render();
  });
  sort.addEventListener("change", () => {
    [sortField, sortDirection] = sort.value.split(":");
    saveSortPreference();
    render();
  });
}

function renderNetworkMenu() {
  const menu = document.getElementById("network-filter-menu");
  const button = document.getElementById("network-filter-toggle");
  if (!menu || !button) return;

  menu.replaceChildren();
  ["all", ...knownSubnets()].forEach((subnet) => {
    const item = document.createElement("button");
    item.type = "button";
    item.textContent = networkLabel(subnet);
    item.className = subnet === networkFilter ? "dropdown-option selected" : "dropdown-option";
    item.addEventListener("click", () => {
      networkFilter = subnet;
      saveNetworkFilterChoice(subnet);
      renderNetworkMenu();
      render();
      menu.hidden = true;
    });
    menu.appendChild(item);
  });
  button.textContent = `${networkLabel(networkFilter)} ▾`;
}

function saveNetworkFilterChoice(subnet) {
  try {
    localStorage.setItem(NETWORK_FILTER_KEY, subnet);
  } catch {
    // Ignore unavailable storage.
  }
}

function loadNetworkFilterChoice() {
  try {
    return localStorage.getItem(NETWORK_FILTER_KEY);
  } catch {
    return null;
  }
}

function initNetworkFilter() {
  if (!document.getElementById("network-filter-menu")) return;

  const subnets = knownSubnets();

  if (networkFilter === null) {
    const stored = loadNetworkFilterChoice();
    networkFilter =
      (stored && (stored === "all" || subnets.length === 0 || subnets.includes(stored)) && stored)
      || "all";
    saveNetworkFilterChoice(networkFilter);
    wireDropdownToggle("network-filter-toggle", "network-filter-menu");
  }

  if (subnets.length && networkFilter !== "all" && !subnets.includes(networkFilter)) {
    networkFilter = "all";
    saveNetworkFilterChoice(networkFilter);
  }

  renderNetworkMenu();
}

// Live updates.

const connectionStatus = document.getElementById("connection-status");

function setConnectionStatus(live) {
  if (!connectionStatus) return;
  connectionStatus.textContent = live ? "Live" : "Reconnecting…";
  connectionStatus.className = `conn-status ${live ? "conn-live" : "conn-down"}`;
}

// Coalesce update bursts.
let refreshDebounceTimer;
function debouncedRefresh() {
  clearTimeout(refreshDebounceTimer);
  refreshDebounceTimer = setTimeout(refreshTable, 300);
}

function connectDeviceEvents() {
  const source = new EventSource("/api/devices/events");
  source.onopen = () => {
    setConnectionStatus(true);
    debouncedRefresh();
  };
  source.onmessage = () => {
    setConnectionStatus(true);
    debouncedRefresh();
  };
  source.onerror = () => setConnectionStatus(false);
}

// Schedule calendar.

const scheduleDialog = document.getElementById("schedule-editor-dialog");
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const SCHEDULE_COLORS = ["#3ecf6e", "#71b7ff", "#c798f2", "#f0b35c", "#eb7f9a", "#59c4c4"];
let calendarEvents = [];

function scheduleColor(event) {
  let hash = 0;
  for (const character of event.rule_name) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return SCHEDULE_COLORS[hash % SCHEDULE_COLORS.length];
}

function addScheduleWindow(column, event, start, end) {
  if (end <= start) return;
  const window = document.createElement("div");
  window.className = "schedule-window";
  window.style.top = `${Math.round(start / 60) + 36}px`;
  window.style.height = `${Math.max(12, Math.round((end - start) / 60))}px`;
  window.style.setProperty("--schedule-color", scheduleColor(event));
  column.appendChild(window);
}

function addScheduleWindows(columns) {
  calendarEvents.forEach((event) => {
    if (
      event.start_action !== "on"
      || event.end_action !== "off"
      || !Number.isFinite(event.start_seconds)
      || !Number.isFinite(event.end_seconds)
    ) {
      return;
    }
    const columnIndex = event.day - 1;
    if (event.end_seconds > event.start_seconds) {
      addScheduleWindow(columns[columnIndex], event, event.start_seconds, event.end_seconds);
    } else {
      addScheduleWindow(columns[columnIndex], event, event.start_seconds, 86400);
      addScheduleWindow(columns[(columnIndex + 1) % 7], event, 0, event.end_seconds);
    }
  });
}

function layoutCalendarEvents(events) {
  // Offset overlapping cards so each stays clickable.
  let nextTop = 36;
  return events
    .slice()
    .sort((first, second) => first.start_seconds - second.start_seconds)
    .map((event) => {
      const scheduledTop = Math.round(event.start_seconds / 60) + 36;
      const top = Math.max(scheduledTop, nextTop);
      nextTop = top + 28;
      return { ...event, top };
    });
}

function renderCalendar() {
  const calendar = document.getElementById("schedule-calendar");
  calendar.replaceChildren();
  const columns = [];
  for (let day = 1; day <= 7; day += 1) {
    const column = document.createElement("section");
    column.className = "calendar-day";
    const heading = document.createElement("h3");
    heading.textContent = WEEKDAYS[day % 7];
    column.appendChild(heading);
    columns.push(column);
    calendar.appendChild(column);
  }
  addScheduleWindows(columns);
  columns.forEach((column, index) => {
    const day = index + 1;
    layoutCalendarEvents(calendarEvents.filter((event) => event.day === day)).forEach((event) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = `calendar-event ${event.enabled ? "" : "calendar-event-disabled"}`;
      item.textContent = `${event.start} ${event.start_action} · ${event.rule_name}`;
      item.style.top = `${event.top}px`;
      item.style.setProperty("--schedule-color", scheduleColor(event));
      item.title = `${event.start} ${event.start_action} · ${event.rule_name}`;
      item.addEventListener("click", () => showCalendarEvent(event));
      column.appendChild(item);
    });
  });
  focusCalendarOnActivity();
}

function focusCalendarOnActivity() {
  const times = calendarEvents.flatMap((event) => [event.start_seconds, event.end_seconds])
    .filter((time) => Number.isFinite(time));
  if (!times.length) return;
  const midpoint = (Math.min(...times) + Math.max(...times)) / 2;
  const calendar = document.getElementById("schedule-calendar");
  requestAnimationFrame(() => {
    calendar.scrollTop = Math.max(0, midpoint / 60 + 36 - calendar.clientHeight / 2);
  });
}

function showCalendarEvent(event) {
  const detail = document.getElementById("calendar-event-detail");
  detail.hidden = false;
  detail.replaceChildren();
  const title = document.createElement("h3");
  title.textContent = event.rule_name;
  const text = document.createElement("p");
  text.textContent = `${event.day_name}: ${event.start_action} at ${event.start}; ${event.end_action} at ${event.end}. Targets: ${event.targets.join(", ") || "none recorded"}. Cached from ${event.source}.`;
  detail.append(title, text);
}

async function loadScheduleCalendar() {
  const status = document.getElementById("calendar-status");
  const response = await fetch("/api/devices/rules/calendar");
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail ?? response.statusText);
  calendarEvents = data.events;
  status.textContent = data.sources.length
    ? `Cached schedules from ${data.sources.map((source) => source.name).join(", ")}. Times use stored device values. View only.`
    : "No cached schedules yet. Use Refresh rules from devices to save a snapshot.";
  renderCalendar();
}

document.getElementById("open-schedule-editor").addEventListener("click", async () => {
  scheduleDialog.showModal();
  try { await loadScheduleCalendar(); } catch (error) { document.getElementById("calendar-status").textContent = `Error: ${error}`; }
});
document.getElementById("close-schedule-editor").addEventListener("click", () => scheduleDialog.close());
document.getElementById("refresh-schedule-cache").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const status = document.getElementById("calendar-status");
  button.disabled = true;
  button.textContent = "Refreshing…";
  try {
    const response = await fetch("/api/devices/rules/summary");
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail ?? response.statusText);
    await loadScheduleCalendar();
  } catch (error) {
    status.textContent = `Error: ${error}`;
  } finally {
    button.disabled = false;
    button.textContent = "Refresh from devices";
  }
});

// Detection dialog.

const detectDialog = document.getElementById("detect-dialog");
const detectForm = document.getElementById("detect-form");
const detectResults = document.getElementById("detect-results");
const detectTargetInput = document.getElementById("detect-target");

async function openDetectDialog() {
  detectResults.innerHTML = "";
  try {
    const res = await fetch("/api/devices/default-network");
    const data = await res.json();
    detectTargetInput.value = data.network;
  } catch (err) {
    console.error("Failed to fetch default network", err);
  }
  detectDialog.showModal();
}

function renderDetectResults(devices) {
  if (devices.length === 0) {
    detectResults.innerHTML = "<p>No devices found.</p>";
    return;
  }
  const rows = devices
    .map(
      (d) => `
      <tr>
        <td><input type="checkbox" class="detect-pick" value="${d.udn}" checked></td>
        <td>${d.name}</td>
        <td>${d.model_name}</td>
        <td>${d.host}</td>
      </tr>`
    )
    .join("");
  detectResults.innerHTML = `
    <table>
      <thead><tr><th></th><th>Name</th><th>Model</th><th>Host</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <div class="dialog-actions">
      <button type="button" class="secondary" id="detect-cancel-2">Close</button>
      <button type="button" id="detect-commit">Add selected devices</button>
    </div>`;

  document.getElementById("detect-cancel-2").addEventListener("click", () => {
    detectDialog.close();
  });
  document.getElementById("detect-commit").addEventListener("click", async () => {
    const udns = Array.from(document.querySelectorAll(".detect-pick:checked")).map(
      (el) => el.value
    );
    if (udns.length === 0) return;
    await fetch("/api/devices/detect/commit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ udns }),
    });
    detectDialog.close();
    refreshTable();
  });
}

detectForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const target = detectTargetInput.value.trim();
  const timeout = parseFloat(document.getElementById("detect-timeout").value) || 2.0;
  detectResults.innerHTML = "<p>Scanning…</p>";
  try {
    const res = await fetch("/api/devices/detect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target, timeout, persist: false }),
    });
    if (!res.ok) {
      const err = await res.json();
      detectResults.innerHTML = `<p>Error: ${err.detail ?? res.statusText}</p>`;
      return;
    }
    const data = await res.json();
    renderDetectResults(data.devices);
  } catch (err) {
    detectResults.innerHTML = `<p>Error: ${err}</p>`;
  }
});

document.getElementById("detect-button").addEventListener("click", openDetectDialog);
document.getElementById("detect-cancel").addEventListener("click", () => detectDialog.close());

// Saved registration settings.

async function loadSetupSummary() {
  const panel = document.getElementById("setup-summary");
  if (!panel) return;
  let config;
  try {
    const response = await fetch("/api/setup/config");
    if (!response.ok) return;
    config = await response.json();
  } catch {
    return;
  }
  if (!config.wifi_ssid) return;
  document.getElementById("summary-ssid").textContent = config.wifi_ssid;
  panel.hidden = false;
}

document.addEventListener("DOMContentLoaded", () => {
  initColumnPicker();
  initListControls();
  loadDevices();
  connectDeviceEvents();
  loadSetupSummary();
});
