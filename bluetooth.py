"""
bluetooth.py - Finds, pairs, connects and disconnects Bluetooth boxes.

How it works, in short:
  Linux manages Bluetooth with a background service called "BlueZ".
  BlueZ comes with a command line tool called "bluetoothctl". Everything you
  can click in this website is turned into a bluetoothctl command, exactly as
  if you typed it into a terminal yourself, for example:

      bluetoothctl connect AA:BB:CC:DD:EE:FF

  Some words you will see here:
    MAC address - the unique "serial number" of a Bluetooth device,
                  six pairs of characters like AA:BB:CC:DD:EE:FF
    scan        - look around for Bluetooth devices nearby
    pair        - introduce the Pi and a box to each other ONCE (like
                  exchanging phone numbers). Afterwards the box is "known".
    trust       - allow the box to reconnect without asking again
    connect     - actually start using a known box (every time you need it)
    forget      - delete a known box again (also called "remove" / "unpair")

  Where are the paired boxes saved?
    Not in this container - BlueZ on the Raspberry Pi itself remembers them
    (in /var/lib/bluetooth). So updating or deleting the RadioBlue container
    never makes the Pi forget your boxes.
"""

import re
import subprocess

import config

# A valid MAC address: 6 groups of 2 hexadecimal characters, separated by ":".
# We check every address before using it, so nobody can sneak other text
# into the bluetoothctl command.
_MAC_PATTERN = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")

# bluetoothctl prints coloured text using invisible "ANSI escape codes".
# This pattern finds them so we can remove them.
_COLOR_CODES = re.compile(r"\x1b\[[0-9;]*m")

# The kinds of devices ("Icon" in bluetoothctl) that can play sound.
_AUDIO_ICONS = {"audio-card", "audio-headset", "audio-headphones", "audio-speakers"}


class BluetoothError(Exception):
    """Raised when a Bluetooth action fails. The message is shown on the website."""


# ----------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------

def check_mac(mac):
    """Return the MAC address in upper case, or raise BluetoothError if it is not valid."""
    mac = (mac or "").strip().upper()
    if not _MAC_PATTERN.match(mac):
        raise BluetoothError(f"'{mac}' is not a valid Bluetooth address.")
    return mac


def _run(*args, timeout=10):
    """Run "bluetoothctl <args>" and return everything it printed (colours removed)."""
    try:
        result = subprocess.run(
            ["bluetoothctl", *args],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise BluetoothError("Bluetooth did not answer in time. Is the box switched on and close by?")
    except OSError as error:
        raise BluetoothError(f"Could not run bluetoothctl: {error}")
    output = _COLOR_CODES.sub("", result.stdout + result.stderr)
    # Inside Docker, bluetoothctl prints this harmless warning (it can't open a
    # low-level kernel interface it doesn't need for our commands). Hide it.
    return output.replace("Unable to open mgmt_socket\n", "")


def _parse_device_list(text):
    """Turn lines like "Device AA:BB:CC:DD:EE:FF My Speaker" into a dict
    {mac: name}."""
    devices = {}
    for line in text.splitlines():
        match = re.search(r"Device (([0-9A-F]{2}:){5}[0-9A-F]{2}) ?(.*)", line)
        if match:
            devices[match.group(1)] = match.group(3).strip()
    return devices


def _info(mac):
    """Return the details bluetoothctl knows about one device as a dict,
    e.g. {"Name": "My Speaker", "Connected": "yes", "Icon": "audio-card"}."""
    details = {}
    for line in _run("info", mac).splitlines():
        if ":" in line and line.startswith(("\t", " ")):
            key, _, value = line.strip().partition(": ")
            details.setdefault(key, value)   # keep the first value of each key
    return details


def _looks_like_mac(name):
    """Devices without a real name show their address as name, e.g. "12-34-56-78-9A-BC"."""
    return bool(re.fullmatch(r"([0-9A-F]{2}[-:]){5}[0-9A-F]{2}", name.upper()))


# ----------------------------------------------------------------------
# Public functions - these are called by the website (app.py)
# ----------------------------------------------------------------------

def list_known():
    """Return all known (= paired) devices, each with its name and whether it
    is connected right now."""
    devices = []
    for mac, name in _parse_device_list(_run("devices", "Paired")).items():
        details = _info(mac)
        devices.append({
            "mac": mac,
            "name": details.get("Alias") or name,
            "connected": details.get("Connected") == "yes",
            "is_audio": details.get("Icon") in _AUDIO_ICONS,
        })
    devices.sort(key=lambda device: device["name"].lower())
    return devices


def connected_device():
    """Return the first connected known device, or None if nothing is connected."""
    for device in list_known():
        if device["connected"]:
            return device
    return None


def scan(seconds=None):
    """Look for NEW (not yet paired) devices nearby for a few seconds.

    Returns a list where audio devices (speakers, headphones) come first.
    Devices that do not tell their name are left out to keep the list short.
    """
    seconds = seconds or config.SCAN_SECONDS
    # "--timeout N" makes bluetoothctl search for N seconds and then stop.
    _run("--timeout", str(seconds), "scan", "on", timeout=seconds + 10)

    known = set(_parse_device_list(_run("devices", "Paired")))
    found = []
    for mac, name in _parse_device_list(_run("devices")).items():
        if mac in known or not name or _looks_like_mac(name):
            continue
        details = _info(mac)
        found.append({
            "mac": mac,
            "name": name,
            "is_audio": details.get("Icon") in _AUDIO_ICONS,
        })
    # Audio devices first, then alphabetical.
    found.sort(key=lambda device: (not device["is_audio"], device["name"].lower()))
    return found


def pair(mac):
    """Pair a NEW box, trust it and connect to it - all in one go.

    The box must be in "pairing mode" (usually: hold the Bluetooth button
    until the light flashes quickly).
    """
    mac = check_mac(mac)
    # BlueZ forgets devices found by a scan after about 30 seconds. If that
    # happened, quickly search again so it can see the box.
    if "not available" in _run("info", mac):
        _run("--timeout", "8", "scan", "on", timeout=20)

    output = _run("pair", mac, timeout=config.CONNECT_TIMEOUT_SECONDS)
    if "Pairing successful" not in output and "AlreadyExists" not in output:
        raise BluetoothError(
            "Pairing failed. Put the box into pairing mode (light flashing) and try again. "
            f"Details: {_last_line(output)}"
        )
    _run("trust", mac)
    connect(mac)


def connect(mac):
    """Connect to a box that is already known (paired)."""
    mac = check_mac(mac)
    output = _run("connect", mac, timeout=config.CONNECT_TIMEOUT_SECONDS)
    if "Connection successful" not in output and _info(mac).get("Connected") != "yes":
        raise BluetoothError(
            "Could not connect. Is the box switched on and not connected to another device? "
            f"Details: {_last_line(output)}"
        )


def disconnect(mac):
    """Disconnect a box (it stays known, you can connect again later)."""
    mac = check_mac(mac)
    _run("disconnect", mac)


def forget(mac):
    """Forget a known box completely. To use it again you have to pair it again."""
    mac = check_mac(mac)
    output = _run("remove", mac)
    if "Device has been removed" not in output and "not available" not in output:
        raise BluetoothError(f"Could not forget the box. Details: {_last_line(output)}")


def _last_line(text):
    """The last non-empty line of a command's output - usually the error message."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else "no output"
