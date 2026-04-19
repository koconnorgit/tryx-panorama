#!/usr/bin/env bash
# Install the Tryx Panorama udev rule so /dev/ttyACM* is granted to the active
# desktop session user (via systemd-logind uaccess). Requires sudo.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
SRC="$SCRIPT_DIR/../data/udev/71-tryx-panorama.rules"
DST="/etc/udev/rules.d/71-tryx-panorama.rules"

if [[ ! -f "$SRC" ]]; then
    echo "udev source rule not found at $SRC" >&2
    exit 1
fi

echo "Installing udev rule to $DST (requires sudo)"
sudo install -m 0644 "$SRC" "$DST"

echo "Reloading udev"
sudo udevadm control --reload

echo "Triggering rules for already-connected devices"
sudo udevadm trigger --subsystem-match=tty --action=change
sudo udevadm trigger --subsystem-match=usb --action=change

echo
echo "Done. Unplug and replug the Tryx cooler's USB cable OR reboot for the"
echo "uaccess ACL to take effect on the currently connected device."
