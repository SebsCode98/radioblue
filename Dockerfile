# Recipe for the RadioBlue container.
# You normally don't build this yourself: GitHub builds it automatically
# (.github/workflows/docker-publish.yml) for 64-bit ARM (arm64), 32-bit ARM
# (armv7) and normal PCs (amd64), and install.sh downloads the right one.
#
# To try out your own changes on the Pi, build it under the same name and
# restart the container (in the deployment folder, e.g. ~/docker/radioblue):
#   docker build -t ghcr.io/sebscode98/radioblue:latest ~/projects/radioblue
#   docker compose up -d
#
# The container brings its own programs (mpv, bluetoothctl, pactl). Nothing is
# installed on the Raspberry Pi itself. It only talks to the Pi's existing
# services through two "sockets" that compose.yaml shares with it:
#   - the system D-Bus  -> to control Bluetooth (BlueZ)
#   - the PipeWire/Pulse socket -> to play sound

FROM python:3.13-slim-trixie

# install.sh uses this label to clean up old RadioBlue images after an update.
LABEL org.opencontainers.image.title="radioblue" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.description="Web radio and Bluetooth speaker control for the Raspberry Pi"

# Print logs immediately (no buffering) and skip writing .pyc files.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp

# mpv               = plays the radio stream
# bluez             = contains "bluetoothctl" (talks to the Pi's Bluetooth service)
# pulseaudio-utils  = contains "pactl" (asks the sound server which speakers exist)
# The "--no-install-recommends" flag keeps the image small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends mpv bluez pulseaudio-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# /data holds your settings (settings.json). compose.yaml replaces it with the
# "data" folder on the Pi so the settings survive updates. The container runs
# as YOUR user id, so the folder must be writable for any user.
ENV DATA_DIR=/data
RUN mkdir -p /data && chmod 1777 /data

# The port INSIDE the container. The port on your Pi is set in .env (RADIOBLUE_PORT).
EXPOSE 8095

# Docker marks the container "unhealthy" if the page stops answering.
HEALTHCHECK --interval=30s --timeout=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8095/api/stations', timeout=4)" || exit 1

# Start the web server:
#   --workers 1    exactly ONE copy of the app, so there is only one radio player
#   --threads 8    but it can handle several clicks at the same time
#   --timeout 120  pairing a box can take a while, don't cut it off
CMD ["gunicorn", "--bind", "0.0.0.0:8095", "--workers", "1", "--threads", "8", "--timeout", "120", "app:app"]
