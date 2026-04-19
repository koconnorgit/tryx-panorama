#!/usr/bin/env bash
# Install the tryx-panorama systemd --user service, pointing at the installed
# reed-tpse binary. Does NOT require sudo.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
TEMPLATE="$SCRIPT_DIR/../data/systemd/tryx-panorama.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_PATH="$UNIT_DIR/tryx-panorama.service"

if [[ ! -f "$TEMPLATE" ]]; then
    echo "service template not found at $TEMPLATE" >&2
    exit 1
fi

# Discover reed-tpse binary
REED=""
for candidate in \
    "$(command -v reed-tpse 2>/dev/null || true)" \
    "$HOME/.local/bin/reed-tpse" \
    "/usr/local/bin/reed-tpse" \
    "/home/kevin/tryx/reed-tpse/build/reed-tpse"
do
    if [[ -n "$candidate" && -x "$candidate" ]]; then
        REED="$candidate"
        break
    fi
done

if [[ -z "$REED" ]]; then
    echo "reed-tpse binary not found. Build and install reed-tpse first." >&2
    exit 1
fi

echo "Using reed-tpse at: $REED"
mkdir -p "$UNIT_DIR"
sed "s|@REED_TPSE_BIN@|$REED|g" "$TEMPLATE" > "$UNIT_PATH"
echo "Wrote $UNIT_PATH"

systemctl --user daemon-reload
echo "Reloaded user systemd"

echo
echo "Enable on login:   systemctl --user enable tryx-panorama.service"
echo "Start now:         systemctl --user start tryx-panorama.service"
echo "(or use the tray icon's Daemon menu)"
