#!/usr/bin/env bash
# RadioBlue update - run this in your deployment folder:   ./update.sh
#
# managed-by: radioblue install.sh (replaced on every update - don't edit)
#
# It downloads the newest installer and runs it for this folder. The installer
# backs up your settings, refreshes compose.yaml, downloads the newest
# container and restarts it. Your .env, your stations (data/) and your paired
# Bluetooth boxes are kept.
set -euo pipefail

RADIOBLUE_RAW_URL="${RADIOBLUE_RAW_URL:-https://raw.githubusercontent.com/SebsCode98/radioblue/main}"
deploy_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Download completely first, then run - a broken download never runs half a script.
installer="$(mktemp)"
trap 'rm -f "$installer"' EXIT
curl -fsSL "$RADIOBLUE_RAW_URL/install.sh" -o "$installer"
bash "$installer" "$deploy_dir" "$@"
