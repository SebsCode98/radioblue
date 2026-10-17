# How RadioBlue works (explained simply)

## The big picture

```
 Your phone / laptop                 Raspberry Pi
 ┌───────────────┐   home network   ┌─────────────────────────────────────────────┐
 │  web browser  │ ───────────────▶ │  Docker container "radioblue"               │
 └───────────────┘   port 8095      │   app.py  (Flask web server)                │
                                    │     ├─ settings.py ─▶ /data/settings.json ──┼──▶ ~/docker/radioblue/data
                                    │     ├─ radio.py ─▶ mpv ──┐                  │
                                    │     └─ bluetooth.py ─▶ bluetoothctl ──┐     │
                                    └─────────────────────────┼─────────────┼─────┘
                                                              │             │
                                          PipeWire sound server ◀┘     BlueZ (Bluetooth service)
                                                              │             │
                                                              └──▶ 🔊 Bluetooth box ◀┘
```

1. You open the page. Your browser asks `app.py` for it.
2. You press a button. A small script in the page (`static/app.js`) sends a background
   request like "play bayern1" to `app.py`.
3. `app.py` passes the job on:
   - radio jobs go to **`radio.py`**, which starts or stops the music player **mpv**.
   - station changes go to **`settings.py`**, which saves them in `settings.json`.
   - Bluetooth jobs go to **`bluetooth.py`**, which runs the tool **bluetoothctl**.
4. mpv sends the music to the Pi's sound server (**PipeWire**), which sends it to the box.
   bluetoothctl asks the Pi's Bluetooth service (**BlueZ**) to pair/connect boxes.
5. Every 4 seconds the page asks `app.py` "what's the status?" and updates itself.

## Why Docker, and how can a container play sound and use Bluetooth?

A Docker container is like a small, sealed box with its own programs inside. That keeps the
Pi clean: mpv, bluetoothctl and Python are only inside the container.

The container can't see the Pi's hardware directly. Instead, `compose.yaml` shares two
**sockets** with it. A socket is a special file that programs use to talk to each other:

| Socket | Who listens on the Pi | What the container uses it for |
|---|---|---|
| `/run/dbus/system_bus_socket` | the system "message bus" (D-Bus); BlueZ listens there | Bluetooth: scan, pair, connect |
| `/run/user/<your user id>/pulse/native` | PipeWire (the sound server of your user) | play sound, list speakers |

The container runs as your normal user (`PUID`/`PGID` in `.env`), because the sound server
only accepts that user.

## What is kept during an update?

A container is thrown away and rebuilt on every update. Everything that must survive is
therefore stored **outside** of it:

| What | Where | Why it survives |
|---|---|---|
| Your stations, volume, last station | `data/settings.json` in the deployment folder, mounted into the container as `/data` | It is a folder on the Pi, not in the container. `install.sh` also copies it to `data/backups/` before every update. |
| Port, user id, time zone | `.env` in the deployment folder | The installer creates it once and never overwrites it. |
| The container itself | – | Nothing in it needs to survive; it is simply replaced by the new version. |
| Paired Bluetooth boxes | `/var/lib/bluetooth` on the Pi (BlueZ) | The container never stores them; it only asks BlueZ. |

`settings.json` carries a `version` number. If a future RadioBlue version stores settings
differently, `settings.py` converts the old file automatically when it starts.

The update itself (`update.sh` downloads the newest `install.sh` and runs it):

1. `settings.json` is backed up; `.env` and `data/` are left alone.
2. The managed files `compose.yaml` and `update.sh` are refreshed from `deploy/` on GitHub.
3. `docker compose pull` downloads the newest container, `docker compose up -d` replaces
   the old one with it.
4. The old, now unused RadioBlue image is deleted to save space.

## Where does the container come from? Which Pis are supported?

On every push to `main`, GitHub Actions (`.github/workflows/docker-publish.yml`) builds the
container and publishes it as `ghcr.io/sebscode98/radioblue`. It is built for three
processor types at once, and Docker on the Pi automatically downloads the matching one:

| Platform | Raspberry Pi |
|---|---|
| `linux/arm64` | Pi 3, 4, 5, Zero 2 W with a 64-bit OS |
| `linux/arm/v7` | Pi 2, 3, 4, Zero 2 W with a 32-bit OS |
| `linux/amd64` | (normal PCs – handy for testing) |

The base image is `python:3.13-slim-trixie`. All other parts (mpv, bluez, pulseaudio-utils,
Flask, gunicorn) come from Debian or are pure Python, so nothing has to be compiled.

## The files

| File | What it does |
|---|---|
| `app.py` | The web server. Shows the page, receives button clicks, blocks visitors from outside the home network. **Start reading here.** |
| `settings.py` | Loads and saves your stations, volume and last station (`settings.json`). Contains the default stations. |
| `config.py` | Technical settings (data folder, scan time), read from environment variables. |
| `radio.py` | Starts/stops mpv, changes the radio volume, reads the current song title. |
| `bluetooth.py` | Runs bluetoothctl commands: list known boxes, scan, pair, connect, disconnect, forget. |
| `audio.py` | Finds out which PipeWire "sink" (speaker) belongs to the Bluetooth box. Read-only. |
| `templates/index.html` | The structure of the web page. |
| `static/style.css` | The look of the web page (colours, sizes, dark mode). |
| `static/app.js` | What happens when you click something on the page. |
| `Dockerfile` | The recipe for building the container. |
| `install.sh` | Installer and updater: checks the Pi, creates the deployment folder, downloads and starts the container. |
| `.github/workflows/docker-publish.yml` | Builds the container for all Pi types and publishes it on GitHub. |
| `deploy/compose.yaml` | How to run the container: image, port, shared sockets, data folder, user, auto-restart. Copied to the deployment folder. |
| `deploy/env.example` | Template for `.env`, the per-Pi settings. |
| `deploy/update.sh` | The update command. Copied to the deployment folder. |

## The API (for the curious)

The page talks to these addresses. You can also try them yourself, e.g. with `curl`:

| Method + address | Body | What it does |
|---|---|---|
| `GET /api/status` | – | Radio state + stations + known boxes |
| `GET /api/stations` | – | List of stations (+ the last played one) |
| `POST /api/stations/add` | `{"name": "My Radio", "url": "https://..."}` | Add a station |
| `POST /api/stations/update` | `{"id": "my-radio", "name": "...", "url": "..."}` | Change name / address |
| `POST /api/stations/move` | `{"id": "my-radio", "direction": "up"}` | Move up / down in the list |
| `POST /api/stations/delete` | `{"id": "my-radio"}` | Delete a station |
| `POST /api/stations/restore-defaults` | `{}` | Replace the list with the default stations |
| `POST /api/radio/play` | `{"station": "bayern1"}` | Play a station |
| `POST /api/radio/stop` | `{}` | Stop |
| `POST /api/volume` | `{"percent": 50}` | Radio volume 0–100 |
| `GET /api/bluetooth/devices` | – | Known (paired) boxes |
| `POST /api/bluetooth/scan` | `{}` | Search ~10 s for new boxes |
| `POST /api/bluetooth/pair` | `{"mac": "AA:BB:CC:DD:EE:FF"}` | Pair + trust + connect a new box |
| `POST /api/bluetooth/connect` | `{"mac": "..."}` | Connect a known box |
| `POST /api/bluetooth/disconnect` | `{"mac": "..."}` | Disconnect |
| `POST /api/bluetooth/forget` | `{"mac": "..."}` | Forget (unpair) |

Example:

```bash
curl -X POST -H 'Content-Type: application/json' \
     -d '{"station": "rockantenne-bayern"}' http://<address-of-your-pi>:8095/api/radio/play
```

## Living next to other audio players (e.g. Spotify Connect / librespot)

If the Pi also runs other players, RadioBlue is careful not to change anything they rely on:

- **Volume:** RadioBlue only changes mpv's own volume, never the speaker's volume.
- **Output:** mpv is told to play directly to the Bluetooth box (`--audio-device=...`). The
  Pi's *default* speaker – which other players use – is left alone.
- **Nothing on the Pi is changed:** no packages, no config files, no service restarts.
