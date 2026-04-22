"""Subprocess wrapper around the reed-tpse CLI."""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

SERVICE_NAME = "tryx-panorama.service"

BINARY_SEARCH_PATHS = [
    "reed-tpse",
    str(Path.home() / ".local/bin/reed-tpse"),
    "/usr/local/bin/reed-tpse",
    "/home/kevin/tryx/reed-tpse/build/reed-tpse",
]


def find_reed_tpse() -> str | None:
    for candidate in BINARY_SEARCH_PATHS:
        resolved = shutil.which(candidate) if "/" not in candidate else (candidate if Path(candidate).is_file() else None)
        if resolved:
            return resolved
    return None


@dataclass
class DeviceInfo:
    product: str = ""
    os: str = ""
    serial: str = ""
    app_version: str = ""
    firmware: str = ""
    hardware: str = ""
    attributes: list[str] = field(default_factory=list)
    port: str = ""


HUD_LABELS: list[str] = [
    "CPU Temperature",
    "CPU Frequency",
    "CPU Usage",
    "CPU Voltage",
    "GPU Temperature",
    "GPU Frequency",
    "GPU Usage",
    "GPU Voltage",
    "Motherboard Temperature",
    "Memory Frequency",
    "Memory Utilization",
    "Hard Disk Temperature",
    "Date & Time",
]


@dataclass
class HudState:
    enabled: bool = False
    metrics: list[str] = field(default_factory=list)
    position: str = "Top"
    align: str = "Left"
    color: str = "#FFFFFF"
    badges: list[str] = field(default_factory=list)  # "CPU Badge", "GPU Badge"
    push_interval_sec: int = 5
    temperature_unit: str = "Celsius"
    cpu_name: str = ""
    gpu_name: str = ""


class BackendError(RuntimeError):
    pass


class Backend:
    def __init__(self, binary: str | None = None):
        self.binary = binary or find_reed_tpse()
        if not self.binary:
            raise BackendError(
                "reed-tpse binary not found on PATH. Install it or set binary path explicitly."
            )

    def _run(self, args: list[str], timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.binary, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def info(self) -> DeviceInfo:
        r = self._run(["info"])
        if r.returncode != 0:
            raise BackendError(r.stderr.strip() or "reed-tpse info failed")
        return _parse_info(r.stdout)

    def list_media(self) -> list[str]:
        r = self._run(["list"])
        if r.returncode != 0:
            raise BackendError(r.stderr.strip() or "reed-tpse list failed")
        files: list[str] = []
        for line in r.stdout.splitlines():
            line = line.rstrip()
            if line.startswith("  ") and line.strip():
                files.append(line.strip())
        return files

    def set_display(self, files: list[str], ratio: str = "2:1", brightness: int | None = None) -> None:
        args = ["display", *files, "--ratio", ratio]
        if brightness is not None:
            args += ["--brightness", str(brightness)]
        r = self._run(args, timeout=60.0)
        if r.returncode != 0:
            raise BackendError(r.stderr.strip() or "reed-tpse display failed")

    def set_brightness(self, value: int) -> None:
        r = self._run(["brightness", str(value)])
        if r.returncode != 0:
            raise BackendError(r.stderr.strip() or "reed-tpse brightness failed")

    def delete(self, files: list[str]) -> None:
        r = self._run(["delete", *files], timeout=60.0)
        if r.returncode != 0:
            raise BackendError(r.stderr.strip() or "reed-tpse delete failed")

    def upload(self, path: str) -> None:
        """Synchronous upload. Wrap in a worker thread for UI code."""
        r = self._run(["upload", path], timeout=600.0)
        if r.returncode != 0:
            raise BackendError(r.stderr.strip() or r.stdout.strip() or "upload failed")

    def daemon_status(self) -> bool:
        """True if the systemd user service is active."""
        r = subprocess.run(
            ["systemctl", "--user", "is-active", SERVICE_NAME],
            capture_output=True, text=True, check=False,
        )
        return r.stdout.strip() == "active"

    def service_installed(self) -> bool:
        unit = Path.home() / ".config/systemd/user" / SERVICE_NAME
        return unit.is_file()

    def daemon_start(self) -> None:
        r = subprocess.run(
            ["systemctl", "--user", "start", SERVICE_NAME],
            capture_output=True, text=True, check=False,
        )
        if r.returncode != 0:
            raise BackendError(r.stderr.strip() or "failed to start daemon")

    def daemon_stop(self) -> None:
        r = subprocess.run(
            ["systemctl", "--user", "stop", SERVICE_NAME],
            capture_output=True, text=True, check=False,
        )
        if r.returncode != 0:
            raise BackendError(r.stderr.strip() or "failed to stop daemon")

    def daemon_restart(self) -> None:
        r = subprocess.run(
            ["systemctl", "--user", "restart", SERVICE_NAME],
            capture_output=True, text=True, check=False,
        )
        if r.returncode != 0:
            raise BackendError(r.stderr.strip() or "failed to restart daemon")

    def daemon_enable(self, enable: bool) -> None:
        verb = "enable" if enable else "disable"
        subprocess.run(
            ["systemctl", "--user", verb, SERVICE_NAME],
            capture_output=True, text=True, check=False,
        )

    def hud_configure(
        self,
        metrics: list[str],
        position: str,
        align: str,
        color: str,
        badges: list[str],
        interval: int,
        unit: str,
    ) -> None:
        """Apply HUD config via `reed-tpse hud configure`. Raises BackendError on failure.

        Badge names are the short forms "cpu" / "gpu" that the CLI accepts.
        """
        if not metrics:
            raise BackendError("Select at least one metric.")
        if len(metrics) > 3:
            raise BackendError(f"Firmware allows at most 3 metrics; got {len(metrics)}.")
        args = [
            "hud", "configure",
            "--metrics", ",".join(metrics),
            "--position", position,
            "--align", align,
            "--color", color,
            "--badges", ",".join(badges) if badges else "none",
            "--interval", str(interval),
            "--unit", unit,
        ]
        r = self._run(args, timeout=30.0)
        if r.returncode != 0:
            raise BackendError(r.stderr.strip() or r.stdout.strip() or "hud configure failed")

    def hud_clear(self) -> None:
        r = self._run(["hud", "clear"], timeout=15.0)
        if r.returncode != 0:
            raise BackendError(r.stderr.strip() or "hud clear failed")

    def hud_status(self) -> HudState:
        r = self._run(["hud", "status"], timeout=10.0)
        if r.returncode != 0:
            raise BackendError(r.stderr.strip() or "hud status failed")
        return _parse_hud_status(r.stdout)


_FIELDS = {
    "Product": "product",
    "OS": "os",
    "Serial": "serial",
    "App Version": "app_version",
    "Firmware": "firmware",
    "Hardware": "hardware",
}


_BRACKET_RE = re.compile(r"\[([^\]]+)\]")


def _parse_hud_status(stdout: str) -> HudState:
    """Parse the `hud status` stdout block into a HudState.

    Format (see cli/main.cpp:cmd_hud status branch):
        HUD: enabled|disabled
          Metrics: [X] [Y] [Z]            (or "(none)")
          Position: Top
          Align: Left
          Color: #FFFFFF
          Badges: [CPU Badge] [GPU Badge]  (or "(none)")
          Push interval: 5s
          Temperature unit: Celsius
          CPU: <name> | (auto)
          GPU: <name> | (auto)
    """
    state = HudState()
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("HUD:"):
            state.enabled = stripped.split(":", 1)[1].strip() == "enabled"
        elif stripped.startswith("Metrics:"):
            state.metrics = _BRACKET_RE.findall(stripped)
        elif stripped.startswith("Position:"):
            state.position = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Align:"):
            state.align = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Color:"):
            state.color = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Badges:"):
            state.badges = _BRACKET_RE.findall(stripped)
        elif stripped.startswith("Push interval:"):
            raw = stripped.split(":", 1)[1].strip().rstrip("s")
            try:
                state.push_interval_sec = int(raw)
            except ValueError:
                pass
        elif stripped.startswith("Temperature unit:"):
            state.temperature_unit = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("CPU:"):
            val = stripped.split(":", 1)[1].strip()
            state.cpu_name = "" if val == "(auto)" else val
        elif stripped.startswith("GPU:"):
            val = stripped.split(":", 1)[1].strip()
            state.gpu_name = "" if val == "(auto)" else val
    return state


def _parse_info(stdout: str) -> DeviceInfo:
    info = DeviceInfo()
    for line in stdout.splitlines():
        line = line.rstrip()
        m = re.match(r"Found device at (.+)", line)
        if m:
            info.port = m.group(1).strip()
            continue
        for label, attr in _FIELDS.items():
            prefix = f"  {label}: "
            if line.startswith(prefix):
                setattr(info, attr, line[len(prefix):].strip())
                break
        if line.startswith("  Attributes: "):
            info.attributes = [a.strip() for a in line[len("  Attributes: "):].split(",")]
    return info
