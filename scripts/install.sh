#!/usr/bin/env bash
# One-shot installer for tryx-panorama:
#   1. Runtime dependency check
#   2. Clone + build + install reed-tpse into ~/.local/bin
#   3. Install udev rule to /etc/udev/rules.d (sudo prompt)
#   4. Install systemd --user service pointing at the installed reed-tpse
#   5. Install the launcher wrapper at ~/.local/bin/tryx-panorama
#   6. Install the .desktop file to ~/.local/share/applications
#   7. Enable + start the daemon
# Idempotent. Re-run to update reed-tpse from upstream or repair a broken install.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
REPO_DIR="$(cd -- "$SCRIPT_DIR/.." &>/dev/null && pwd)"

log() { printf "\n\033[1;36m==\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33mWARN:\033[0m %s\n" "$*" >&2; }

log "Checking runtime dependencies"
missing=()
for cmd in adb ffmpeg python git cmake make g++; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
if ! python -c "import PySide6" 2>/dev/null; then
    missing+=("python-pyside6")
fi
if ((${#missing[@]})); then
    echo "Missing runtime / build dependencies: ${missing[*]}" >&2
    echo >&2
    echo "On Arch / CachyOS:" >&2
    echo "  sudo pacman -S --needed base-devel cmake git android-tools ffmpeg pyside6" >&2
    echo >&2
    echo "On Debian / Ubuntu:" >&2
    echo "  sudo apt install build-essential cmake git adb ffmpeg python3-pyside6.qtwidgets" >&2
    exit 1
fi
echo "All dependencies present."

log "Installing reed-tpse (clone + build + install)"
bash "$SCRIPT_DIR/install-reed-tpse.sh"

log "Installing udev rule (may prompt for sudo)"
bash "$SCRIPT_DIR/install-udev.sh"

log "Installing systemd --user service"
bash "$SCRIPT_DIR/install-service.sh"

log "Installing tryx-panorama launcher"
LAUNCHER="$HOME/.local/bin/tryx-panorama"
mkdir -p "$(dirname "$LAUNCHER")"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
exec python -c 'import sys; sys.path.insert(0, "$REPO_DIR/src"); from tryx_panorama.app import main; raise SystemExit(main())' "\$@"
EOF
chmod 0755 "$LAUNCHER"
echo "Installed: $LAUNCHER"

log "Installing .desktop launcher"
install -Dm 0644 "$REPO_DIR/data/tryx-panorama.desktop" \
    "$HOME/.local/share/applications/tryx-panorama.desktop"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
fi
echo "Installed: $HOME/.local/share/applications/tryx-panorama.desktop"

log "Enabling + starting daemon"
systemctl --user daemon-reload
systemctl --user enable tryx-panorama.service >/dev/null 2>&1 || true
if ! systemctl --user start tryx-panorama.service 2>&1; then
    warn "Daemon failed to start. You may need to unplug/replug the cooler's USB"
    warn "cable once for the udev uaccess ACL to apply to the live device, then:"
    warn "  systemctl --user restart tryx-panorama.service"
fi

case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) warn "$HOME/.local/bin is not on PATH — the 'tryx-panorama' command won't resolve until you add it." ;;
esac

log "Done."
echo "Launch:  tryx-panorama"
echo "         (or find 'Tryx Panorama' in your KDE application menu)"
