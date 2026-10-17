"""
settings.py - Remembers YOUR settings (radio stations, volume, last station).

Where are they saved?
  In one small file, settings.json, in the "data" folder. Inside the container
  that folder is /data. compose.yaml connects it to the folder "data" next to
  compose.yaml on the Raspberry Pi (e.g. ~/docker/radioblue/data/settings.json).

  Because this folder lives OUTSIDE the container, your settings survive
  updates, rebuilds and reboots. Deleting the container does not delete them.

  The file is plain JSON. You can edit it by hand while RadioBlue is stopped,
  but the easiest way is the "Edit stations" button on the web page.

Upgrades:
  The file has a "version" number. When a future version of RadioBlue needs to
  store things differently, _migrate() converts old files automatically, so an
  update never throws your stations away.
"""

import copy
import json
import os
import re
import threading
from contextlib import contextmanager
from urllib.parse import urlparse

import config

# Increase this (and teach _migrate() the new format) when the file layout changes.
SETTINGS_VERSION = 1

SETTINGS_FILE = os.path.join(config.DATA_DIR, "settings.json")

# Limits that keep the file and the web page reasonable.
MAX_STATIONS = 100
MAX_NAME_LENGTH = 60
MAX_URL_LENGTH = 2000

# The stations a fresh installation starts with. Once settings.json exists,
# this list is NOT used any more (except for "Restore default stations").
DEFAULT_STATIONS = [
    {
        "id": "rockantenne-bayern",
        "name": "Rock Antenne Bayern",
        "url": "https://stream.rockantenne.bayern/rockantenne-bayern/stream/mp3",
    },
    {
        "id": "bayern1",
        "name": "Bayern 1",
        "url": "https://dispatcher.rndfnk.com/br/br1/obb/mp3/mid",
    },
    {
        "id": "radiobob",
        "name": "Radio Bob",
        "url": "https://streams.radiobob.de/bob-national/mp3-192/streams.radiobob.de/",
    },
]

DEFAULTS = {
    "version": SETTINGS_VERSION,
    "stations": DEFAULT_STATIONS,
    "last_station": DEFAULT_STATIONS[0]["id"],
    "volume": 70,
}


class SettingsError(Exception):
    """Raised when a change is not allowed. The message is shown on the website."""


# ----------------------------------------------------------------------
# Checking what the user typed
# ----------------------------------------------------------------------

def check_name(name):
    name = " ".join(str(name or "").split())    # trim and collapse spaces
    if not name:
        raise SettingsError("Please enter a name for the station.")
    if len(name) > MAX_NAME_LENGTH:
        raise SettingsError(f"The name is too long (at most {MAX_NAME_LENGTH} characters).")
    return name


def check_url(url):
    """Only allow normal web addresses (http:// or https://). This also makes
    sure nobody can make the player open files or other things on the Pi."""
    url = str(url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise SettingsError("The stream address must start with http:// or https://")
    if len(url) > MAX_URL_LENGTH or any(char.isspace() for char in url):
        raise SettingsError("That does not look like a valid stream address.")
    return url


def _make_id(name, taken):
    """Turn a name like "Radio Bob!" into a short id like "radio-bob" that is
    not used by another station yet."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "station"
    candidate, number = base, 2
    while candidate in taken:
        candidate, number = f"{base}-{number}", number + 1
    return candidate


# ----------------------------------------------------------------------
# The settings store
# ----------------------------------------------------------------------

class Settings:
    """Holds the settings in memory and writes every change to settings.json.

    Only ONE Settings object exists while the website runs (see app.py).
    """

    def __init__(self, path=SETTINGS_FILE):
        self._path = path
        self._lock = threading.Lock()
        self._data = self._load()

    # ------------------------- reading -------------------------

    def stations(self):
        with self._lock:
            return copy.deepcopy(self._data["stations"])

    def find_station(self, station_id):
        for station in self.stations():
            if station["id"] == station_id:
                return station
        return None

    def last_station(self):
        """The station to pre-select on the page (falls back to the first one)."""
        with self._lock:
            ids = [station["id"] for station in self._data["stations"]]
            last = self._data["last_station"]
            return last if last in ids else (ids[0] if ids else None)

    def volume(self):
        with self._lock:
            return self._data["volume"]

    # ------------------------- changing -------------------------

    def add_station(self, name, url):
        name, url = check_name(name), check_url(url)
        with self._change() as data:
            stations = data["stations"]
            if len(stations) >= MAX_STATIONS:
                raise SettingsError(f"You can save at most {MAX_STATIONS} stations.")
            station = {"id": _make_id(name, {s["id"] for s in stations}), "name": name, "url": url}
            stations.append(station)
        return copy.deepcopy(station)

    def update_station(self, station_id, name, url):
        name, url = check_name(name), check_url(url)
        with self._change():
            station = self._get_locked(station_id)
            station["name"], station["url"] = name, url
        return copy.deepcopy(station)

    def delete_station(self, station_id):
        with self._change() as data:
            data["stations"].remove(self._get_locked(station_id))

    def move_station(self, station_id, direction):
        """Move a station one place up (direction -1) or down (+1) in the list."""
        with self._change() as data:
            stations = data["stations"]
            index = stations.index(self._get_locked(station_id))
            target = index + (1 if direction > 0 else -1)
            if 0 <= target < len(stations):
                stations[index], stations[target] = stations[target], stations[index]

    def restore_default_stations(self):
        with self._change() as data:
            data["stations"] = copy.deepcopy(DEFAULT_STATIONS)

    def remember(self, last_station=None, volume=None):
        """Remember the last played station and/or the radio volume."""
        with self._lock:
            changed = False
            if last_station is not None and last_station != self._data["last_station"]:
                self._data["last_station"], changed = last_station, True
            if volume is not None and volume != self._data["volume"]:
                self._data["volume"], changed = volume, True
            if changed:
                try:
                    self._save_locked()
                except SettingsError as error:
                    # Not worth bothering the user about on every click; the
                    # station editor shows the same problem loudly.
                    print(f"[settings] {error}")

    # ------------------------- internal helpers -------------------------

    @contextmanager
    def _change(self):
        """Make a change and save it. If anything goes wrong (e.g. the file
        can't be written), the change is undone, so the page never shows
        stations that were not really saved."""
        with self._lock:
            before = copy.deepcopy(self._data)
            try:
                yield self._data
                self._save_locked()
            except Exception:
                self._data = before
                raise

    def _get_locked(self, station_id):
        for station in self._data["stations"]:
            if station["id"] == station_id:
                return station
        raise SettingsError("This station does not exist (any more). Reload the page.")

    def _load(self):
        """Read settings.json. If it is missing (first start), start with the
        defaults and create it."""
        try:
            with open(self._path, encoding="utf-8") as file:
                data = json.load(file)
        except FileNotFoundError:
            data = copy.deepcopy(DEFAULTS)
            self._data = data
            try:
                self._save_locked()
                print(f"[settings] Created {self._path} with the default stations.")
            except SettingsError as error:
                print(f"[settings] {error}")
            return data
        except (OSError, ValueError) as error:
            # A broken file must never be overwritten silently - the user's
            # stations are in there. Keep a copy, then start with the defaults.
            backup = self._path + ".broken"
            try:
                os.replace(self._path, backup)
            except OSError:
                pass
            print(f"[settings] Could not read {self._path} ({error}). "
                  f"Moved it to {backup} and started with the default settings.")
            return copy.deepcopy(DEFAULTS)
        return _migrate(data)

    def _save_locked(self):
        """Write the settings safely: first to a temporary file, then rename it.
        That way a power cut in the middle never leaves a half-written file."""
        temporary = self._path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(temporary, "w", encoding="utf-8") as file:
                json.dump(self._data, file, indent=2, ensure_ascii=False)
                file.write("\n")
            os.replace(temporary, self._path)
        except OSError as error:
            raise SettingsError(
                f"Could not save the settings to {self._path}: {error.strerror}. "
                "Is the data folder writable by your user? See the README (Troubleshooting)."
            )


def _migrate(data):
    """Bring a settings file from any older version up to the current format.
    Missing values are filled in with defaults; unknown values are kept."""
    if not isinstance(data, dict):
        data = {}
    # (Future format changes go here, e.g. "if data.get('version', 1) < 2: ...")

    saved = data.get("stations")
    if not isinstance(saved, list):
        saved = copy.deepcopy(DEFAULT_STATIONS)
    stations = []
    for station in saved:
        try:
            name, url = check_name(station.get("name")), check_url(station.get("url"))
        except (SettingsError, AttributeError):
            print(f"[settings] Skipping an invalid station in settings.json: {station!r}")
            continue
        station_id = str(station.get("id") or "")
        if not station_id or station_id in {s["id"] for s in stations}:
            station_id = _make_id(name, {s["id"] for s in stations})
        stations.append({**station, "id": station_id, "name": name, "url": url})
    data["stations"] = stations

    try:
        data["volume"] = max(0, min(100, int(data.get("volume", DEFAULTS["volume"]))))
    except (TypeError, ValueError):
        data["volume"] = DEFAULTS["volume"]
    data.setdefault("last_station", stations[0]["id"] if stations else None)
    data["version"] = SETTINGS_VERSION
    return data
