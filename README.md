# 📻 RadioBlue

A tiny website for your Raspberry Pi that plays web radio on your Bluetooth box.

- ▶ Play / ■ Stop internet radio – comes with **Rock Antenne Bayern**, **Bayern 1** and
  **Radio Bob**, and you can **add, rename, reorder and delete your own stations** on the page
- Shows the song that is playing right now
- Radio volume slider
- Connect / disconnect / forget your **known** Bluetooth boxes
- Search for and pair **new** Bluetooth boxes
- Only reachable from your **home network**
- Runs inside **Docker** – nothing is installed on the Pi itself
- Your stations and settings are **kept during updates**

---

## Setup guide

### What you need

- A Raspberry Pi with Bluetooth: Pi 3, 4, 5 or Zero 2 W (or a Pi with a Bluetooth USB stick).
  The original Pi Zero W and Pi 1 are not supported.
- **Raspberry Pi OS** (Bookworm or Trixie) or another Debian-based system, 64-bit
  recommended. Ready-made containers exist for 64-bit (arm64) and 32-bit (armv7) systems.
  (Note that recent Docker versions no longer support the 32-bit Raspberry Pi OS.)
- Internet access on the Pi and a Bluetooth speaker ("box").

Tested on 64-bit Raspberry Pi OS (Debian 13 "trixie").

### Step 1 – Prepare the Pi (once)

Open a terminal on the Pi (or connect with `ssh`) and run these commands **as your normal
user** (not as root).

**a) Install Docker** (skip if `docker compose version` already prints a version):

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

**b) Make sure the sound server is installed.** Raspberry Pi OS *with desktop* already has
it. On Raspberry Pi OS **Lite**, install it:

```bash
sudo apt update
sudo apt install -y pipewire pipewire-pulse wireplumber libspa-0.2-bluetooth bluez
```

**c) Keep the sound server running without a login**, so the radio works right after a
reboot, and make sure Bluetooth is on:

```bash
sudo loginctl enable-linger $USER
sudo systemctl enable --now bluetooth
```

**d) Reboot** (`sudo reboot`) so all of this takes effect. Afterwards,
`ls /run/user/$(id -u)/pulse/native` should show the file (that is the sound server's socket).

### Step 2 – Install RadioBlue

Download the installer, (optionally) look at it, and run it:

```bash
curl -fsSLO https://raw.githubusercontent.com/SebsCode98/radioblue/main/install.sh
bash install.sh
```

The installer checks the Pi, creates the folder **`~/docker/radioblue`** with your
settings, downloads the ready-made container and starts it. You don't need Git and
nothing is compiled. At the end it prints the address of the page, e.g.
`http://192.168.1.50:8095`. You can delete `install.sh` afterwards.

Options:

| Command | What it does |
|---|---|
| `bash install.sh --port 8123` | Use a different port for the web page (default: 8095) |
| `bash install.sh /path/to/folder` | Install to a different folder instead of `~/docker/radioblue` |

<details>
<summary>Prefer to do it by hand? (without the installer)</summary>

```bash
mkdir -p ~/docker/radioblue/data && cd ~/docker/radioblue
curl -fsSLO https://raw.githubusercontent.com/SebsCode98/radioblue/main/deploy/compose.yaml
docker compose up -d
```

This uses the defaults (port 8095, user id 1000 = the first user on a Raspberry Pi). To
change them, download
[`deploy/env.example`](deploy/env.example) as `.env` into the same folder and edit it.
Create the `data` folder *before* the first start, as shown – otherwise Docker creates it
for the root user and RadioBlue can't save your stations. To update later:
`docker compose pull && docker compose up -d`.
</details>

### Step 3 – Open the page

On your phone or computer (in the same home network as the Pi), open
**`http://<address-of-your-pi>:8095`**. `hostname -I` on the Pi shows its address.

RadioBlue starts automatically after every reboot.

---

## Where things live

Everything is in one folder, `~/docker/radioblue`:

| File / folder | What is in it | Changed by updates? |
|---|---|---|
| `.env` | **Your settings for this Pi**: port, user id, time zone | **never** |
| `data/settings.json` | **Your stations**, volume and last station | **never** |
| `data/backups/` | Copies of `settings.json` from before each update (last 10) | new copy added |
| `compose.yaml` | How Docker runs the container | replaced – don't edit |
| `update.sh` | The update command | replaced – don't edit |
| `compose.override.yaml` | *Optional*: your own Docker additions | **never** |

Your **paired Bluetooth boxes** are not stored in the container at all – the Pi's own
Bluetooth service remembers them. Updating, reinstalling or even deleting RadioBlue never
makes the Pi forget a box.

## Updating

```bash
~/docker/radioblue/update.sh
```

This backs up your `settings.json`, downloads the newest `compose.yaml` and container, and
restarts RadioBlue. Your `.env`, your stations and your Bluetooth boxes are kept.

**Restore a backup** of your stations:

```bash
cd ~/docker/radioblue
docker compose stop
cp data/backups/settings-YYYYMMDD-HHMMSS.json data/settings.json
docker compose start
```

## Changing settings

### Port

```bash
~/docker/radioblue/update.sh --port 8123
```

or edit `RADIOBLUE_PORT` in `~/docker/radioblue/.env` and apply it with
`cd ~/docker/radioblue && docker compose up -d`.

### Other settings in `.env`

| Setting | Meaning |
|---|---|
| `RADIOBLUE_PORT` | Port of the web page (default 8095) |
| `RADIOBLUE_BIND` | `0.0.0.0` = reachable from the home network, `127.0.0.1` = only from the Pi itself |
| `PUID` / `PGID` | Your user and group id (`id -u` / `id -g`). Filled in by the installer. |
| `TZ` | Time zone for the log, e.g. `Europe/London`. Filled in by the installer. |
| `SCAN_SECONDS` | How long "Search for boxes" searches (default 10) |
| `CONNECT_TIMEOUT_SECONDS` | How long to wait when pairing/connecting (default 20) |
| `RADIOBLUE_IMAGE` | Which container to use, e.g. a fixed version like `ghcr.io/sebscode98/radioblue:1.0` |

After editing `.env`, run `docker compose up -d` in `~/docker/radioblue`.

## Other useful commands

Run these in `~/docker/radioblue`:

| What you want                     | Command                          |
|-----------------------------------|----------------------------------|
| See if it runs                    | `docker compose ps`              |
| See the log (error messages)      | `docker compose logs -f`         |
| Stop it                           | `docker compose stop`            |
| Start it again                    | `docker compose start`           |
| Uninstall (keeps your settings)   | `docker compose down --rmi all`  |

To remove everything including your stations, uninstall and then delete `~/docker/radioblue`.

## How to use it

### Listen to the radio
1. Switch on your Bluetooth box and press **Connect** next to it (see below).
2. Tap a station, then **▶ Play**. Tap another station to switch.
3. **■ Stop** stops the radio.

The volume slider changes **only the radio's volume**. If the box is too quiet overall,
turn up the box itself. RadioBlue remembers the volume and the last station.

### Add, change or remove stations
1. Press **✎ Edit stations** next to "Radio".
2. **Add a station:** enter a name and the station's *stream address* and press **＋ Add station**.
   You can find stream addresses on [radio-browser.info](https://www.radio-browser.info)
   or on the station's website (often ending in `.mp3`, `.aac`, `.m3u` or `.pls`).
3. **Change** a name or address and press **Save**, move stations with **↑ / ↓**,
   or remove them with **Delete**.
4. **Restore default stations** brings back the three original stations (and replaces your list).

### Connect a box you have used before
Under **My Bluetooth boxes**, press **Connect**. If the radio is already playing it moves
over to the box automatically.

### Add a new box
1. Put the box into **pairing mode** – usually by holding its Bluetooth button until
   the light flashes quickly (see the box's manual).
2. Under **Add a new box**, press **🔍 Search for boxes** and wait about 10 seconds.
3. Press **Pair & connect** next to your box (🔊 marks speakers/headphones).
4. From now on it shows up under **My Bluetooth boxes**.

### Remove a box
Press **Forget**. To use it again you have to pair it again (see above).

## Does this affect other audio on the Pi (e.g. Spotify Connect)?

No. RadioBlue does not change any settings on the Pi:

- It does not install anything on the Pi, edit config files, or restart any service.
- The volume slider only changes the radio's own volume, not the speaker volume.
- It does not change the Pi's default speaker; the radio plays directly to the Bluetooth box.

Things to know:
- If another player (e.g. Spotify Connect) and the radio play at the same time, you hear both mixed together.
- **Disconnect** / **Forget** on a box that another player uses also stops that player's sound.
- **Search** keeps the Bluetooth chip busy for ~10 seconds; music can stutter briefly.

## Only reachable from the home network – how?

1. Docker only opens the port for IPv4 (`RADIOBLUE_BIND=0.0.0.0`). Your router does not let
   IPv4 connections from the internet in, and because no IPv6 port is opened, a public IPv6
   address of the Pi can't be used either.
2. As a second safety net, `app.py` refuses every visitor whose address is not a private
   home-network address (answer: "403 Forbidden").

Do **not** set up port forwarding to this port on your router.

## Troubleshooting

| Problem | Try this |
|---|---|
| `install.sh`: "Your user may not use Docker yet" | Run `sudo usermod -aG docker $USER`, log out and in again (or reboot). |
| `install.sh`: "sound server socket ... not found" | Do step 1 b) – d) of the setup guide and reboot. |
| "Could not download the container" | Check the Pi's internet connection, then run `update.sh` again. |
| Page does not open | `docker compose ps` – is it "running"? Correct address and port? Same network? |
| "Could not save the settings" | The data folder belongs to another user. Run `sudo chown -R $(id -u):$(id -g) ~/docker/radioblue/data` |
| Stations are suddenly the defaults again | `settings.json` was damaged. It was kept as `data/settings.json.broken`; restore it or a file from `data/backups/`. |
| No sound after a reboot | Run `sudo loginctl enable-linger $USER` and reboot. |
| "Could not connect" | Box switched on? Close to the Pi? Not connected to your phone at the same time? |
| New box not found | Is it really in pairing mode (fast flashing)? Search again. Some boxes leave pairing mode after a minute. |
| "Pairing failed" | Press **Forget** on your phone for this box, put it into pairing mode again, retry. |
| Radio plays but no sound | Is the box connected *before* pressing Play? Is the radio volume above 0? Is the box itself turned up? |
| A new station does not play | Check the stream address – open it in your browser; it should start playing or download a small playlist file. |
| Radio stops by itself | The station's stream was interrupted. Press Play again. Check the Pi's internet. |
| Port already in use | Pick another one: `~/docker/radioblue/update.sh --port <number>` |

## Development

To change the code yourself:

```bash
git clone https://github.com/SebsCode98/radioblue.git ~/projects/radioblue
cd ~/projects/radioblue
bash install.sh                                  # uses the deploy/ files of your copy
docker build -t ghcr.io/sebscode98/radioblue:latest .
cd ~/docker/radioblue && docker compose up -d    # restart with your own build
```

(`update.sh` replaces your build with the published version again.)
Every push to `main` makes GitHub build and publish a new container
(see `.github/workflows/docker-publish.yml`); a tag like `v1.0.0` publishes version `1.0.0`.

More details on how everything works inside: see [HOW_IT_WORKS.md](HOW_IT_WORKS.md).
