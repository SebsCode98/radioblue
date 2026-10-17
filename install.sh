#!/usr/bin/env bash
# RadioBlue installer. Safe to run again at any time - it never deletes your
# settings. Usage:
#
#   bash install.sh                     install to ~/docker/radioblue
#   bash install.sh /some/other/folder  install to a different folder
#   bash install.sh --port 8123         also set (or change) the web page port
#
# What it does:
#   1. checks that Docker, Bluetooth and the sound server are ready
#   2. creates the deployment folder with .env (your settings for this Pi),
#      compose.yaml, update.sh and the data/ folder (your stations)
#   3. backs up data/settings.json, downloads the newest container and starts it
#
# It works on its own (downloaded with curl) and from a copy of the Git project.
set -euo pipefail

# Where the deployment files are downloaded from (can be changed for forks).
RADIOBLUE_RAW_URL="${RADIOBLUE_RAW_URL:-https://raw.githubusercontent.com/SebsCode98/radioblue/main}"

deploy_dir="$HOME/docker/radioblue"
port=""

# When run from the Git project, use its deploy/ files instead of downloading.
local_deploy=""
if [[ -f "${BASH_SOURCE[0]:-}" ]]; then
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [[ -f "$script_dir/deploy/compose.yaml" ]] && local_deploy="$script_dir/deploy"
fi

# ---------------------------------------------------------------- helpers
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
info()  { printf '==> %s\n' "$*"; }
warn()  { printf '\033[33mWARNING:\033[0m %s\n' "$*" >&2; }
fail()  { printf '\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0; }

# Set KEY=VALUE in the .env file (replace the line if it exists, else append).
set_env() {
    local key="$1" value="$2" file="$deploy_dir/.env"
    if grep -q "^${key}=" "$file"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$file"
    else
        printf '%s=%s\n' "$key" "$value" >>"$file"
    fi
}

get_env() { sed -n "s/^$1=//p" "$deploy_dir/.env" | tail -n 1; }

# Install one file from deploy/ (local project or GitHub) as $2 with mode $3.
fetch() {
    local name="$1" target="$2" mode="$3" temporary
    temporary="$(mktemp)"
    if [[ -n "$local_deploy" ]]; then
        cp "$local_deploy/$name" "$temporary"
    else
        curl -fsSL "$RADIOBLUE_RAW_URL/deploy/$name" -o "$temporary" \
            || { rm -f "$temporary"; fail "Could not download $name from $RADIOBLUE_RAW_URL"; }
    fi
    install -m "$mode" "$temporary" "$target"
    rm -f "$temporary"
}

# ---------------------------------------------------------------- arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage ;;
        --port)    port="${2:-}"; shift 2 ;;
        --port=*)  port="${1#--port=}"; shift ;;
        -*)        fail "Unknown option: $1 (see install.sh --help)" ;;
        *)         deploy_dir="$1"; shift ;;
    esac
done
if [[ -n "$port" ]] && ! [[ "$port" =~ ^[0-9]+$ && "$port" -ge 1024 && "$port" -le 65535 ]]; then
    fail "The port must be a number between 1024 and 65535."
fi

bold "RadioBlue installer"
echo "    install to : $deploy_dir"
echo

# ---------------------------------------------------------------- 1. checks
info "Checking your Raspberry Pi"

[[ $EUID -ne 0 ]] || fail "Please run this as your normal user, not with sudo / as root.
       The radio has to run as the user who owns the sound server."

[[ -n "$local_deploy" ]] || command -v curl >/dev/null || fail "curl is missing. Run: sudo apt install -y curl"
command -v docker >/dev/null || fail "Docker is not installed. See the README, step 1."
docker compose version >/dev/null 2>&1 || fail "The Docker Compose plugin is missing. See the README, step 1."
docker info >/dev/null 2>&1 || fail "Your user may not use Docker yet. Run:
       sudo usermod -aG docker $USER
       then log out and in again (or reboot) and run this script again."

[[ -S /run/dbus/system_bus_socket ]] || fail "The system D-Bus socket /run/dbus/system_bus_socket is missing."

if command -v systemctl >/dev/null && ! systemctl is-active --quiet bluetooth; then
    warn "The Bluetooth service is not running. Try: sudo systemctl enable --now bluetooth"
fi

pulse_socket="/run/user/$(id -u)/pulse/native"
if [[ ! -S "$pulse_socket" ]]; then
    warn "The sound server socket $pulse_socket was not found.
         RadioBlue needs PipeWire with its PulseAudio part (pipewire-pulse) running for
         your user. On Raspberry Pi OS Lite install it first - see the README, step 1."
fi

if command -v loginctl >/dev/null && [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]]; then
    warn "\"Linger\" is off for $USER. Then the sound server only runs while you are
         logged in, and the radio has no sound after a reboot. Fix:
         sudo loginctl enable-linger $USER"
fi

# ---------------------------------------------------------------- 2. files
info "Preparing $deploy_dir"
mkdir -p "$deploy_dir"
deploy_dir="$(cd "$deploy_dir" && pwd)"

if [[ ! -f "$deploy_dir/.env" ]]; then
    timezone="$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || true)"
    fetch env.example "$deploy_dir/.env" 600
    set_env PUID "$(id -u)"
    set_env PGID "$(id -g)"
    set_env TZ "${timezone:-Etc/UTC}"
    echo "    created .env (your settings for this Pi)"
fi
[[ -z "$port" ]] || { set_env RADIOBLUE_PORT "$port"; echo "    port set to $port"; }
port="$(get_env RADIOBLUE_PORT)"; port="${port:-8095}"

# Install the managed files. An older, hand-written compose.yaml is kept as a backup.
if [[ -f "$deploy_dir/compose.yaml" ]] && ! grep -q "managed-by: radioblue" "$deploy_dir/compose.yaml"; then
    old="compose.yaml.old-$(date +%Y%m%d-%H%M%S)"
    mv "$deploy_dir/compose.yaml" "$deploy_dir/$old"
    echo "    your previous compose.yaml was saved as $old"
fi
fetch compose.yaml "$deploy_dir/compose.yaml" 644
fetch update.sh    "$deploy_dir/update.sh"    755

# The data folder must belong to you, otherwise the container can't save stations.
mkdir -p "$deploy_dir/data"
if [[ ! -w "$deploy_dir/data" ]]; then
    fail "The folder $deploy_dir/data is not writable for $USER. Fix it with:
       sudo chown -R $(id -u):$(id -g) \"$deploy_dir/data\""
fi

# Back up the settings before every update (the last 10 backups are kept).
if [[ -f "$deploy_dir/data/settings.json" ]]; then
    mkdir -p "$deploy_dir/data/backups"
    cp "$deploy_dir/data/settings.json" "$deploy_dir/data/backups/settings-$(date +%Y%m%d-%H%M%S).json"
    ls -1t "$deploy_dir/data/backups"/settings-*.json | tail -n +11 | xargs -r rm --
    echo "    settings backed up to data/backups/"
fi

# Warn if another program already uses the port.
if command -v ss >/dev/null && ss -Hltn "sport = :$port" | grep -q . \
        && ! docker ps --filter name='^radioblue$' --format '{{.Ports}}' | grep -q ":$port->"; then
    warn "Port $port is already used by another program on this Pi.
         Choose a free one with:  bash install.sh --port <number>"
fi

# ---------------------------------------------------------------- 3. start
info "Downloading the newest RadioBlue container"
(cd "$deploy_dir" && docker compose pull) \
    || warn "Could not download the container (no internet?). Using the version already on this Pi, if there is one."

info "Starting RadioBlue"
(cd "$deploy_dir" && docker compose up -d --remove-orphans)

# An update leaves the previous RadioBlue image behind as "<none>". Remove
# those (only RadioBlue's - other images on this Pi are not touched).
docker image prune -f --filter "label=org.opencontainers.image.title=radioblue" >/dev/null || true

address="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
bold "RadioBlue is running:  http://${address:-<your-pi-address>}:$port"
echo
echo "    Settings for this Pi : $deploy_dir/.env"
echo "    Your stations        : $deploy_dir/data/settings.json"
echo "    Update later with    : $deploy_dir/update.sh"
echo "    See the log with     : docker logs -f radioblue"
