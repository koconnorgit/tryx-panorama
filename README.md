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
./scripts/install.sh
```

That single command:

1. Checks for runtime/build dependencies (and prints the right `pacman` /
   `apt` command if anything's missing — doesn't auto-install them).
2. Clones + builds [reed-tpse](https://github.com/koconnorgit/reed-tpse)
   (a fork of [@fadli0029](https://github.com/fadli0029)'s original,
   see [Which reed-tpse gets installed](#which-reed-tpse-gets-installed))
   into `~/.local/share/tryx-panorama/reed-tpse` and drops the binary at
   `~/.local/bin/reed-tpse`.
3. Installs the udev rule (`/etc/udev/rules.d/71-tryx-panorama.rules`) —
   prompts for `sudo` once.
4. Installs the `tryx-panorama.service` systemd **user** unit at
   `~/.config/systemd/user/`, pointing at the reed-tpse binary it just
   built.
5. Installs the `tryx-panorama` launcher wrapper at `~/.local/bin/`.
6. Installs the `.desktop` entry at `~/.local/share/applications/`.
7. Enables and starts the daemon.

Re-running `./scripts/install.sh` is safe — it updates reed-tpse from its
configured remote via `git pull`, re-applies the rest, and restarts the
daemon.

If you prefer to run individual steps, the orchestrator is a thin wrapper
around:

- `scripts/install-reed-tpse.sh` — just reed-tpse clone + build + install
- `scripts/install-udev.sh` — just the udev rule
- `scripts/install-service.sh` — just the systemd user unit

### Which reed-tpse gets installed

The installer pulls from
[**koconnorgit/reed-tpse**](https://github.com/koconnorgit/reed-tpse) by
default — a fork of
[fadli0029/reed-tpse](https://github.com/fadli0029/reed-tpse) that adds a
reconnect loop to the keepalive daemon (upstream silently no-ops on a
dead serial fd after USB suspend/resume or `/dev/ttyACM*` renumbering, so
`Restart=on-failure` never fires and the LCD goes blank until the next
manual restart).

To pull from the upstream repo instead:

```bash
REED_TPSE_REMOTE=https://github.com/fadli0029/reed-tpse.git ./scripts/install.sh
```

Any fork URL works — set `REED_TPSE_REMOTE` to point wherever you want.
If you've previously installed from a different remote, the installer
retargets the existing clone's `origin` and re-fetches before pulling, so
switching is a single re-run.

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

## System HUD overlay

The GUI exposes the cooler's native telemetry HUD: pick up to 3 metrics
from the firmware's label set (CPU / GPU temp / usage / freq / voltage,
motherboard temp, memory, disk temp, date & time), choose one of the 9
anchor points on a 3×3 placement grid, set the text color, toggle
CPU/GPU name badges, and set the push interval. Apply writes the config
via `reed-tpse hud configure` and restarts the keepalive daemon so it
starts pushing fresh values at the new cadence.

The cooler firmware renders the overlay natively — no host-side frame
compositing — so the feature is essentially free at the transport
layer. One caveat surfaced in the UI: **the render order of the
selected metrics is fixed by the firmware**, not by the order they
appear in the array we send. The UI shows a note to that effect rather
than pretending we have an ordering knob.

## What this does *not* do (yet)

The same things reed-tpse doesn't do yet:

- Pump / fan RPM control or ARGB control
- Screen Splitting mode (6-metric, two-zone layout)
- Arbitrary pixel-level overlay placement (firmware only exposes the
  9 anchor points)

If you want those, watch [reed-tpse](https://github.com/fadli0029/reed-tpse)
or open an issue there.

## License

MIT. See `LICENSE`.
