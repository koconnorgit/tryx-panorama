#!/usr/bin/env bash
# Clone, build, and install reed-tpse (by @fadli0029) into ~/.local/bin.
# Idempotent: re-running updates an existing clone via `git pull`.
# Does NOT require sudo.
set -euo pipefail

REED_SRC_DIR="${REED_TPSE_SRC_DIR:-$HOME/.local/share/tryx-panorama/reed-tpse}"
REED_REMOTE="${REED_TPSE_REMOTE:-https://github.com/fadli0029/reed-tpse.git}"
INSTALL_BIN="$HOME/.local/bin/reed-tpse"

# Build-time dependency check
missing=()
for cmd in git cmake make g++; do
    command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
if ((${#missing[@]})); then
    echo "Missing build dependencies: ${missing[*]}" >&2
    echo "On Arch / CachyOS:  sudo pacman -S --needed base-devel cmake git" >&2
    echo "On Debian / Ubuntu: sudo apt install build-essential cmake git" >&2
    exit 1
fi

# Clone or fast-forward update
if [[ -d "$REED_SRC_DIR/.git" ]]; then
    echo "Updating existing reed-tpse clone at $REED_SRC_DIR"
    git -C "$REED_SRC_DIR" pull --ff-only
else
    mkdir -p "$(dirname "$REED_SRC_DIR")"
    echo "Cloning reed-tpse from $REED_REMOTE"
    echo "  into $REED_SRC_DIR"
    git clone "$REED_REMOTE" "$REED_SRC_DIR"
fi

# Build (out-of-tree)
BUILD_DIR="$REED_SRC_DIR/build"
mkdir -p "$BUILD_DIR"
echo "Configuring build"
cmake -S "$REED_SRC_DIR" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
echo "Compiling"
cmake --build "$BUILD_DIR" --parallel

# Install binary to ~/.local/bin
mkdir -p "$(dirname "$INSTALL_BIN")"
install -m 0755 "$BUILD_DIR/reed-tpse" "$INSTALL_BIN"
echo "Installed: $INSTALL_BIN"

# PATH sanity check (non-fatal)
case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *)
        echo "WARN: $HOME/.local/bin is not on your PATH." >&2
        echo "      Add it to ~/.bashrc / ~/.zshrc / ~/.config/fish/config.fish" >&2
        ;;
esac
