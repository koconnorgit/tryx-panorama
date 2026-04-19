from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from tryx_panorama.backend import Backend, BackendError
from tryx_panorama.tray import TrayIcon
from tryx_panorama.window import MainWindow


def _setup_service_notice(backend: Backend) -> str | None:
    """Return a user-visible warning if the systemd user service isn't installed yet."""
    if backend.service_installed():
        return None
    return (
        "The keepalive daemon's systemd user service is not installed.\n\n"
        "Run: ./scripts/install-service.sh\n"
        "(see project README)"
    )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Tryx Panorama")
    app.setDesktopFileName("tryx-panorama")
    app.setQuitOnLastWindowClosed(False)

    try:
        backend = Backend()
    except BackendError as e:
        QMessageBox.critical(None, "Tryx Panorama", str(e))
        return 1

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None, "Tryx Panorama",
            "No system tray available. KDE Plasma tray should be present on this session.",
        )
        return 1

    window = MainWindow(backend)
    tray = TrayIcon(parent=app)
    tray.show()

    def on_show_window() -> None:
        window.show()
        window.raise_()
        window.activateWindow()

    def on_upload() -> None:
        window._upload_dialog()
        on_show_window()

    def on_daemon_action(action: str) -> None:
        try:
            if action == "start":
                backend.daemon_start()
            elif action == "stop":
                backend.daemon_stop()
            elif action == "restart":
                backend.daemon_restart()
        except BackendError as e:
            tray.show_message("Daemon error", str(e))
            return
        QTimer.singleShot(500, refresh_daemon)

    def refresh_daemon() -> None:
        active = backend.daemon_status()
        tray.set_daemon_active(active)
        window._set_daemon_label(active)

    tray.show_window_requested.connect(on_show_window)
    tray.upload_requested.connect(on_upload)
    tray.daemon_action_requested.connect(on_daemon_action)
    tray.quit_requested.connect(app.quit)
    window.daemon_action_requested.connect(on_daemon_action)

    status_timer = QTimer(app)
    status_timer.setInterval(5000)
    status_timer.timeout.connect(refresh_daemon)
    status_timer.start()

    QTimer.singleShot(0, refresh_daemon)
    QTimer.singleShot(0, window.refresh_all)

    notice = _setup_service_notice(backend)
    if notice:
        QTimer.singleShot(500, lambda: tray.show_message("Daemon not installed", notice))

    window.show()  # show on first launch
    return app.exec()
