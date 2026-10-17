/*
  app.js - What happens when you click something on the RadioBlue page.

  The page never reloads. Instead, this script sends small background
  requests ("fetch") to the Python server (app.py), e.g.
      POST /api/radio/play   {"station": "bayern1"}
  and then updates the page with the answer.

  Every few seconds it also asks the server for the current status, so the
  page stays up to date even if someone else changed something.
*/

// How often (in milliseconds) the page asks for the current status.
const STATUS_INTERVAL_MS = 4000;

// The station that is selected on the page (not necessarily playing).
let selectedStation = null;

// The station list as last received from the server (to notice changes).
let stations = [];

// True while the user is dragging the volume slider, so the status update
// does not make the slider jump back.
let draggingVolume = false;

// ---------------------------------------------------------------------
// Talking to the server
// ---------------------------------------------------------------------

/**
 * Send a request to the server and return its answer as an object.
 * path: e.g. "/api/radio/stop"   body: data to send (only for POST)
 * If the server reports an error, it is shown at the top of the page.
 */
async function api(path, body) {
  const options = body === undefined
    ? { method: "GET" }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  try {
    const response = await fetch(path, options);
    const data = await response.json();
    if (!data.ok) {
      showMessage(data.error || "Something went wrong.", true);
    }
    return data;
  } catch (err) {
    showMessage("Cannot reach the RadioBlue server. Is it running?", true);
    return { ok: false };
  }
}

/** Show a message at the top of the page. isError = red text. */
function showMessage(text, isError = false) {
  const box = document.getElementById("message");
  box.textContent = text;
  box.classList.toggle("error", isError);
  box.hidden = false;
  clearTimeout(showMessage.timer);
  showMessage.timer = setTimeout(() => { box.hidden = true; }, 8000);
}

/**
 * Disable a button while its action runs (so it can't be clicked twice)
 * and show a temporary label like "Connecting…".
 */
async function whileBusy(button, busyLabel, action) {
  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = busyLabel;
  try {
    return await action();
  } finally {
    button.disabled = false;
    button.textContent = originalLabel;
  }
}

// ---------------------------------------------------------------------
// Radio
// ---------------------------------------------------------------------

/** Mark one station button as selected. */
function selectStation(stationId) {
  selectedStation = stationId;
  document.querySelectorAll(".station").forEach((button) => {
    button.classList.toggle("selected", button.dataset.station === stationId);
  });
}

/**
 * Show the station buttons (and the editor list, if it is open).
 * Only rebuilds when the list really changed, so nothing flickers.
 */
function showStations(newStations, preferred) {
  if (JSON.stringify(newStations) === JSON.stringify(stations)) return;
  stations = newStations;

  const ids = stations.map((station) => station.id);
  if (!ids.includes(selectedStation)) {
    selectedStation = ids.includes(preferred) ? preferred : ids[0] ?? null;
  }

  const box = document.getElementById("stations");
  box.replaceChildren();
  if (stations.length === 0) {
    const empty = document.createElement("p");
    empty.className = "hint";
    empty.textContent = "No stations yet – press “Edit stations” to add one.";
    box.appendChild(empty);
  }
  for (const station of stations) {
    const button = document.createElement("button");
    button.className = "station";
    button.dataset.station = station.id;
    button.textContent = station.name;
    // Clicking a station selects it. If the radio is already playing, it
    // switches to the new station straight away.
    button.addEventListener("click", async () => {
      selectStation(station.id);
      if (document.getElementById("now-playing").classList.contains("on")) {
        const data = await api("/api/radio/play", { station: selectedStation });
        if (data.ok) showRadio(data.radio);
      }
    });
    box.appendChild(button);
  }
  selectStation(selectedStation);
  document.getElementById("play").disabled = stations.length === 0;
  showStationEditor();
}

document.getElementById("play").addEventListener("click", async (event) => {
  await whileBusy(event.currentTarget, "Starting…", async () => {
    const data = await api("/api/radio/play", { station: selectedStation });
    if (data.ok) showRadio(data.radio);
  });
});

document.getElementById("stop").addEventListener("click", async () => {
  const data = await api("/api/radio/stop", {});
  if (data.ok) showRadio(data.radio);
});

const volumeSlider = document.getElementById("volume");
volumeSlider.addEventListener("pointerdown", () => { draggingVolume = true; });
volumeSlider.addEventListener("input", () => {
  document.getElementById("volume-value").textContent = `${volumeSlider.value} %`;
});
// "change" fires when you let go of the slider -> then we tell the server.
volumeSlider.addEventListener("change", async () => {
  draggingVolume = false;
  await api("/api/volume", { percent: Number(volumeSlider.value) });
});

/** Update the radio part of the page with the status from the server. */
function showRadio(radio) {
  const line = document.getElementById("now-playing");
  if (radio.playing) {
    const song = radio.song ? ` – ${radio.song}` : "";
    line.textContent = `♪ Playing ${radio.station.name}${song}`;
    line.classList.add("on");
    selectStation(radio.station.id);
  } else {
    line.textContent = "Stopped";
    line.classList.remove("on");
  }
  if (!draggingVolume) {
    volumeSlider.value = radio.volume;
    document.getElementById("volume-value").textContent = `${radio.volume} %`;
  }
}

// ---------------------------------------------------------------------
// Editing the station list
// ---------------------------------------------------------------------

const editor = document.getElementById("station-editor");
const editButton = document.getElementById("edit-stations");

function toggleEditor(open) {
  editor.hidden = !open;
  editButton.setAttribute("aria-expanded", String(open));
  editButton.textContent = open ? "✎ Close editor" : "✎ Edit stations";
  if (open) showStationEditor(true);
}
editButton.addEventListener("click", () => toggleEditor(editor.hidden));
document.getElementById("close-editor").addEventListener("click", () => toggleEditor(false));

/** Send a station change to the server and show the new list. */
async function changeStations(path, body, doneMessage) {
  const data = await api(path, body);
  if (data.ok) {
    showStations(data.stations, data.selected);
    showStationEditor(true);
    if (doneMessage) showMessage(doneMessage);
  }
  return data;
}

/**
 * Fill the editor: one row per station with name + address fields and
 * Save / ↑ / ↓ / Delete buttons. force = rebuild even if the user is typing.
 */
function showStationEditor(force = false) {
  if (editor.hidden) return;
  const list = document.getElementById("station-list");
  // Don't throw away what the user is typing because of a background update.
  if (!force && (list.contains(document.activeElement) || list.querySelector("button:disabled"))) return;
  list.replaceChildren();

  stations.forEach((station, index) => {
    const row = document.createElement("li");

    const name = document.createElement("input");
    name.value = station.name;
    name.maxLength = 60;
    name.setAttribute("aria-label", "Station name");
    const url = document.createElement("input");
    url.type = "url";
    url.value = station.url;
    url.setAttribute("aria-label", "Stream address");
    const fields = document.createElement("div");
    fields.className = "fields";
    fields.append(name, url);
    row.appendChild(fields);

    const actions = document.createElement("div");
    actions.className = "actions";
    const addButton = (label, busyLabel, className, title, onClick, disabled = false) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "small " + className;
      button.textContent = label;
      button.title = title;
      button.disabled = disabled;
      button.addEventListener("click", () => whileBusy(button, busyLabel, onClick));
      actions.appendChild(button);
    };
    addButton("Save", "Saving…", "primary", "Save name and address", () =>
      changeStations("/api/stations/update", { id: station.id, name: name.value, url: url.value }, `Saved ${name.value.trim()}.`));
    addButton("↑", "…", "", "Move up", () =>
      changeStations("/api/stations/move", { id: station.id, direction: "up" }), index === 0);
    addButton("↓", "…", "", "Move down", () =>
      changeStations("/api/stations/move", { id: station.id, direction: "down" }), index === stations.length - 1);
    addButton("Delete", "Deleting…", "danger", "Delete this station", () => {
      if (confirm(`Delete the station "${station.name}"?`)) {
        return changeStations("/api/stations/delete", { id: station.id }, `Deleted ${station.name}.`);
      }
    });
    row.appendChild(actions);
    list.appendChild(row);
  });
}

document.getElementById("add-station").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector("button[type=submit]");
  await whileBusy(button, "Adding…", async () => {
    const data = await changeStations("/api/stations/add",
      { name: form.elements.name.value, url: form.elements.url.value },
      `Added ${form.elements.name.value.trim()}.`);
    if (data.ok) form.reset();
  });
});

document.getElementById("restore-defaults").addEventListener("click", async (event) => {
  if (!confirm("Replace ALL your stations with the three default stations?")) return;
  await whileBusy(event.currentTarget, "Restoring…", () =>
    changeStations("/api/stations/restore-defaults", {}, "Default stations restored."));
});

// ---------------------------------------------------------------------
// Bluetooth
// ---------------------------------------------------------------------

/**
 * Build one row of a device list.
 * We create the elements one by one and use "textContent" (never innerHTML),
 * so a box with a strange name can never break or hijack the page.
 */
function deviceRow(device, buttons) {
  const row = document.createElement("li");

  const name = document.createElement("span");
  name.className = "name";
  name.textContent = (device.is_audio ? "🔊 " : "") + device.name;
  const mac = document.createElement("span");
  mac.className = "mac";
  mac.textContent = device.mac;
  name.appendChild(mac);
  row.appendChild(name);

  if (device.connected !== undefined) {
    const state = document.createElement("span");
    state.className = "state" + (device.connected ? " on" : "");
    state.textContent = device.connected ? "Connected" : "Not connected";
    row.appendChild(state);
  }

  for (const { label, busyLabel, className, onClick } of buttons) {
    const button = document.createElement("button");
    button.className = "small " + (className || "");
    button.textContent = label;
    button.addEventListener("click", () => whileBusy(button, busyLabel, onClick));
    row.appendChild(button);
  }
  return row;
}

/** Fill the "My Bluetooth boxes" list. */
function showKnownDevices(devices) {
  const list = document.getElementById("known-devices");
  // Don't rebuild the list while a button in it is busy (would reset it).
  if (list.querySelector("button:disabled")) return;
  list.replaceChildren();

  if (devices.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "No boxes known yet – add one below.";
    list.appendChild(empty);
    return;
  }

  for (const device of devices) {
    const buttons = device.connected
      ? [{ label: "Disconnect", busyLabel: "Disconnecting…", onClick: () => bluetoothAction("disconnect", device) }]
      : [{ label: "Connect", busyLabel: "Connecting…", className: "primary", onClick: () => bluetoothAction("connect", device) }];
    buttons.push({
      label: "Forget", busyLabel: "Forgetting…", className: "danger",
      onClick: () => {
        if (confirm(`Forget "${device.name}"? You will have to pair it again to use it.`)) {
          return bluetoothAction("forget", device);
        }
      },
    });
    list.appendChild(deviceRow(device, buttons));
  }
}

/** Run connect / disconnect / forget / pair for one device, then refresh. */
async function bluetoothAction(action, device) {
  const data = await api(`/api/bluetooth/${action}`, { mac: device.mac });
  if (data.ok) {
    const done = { connect: "Connected to", disconnect: "Disconnected from", forget: "Forgot", pair: "Paired and connected" };
    showMessage(`${done[action]} ${device.name}.`);
    if (action === "pair") document.getElementById("new-devices").replaceChildren();
  }
  await refreshStatus();
}

document.getElementById("scan").addEventListener("click", async (event) => {
  const list = document.getElementById("new-devices");
  await whileBusy(event.currentTarget, "Searching… (about 10 s)", async () => {
    list.replaceChildren();
    const data = await api("/api/bluetooth/scan", {});
    if (!data.ok) return;
    if (data.devices.length === 0) {
      const empty = document.createElement("li");
      empty.className = "empty";
      empty.textContent = "Nothing found. Is the box in pairing mode? Try again.";
      list.appendChild(empty);
      return;
    }
    for (const device of data.devices) {
      list.appendChild(deviceRow(device, [{
        label: "Pair & connect", busyLabel: "Pairing…", className: "primary",
        onClick: () => bluetoothAction("pair", device),
      }]));
    }
  });
});

// ---------------------------------------------------------------------
// Keep the page up to date
// ---------------------------------------------------------------------

async function refreshStatus() {
  const data = await api("/api/status");
  if (data.ok) {
    showStations(data.stations);
    showRadio(data.radio);
    showKnownDevices(data.known_devices);
  }
}

// First load: get the stations (with the last played one pre-selected),
// then keep everything up to date.
api("/api/stations").then((data) => {
  if (data.ok) showStations(data.stations, data.selected);
  refreshStatus();
  setInterval(refreshStatus, STATUS_INTERVAL_MS);
});
