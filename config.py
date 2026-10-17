"""
config.py - Technical settings of RadioBlue in one place.

Your own settings (radio stations, volume, last station) are NOT here - they
are changed on the web page and saved in the data folder (see settings.py).

The values below can be changed WITHOUT editing code, by setting an
"environment variable" (a named value given to the program when it starts).
With Docker you do that in the .env file next to compose.yaml
(see .env.example in this project).
"""

import os

# ---------------------------------------------------------------------------
# Web server
# ---------------------------------------------------------------------------

# The port the web server listens on INSIDE the container. You normally don't
# change this - to use a different port on your Pi, set RADIOBLUE_PORT in the
# .env file instead. Docker then forwards that port to this one.
PORT = int(os.environ.get("PORT", "8095"))

# ---------------------------------------------------------------------------
# Saved settings
# ---------------------------------------------------------------------------

# The folder where settings.json is stored. compose.yaml connects /data to the
# "data" folder next to compose.yaml, so the settings survive updates.
DATA_DIR = os.environ.get("DATA_DIR", "/data")

# ---------------------------------------------------------------------------
# Bluetooth
# ---------------------------------------------------------------------------

# How many seconds to look for new Bluetooth boxes when you press "Search".
SCAN_SECONDS = int(os.environ.get("SCAN_SECONDS", "10"))

# How many seconds to wait for pairing / connecting before giving up.
CONNECT_TIMEOUT_SECONDS = int(os.environ.get("CONNECT_TIMEOUT_SECONDS", "20"))

# ---------------------------------------------------------------------------
# Files used while running
# ---------------------------------------------------------------------------

# The radio player (mpv) opens a small "control socket" here, so that the
# website can tell it to change the volume while it is playing.
MPV_SOCKET_PATH = os.environ.get("MPV_SOCKET_PATH", "/tmp/radioblue-mpv.sock")
