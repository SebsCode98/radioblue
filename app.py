"""
app.py - The web server of RadioBlue. Start here when reading the code.

What this file does:
  1. It shows the web page (templates/index.html) when you open the site.
  2. It offers small "API" addresses (all starting with /api/...). The buttons
     on the web page call these addresses in the background, and this file
     then tells radio.py or bluetooth.py what to do.
  3. It makes sure only devices from your HOME NETWORK can use the site.

It uses "Flask", a popular, beginner-friendly Python library for websites.
"""

import ipaddress

from flask import Flask, abort, jsonify, render_template, request

import bluetooth
import config
from radio import RadioPlayer
from settings import Settings, SettingsError

app = Flask(__name__)

# Your saved settings: stations, volume, last station (see settings.py).
settings = Settings()

# The one and only radio player (see radio.py).
player = RadioPlayer(volume=settings.volume())


# ----------------------------------------------------------------------
# Safety: only allow visitors from the local network
# ----------------------------------------------------------------------

def is_local_address(address):
    """True if an IP address belongs to a private/home network.

    Home networks use special address ranges that are never used on the
    public internet, e.g. 192.168.x.x, 10.x.x.x or 172.16-31.x.x.
    "Loopback" (127.0.0.1) means the Pi itself.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    # An IPv4 address written in IPv6 style (::ffff:192.168.1.5) -> unwrap it.
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_private or ip.is_loopback or ip.is_link_local


@app.before_request
def only_local_network():
    """Runs before EVERY request. Visitors from outside get "403 Forbidden"."""
    if not is_local_address(request.remote_addr):
        abort(403)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def json_body():
    """The data the web page sent along with a button click, as a dict."""
    return request.get_json(silent=True) or {}


def error(message, status=400):
    """Send an error message back to the web page, which shows it to you."""
    return jsonify({"ok": False, "error": message}), status


@app.errorhandler(bluetooth.BluetoothError)
@app.errorhandler(SettingsError)
def action_failed(exception):
    """If a Bluetooth action or a settings change fails, show its message on the web page."""
    return error(str(exception))


# ----------------------------------------------------------------------
# The web page
# ----------------------------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html", volume=settings.volume())


# ----------------------------------------------------------------------
# Status (the page asks for this every few seconds)
# ----------------------------------------------------------------------

@app.get("/api/status")
def status():
    return jsonify({
        "ok": True,
        "radio": player.status(),
        "stations": settings.stations(),
        "known_devices": bluetooth.list_known(),
    })


# ----------------------------------------------------------------------
# Radio
# ----------------------------------------------------------------------

@app.post("/api/radio/play")
def radio_play():
    station = settings.find_station(json_body().get("station"))
    if station is None:
        return error("Unknown station.")
    player.play(station)
    settings.remember(last_station=station["id"])
    return jsonify({"ok": True, "radio": player.status()})


@app.post("/api/radio/stop")
def radio_stop():
    player.stop()
    return jsonify({"ok": True, "radio": player.status()})


@app.post("/api/volume")
def volume():
    try:
        percent = int(json_body().get("percent"))
    except (TypeError, ValueError):
        return error("Volume must be a number between 0 and 100.")
    percent = player.set_volume(percent)
    settings.remember(volume=percent)
    return jsonify({"ok": True, "volume": percent})


# ----------------------------------------------------------------------
# Editing the station list (saved in the data folder, see settings.py)
# ----------------------------------------------------------------------

def stations_answer():
    """The answer for every station change: the whole new list."""
    return jsonify({"ok": True, "stations": settings.stations(), "selected": settings.last_station()})


@app.get("/api/stations")
def stations():
    return stations_answer()


@app.post("/api/stations/add")
def station_add():
    body = json_body()
    settings.add_station(body.get("name"), body.get("url"))
    return stations_answer()


@app.post("/api/stations/update")
def station_update():
    body = json_body()
    settings.update_station(body.get("id"), body.get("name"), body.get("url"))
    return stations_answer()


@app.post("/api/stations/delete")
def station_delete():
    station_id = json_body().get("id")
    settings.delete_station(station_id)
    # Deleting the station that is playing right now also stops it.
    playing = player.status()["station"]
    if playing and playing["id"] == station_id:
        player.stop()
    return stations_answer()


@app.post("/api/stations/move")
def station_move():
    body = json_body()
    settings.move_station(body.get("id"), -1 if body.get("direction") == "up" else 1)
    return stations_answer()


@app.post("/api/stations/restore-defaults")
def station_restore_defaults():
    settings.restore_default_stations()
    return stations_answer()


# ----------------------------------------------------------------------
# Bluetooth
# ----------------------------------------------------------------------

@app.get("/api/bluetooth/devices")
def bluetooth_devices():
    return jsonify({"ok": True, "devices": bluetooth.list_known()})


@app.post("/api/bluetooth/scan")
def bluetooth_scan():
    return jsonify({"ok": True, "devices": bluetooth.scan()})


@app.post("/api/bluetooth/connect")
def bluetooth_connect():
    bluetooth.connect(json_body().get("mac"))
    # If the radio is already playing, restart it so the sound moves to the box.
    player.restart_if_playing()
    return jsonify({"ok": True})


@app.post("/api/bluetooth/pair")
def bluetooth_pair():
    bluetooth.pair(json_body().get("mac"))
    player.restart_if_playing()
    return jsonify({"ok": True})


@app.post("/api/bluetooth/disconnect")
def bluetooth_disconnect():
    bluetooth.disconnect(json_body().get("mac"))
    return jsonify({"ok": True})


@app.post("/api/bluetooth/forget")
def bluetooth_forget():
    bluetooth.forget(json_body().get("mac"))
    return jsonify({"ok": True})


# ----------------------------------------------------------------------
# Start the server when you run "python app.py" (handy for testing).
# Inside Docker the server "gunicorn" is used instead (see Dockerfile).
# ----------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT)
