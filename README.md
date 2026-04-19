# tryx-panorama

System-tray GUI for the [Tryx](https://www.tryx.com) Panorama AIO cooler's LCD
display on Linux. PySide6 front-end that wraps the
[**reed-tpse**](https://github.com/fadli0029/reed-tpse) CLI (by
[@fadli0029](https://github.com/fadli0029)) with:

- File-picker uploads for images, videos, and GIFs (reed-tpse auto-converts
  GIF → MP4 via `ffmpeg`)
- A media browser to switch what's shown on the LCD, delete files, and
  adjust brightness
- System-tray icon with daemon start / stop / restart and a live running
  status indicator
- `systemd --user` service for the keepalive daemon so the chosen media
  persists across reboots
- A `udev` rule that grants `/dev/ttyACM*` to the active session user via
  `uaccess`, so no group-membership gymnastics are required

Tested on CachyOS + KDE Plasma (Wayland), with a Tryx Panorama 360
(firmware V1.0.11, hardware V1.1). Should work on any KDE / XFCE / Cinnamon
desktop; GNOME Shell needs the AppIndicator extension for the tray icon.

## Credit where it's due

All of the hard reverse-engineering work — decoding the frame protocol,
figuring out the CDC-ACM + ADB split, handling the keepalive — was done by
**[@fadli0029](https://github.com/fadli0029)** in the
[**reed-tpse**](https://github.com/fadli0029/reed-tpse) project. This
repository is just a Qt GUI that shells out to their CLI; it would not exist
without their work. Please ⭐ their repo, not this one.

## Requirements

Runtime:
- Python 3.10+
- `PySide6` (`pacman -S pyside6` on Arch/CachyOS)
- `reed-tpse` built and available on `$PATH`
  (auto-discovery also checks `~/.local/bin`, `/usr/local/bin`, and
  `/home/kevin/tryx/reed-tpse/build/reed-tpse`)
- `adb` (from `android-tools`) and `ffmpeg`, both required by reed-tpse
- KDE Plasma or another desktop with `StatusNotifierItem` tray support

## Install

```bash
# 0. Build and install reed-tpse first (see its README).
#    This project assumes the binary is on $PATH or at a known location.

# 1. udev rule — grants /dev/ttyACM* + the USB device to the active session
#    user, so no `uucp` group membership required.
./scripts/install-udev.sh            # requires sudo once

# 2. systemd --user service template for the keepalive daemon
./scripts/install-service.sh         # no sudo; writes ~/.config/systemd/user/

# 3. Put a launcher on $PATH
install -m 0755 - ~/.local/bin/tryx-panorama <<'EOF'
#!/usr/bin/env bash
exec python -c 'import sys; sys.path.insert(0, "REPO_PATH/src"); from tryx_panorama.app import main; raise SystemExit(main())' "$@"
EOF
# Substitute REPO_PATH above for the absolute path to this repo.

# 4. (Optional) .desktop launcher for the KDE app menu
install -m 0644 data/tryx-panorama.desktop ~/.local/share/applications/

# 5. Enable the daemon on login
systemctl --user enable --now tryx-panorama.service
```

## Run

```bash
tryx-panorama
```

…or launch "Tryx Panorama" from your desktop's application menu.

## Project layout

```
src/tryx_panorama/
├── app.py           QApplication wiring, signal/slot glue
├── backend.py       subprocess wrapper around the reed-tpse CLI
├── tray.py          QSystemTrayIcon + right-click menu
├── window.py        QMainWindow (device info, media list, brightness, daemon)
├── workers.py       QThread workers for long-running ops (upload/display/delete)
└── resources/       SVG icons for the tray (on/off variants)

data/
├── udev/71-tryx-panorama.rules     uaccess ACL + /dev/tryx-panorama symlink
├── systemd/tryx-panorama.service   keepalive user unit (templated)
└── tryx-panorama.desktop           launcher

scripts/
├── install-udev.sh      copies udev rule, reloads, triggers
└── install-service.sh   resolves reed-tpse path, writes ~/.config/systemd/user unit
```

## How it works

`reed-tpse` decodes the Tryx protocol (documented in its repo — frame
markers `0x5A`, byte-stuffing with `0x5B`, sum-of-bytes CRC, length-prefixed
frames carrying HTTP-like text headers and a JSON body) and speaks to the
cooler over two USB interfaces it exposes:

1. **CDC-ACM** on `/dev/ttyACM*` for display control (which media, brightness,
   ratio, screen mode)
2. **ADB** for media file transfer into `/sdcard/pcMedia/` on the LCD's
   embedded Rockchip Android stack

This GUI treats `reed-tpse` as a black-box CLI. Uploads, display changes,
and deletes are dispatched on `QThread` workers so the UI stays responsive.
Daemon start/stop/restart go through `systemctl --user` against
`tryx-panorama.service`, which wraps `reed-tpse daemon start --foreground`.

## What this does *not* do (yet)

The same things reed-tpse doesn't do yet:

- CPU / GPU / RAM / fan / network telemetry overlays
- Pump / fan RPM control or ARGB control
- Custom layout composition

If you want those, watch [reed-tpse](https://github.com/fadli0029/reed-tpse)
or open an issue there — the rendering pipeline for rasterising telemetry
into frames is the hard part, not the transport.

## License

MIT. See `LICENSE`.
