#!/usr/bin/env bash
# RadioBlue update - run this in your deployment folder:   ./update.sh
#
# managed-by: radioblue install.sh (replaced on every update - don't edit)
#
# It downloads the newest RadioBlue code (git pull) and then runs install.sh,
# which backs up your settings, rebuilds the container and starts it again.
# Your .env, your stations (data/) and your paired Bluetooth boxes are kept.
set -euo pipefail

deploy_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source_dir="$(sed -n 's/^RADIOBLUE_SOURCE=//p' "$deploy_dir/.env" | tail -n 1)"
source_dir="${source_dir%\"}"; source_dir="${source_dir#\"}"
if [[ -z "$source_dir" || ! -d "$source_dir/.git" ]]; then
    echo "Could not find the RadioBlue project. Check RADIOBLUE_SOURCE in $deploy_dir/.env" >&2
    exit 1
fi

echo "==> Downloading the newest RadioBlue version into $source_dir"
git -C "$source_dir" pull --ff-only

exec "$source_dir/install.sh" "$deploy_dir"
