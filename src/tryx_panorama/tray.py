from __future__ import annotations

from importlib.resources import files

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def _icon(name: str) -> QIcon:
    path = files("tryx_panorama.resources").joinpath(f"{name}.svg")
    return QIcon(str(path))


class TrayIcon(QObject):
    show_window_requested = Signal()
    upload_requested = Signal()
    daemon_action_requested = Signal(str)  # "start" | "stop" | "restart"
    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._icon_on = _icon("tryx-on")
        self._icon_off = _icon("tryx-off")

        self.tray = QSystemTrayIcon(self._icon_off, parent)
        self.tray.setToolTip("Tryx Panorama")
        self.tray.activated.connect(self._on_activated)

        menu = QMenu()
        act_show = QAction("Show window", menu)
        act_show.triggered.connect(self.show_window_requested.emit)
        menu.addAction(act_show)

        menu.addSeparator()

        act_upload = QAction("Upload media…", menu)
        act_upload.triggered.connect(self.upload_requested.emit)
        menu.addAction(act_upload)

        menu.addSeparator()

        daemon_menu = menu.addMenu("Daemon")
        for label, key in (("Start", "start"), ("Stop", "stop"), ("Restart", "restart")):
            a = QAction(label, daemon_menu)
            a.triggered.connect(lambda _=False, k=key: self.daemon_action_requested.emit(k))
            daemon_menu.addAction(a)

        menu.addSeparator()

        act_quit = QAction("Quit", menu)
        act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(act_quit)

        self.tray.setContextMenu(menu)
        self._menu = menu  # keep reference

    def show(self) -> None:
        self.tray.show()

    def set_daemon_active(self, active: bool) -> None:
        self.tray.setIcon(self._icon_on if active else self._icon_off)
        state = "running" if active else "stopped"
        self.tray.setToolTip(f"Tryx Panorama — daemon {state}")

    def show_message(self, title: str, body: str) -> None:
        self.tray.showMessage(title, body, self.tray.icon(), 4000)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window_requested.emit()
