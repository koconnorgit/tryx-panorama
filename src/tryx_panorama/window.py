from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from tryx_panorama.backend import Backend, BackendError, DeviceInfo
from tryx_panorama.workers import DeleteWorker, DisplayWorker, UploadWorker, run_worker

MEDIA_FILTER = (
    "Media files (*.mp4 *.mov *.webm *.mkv *.avi *.gif *.png *.jpg *.jpeg *.bmp);;"
    "Videos (*.mp4 *.mov *.webm *.mkv *.avi);;"
    "Images (*.png *.jpg *.jpeg *.bmp);;"
    "GIFs (*.gif);;"
    "All files (*)"
)


class MainWindow(QMainWindow):
    daemon_action_requested = Signal(str)  # "start" | "stop" | "restart"

    def __init__(self, backend: Backend):
        super().__init__()
        self.backend = backend
        self._busy = False

        self.setWindowTitle("Tryx Panorama")
        self.resize(620, 520)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(self._build_device_group())
        root.addWidget(self._build_media_group(), 1)
        root.addWidget(self._build_display_group())
        root.addWidget(self._build_daemon_group())

        self.setStatusBar(QStatusBar())

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self.refresh_daemon_status)
        self._refresh_timer.start()

    # ---------- UI sections ----------
    def _build_device_group(self) -> QGroupBox:
        g = QGroupBox("Device")
        form = QFormLayout(g)
        self.lbl_product = QLabel("—")
        self.lbl_firmware = QLabel("—")
        self.lbl_serial = QLabel("—")
        self.lbl_port = QLabel("—")
        form.addRow("Product:", self.lbl_product)
        form.addRow("Firmware:", self.lbl_firmware)
        form.addRow("Serial:", self.lbl_serial)
        form.addRow("Port:", self.lbl_port)

        row = QHBoxLayout()
        self.btn_refresh_info = QPushButton("Refresh")
        self.btn_refresh_info.clicked.connect(self.refresh_device)
        row.addStretch(1)
        row.addWidget(self.btn_refresh_info)
        form.addRow(row)
        return g

    def _build_media_group(self) -> QGroupBox:
        g = QGroupBox("Media on device")
        lay = QVBoxLayout(g)

        self.media_list = QListWidget()
        self.media_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.media_list.itemDoubleClicked.connect(self._display_selected)
        lay.addWidget(self.media_list)

        row = QHBoxLayout()
        self.btn_upload = QPushButton("Upload…")
        self.btn_upload.clicked.connect(self._upload_dialog)
        self.btn_refresh = QPushButton("Refresh list")
        self.btn_refresh.clicked.connect(self.refresh_media)
        self.btn_display = QPushButton("Set as display")
        self.btn_display.clicked.connect(self._display_selected)
        self.btn_delete = QPushButton("Delete")
        self.btn_delete.clicked.connect(self._delete_selected)
        for b in (self.btn_upload, self.btn_refresh, self.btn_display, self.btn_delete):
            row.addWidget(b)
        lay.addLayout(row)
        return g

    def _build_display_group(self) -> QGroupBox:
        g = QGroupBox("Display settings")
        form = QFormLayout(g)

        bright_row = QHBoxLayout()
        self.slider_brightness = QSlider(Qt.Horizontal)
        self.slider_brightness.setRange(0, 100)
        self.slider_brightness.setValue(80)
        self.slider_brightness.setTickInterval(10)
        self.slider_brightness.setTickPosition(QSlider.TicksBelow)
        self.lbl_brightness = QLabel("80")
        self.slider_brightness.valueChanged.connect(lambda v: self.lbl_brightness.setText(str(v)))
        self.btn_apply_brightness = QPushButton("Apply")
        self.btn_apply_brightness.clicked.connect(self._apply_brightness)
        bright_row.addWidget(self.slider_brightness, 1)
        bright_row.addWidget(self.lbl_brightness)
        bright_row.addWidget(self.btn_apply_brightness)
        form.addRow("Brightness:", bright_row)

        self.chk_square = QCheckBox("1:1 aspect (square pump LCDs)")
        form.addRow("Aspect:", self.chk_square)
        return g

    def _build_daemon_group(self) -> QGroupBox:
        g = QGroupBox("Keepalive daemon")
        row = QHBoxLayout(g)
        self.lbl_daemon_state = QLabel("unknown")
        self.lbl_daemon_state.setStyleSheet("font-weight: bold;")
        row.addWidget(QLabel("Status:"))
        row.addWidget(self.lbl_daemon_state)
        row.addStretch(1)

        for label, action in (("Start", "start"), ("Stop", "stop"), ("Restart", "restart")):
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, a=action: self.daemon_action_requested.emit(a))
            row.addWidget(b)
        return g

    # ---------- public ----------
    def refresh_all(self) -> None:
        self.refresh_device()
        self.refresh_media()
        self.refresh_daemon_status()

    def refresh_device(self) -> None:
        try:
            info = self.backend.info()
        except BackendError as e:
            self._set_device_info(DeviceInfo())
            self.statusBar().showMessage(f"Device error: {e}", 6000)
            return
        self._set_device_info(info)
        self.statusBar().showMessage("Device info updated.", 3000)

    def refresh_media(self) -> None:
        try:
            files = self.backend.list_media()
        except BackendError as e:
            self.statusBar().showMessage(f"List failed: {e}", 6000)
            return
        self.media_list.clear()
        for f in files:
            QListWidgetItem(f, self.media_list)

    def refresh_daemon_status(self) -> None:
        active = self.backend.daemon_status()
        self._set_daemon_label(active)

    def _set_daemon_label(self, active: bool) -> None:
        if active:
            self.lbl_daemon_state.setText("running")
            self.lbl_daemon_state.setStyleSheet("color: #33cc66; font-weight: bold;")
        else:
            self.lbl_daemon_state.setText("stopped")
            self.lbl_daemon_state.setStyleSheet("color: #cc5533; font-weight: bold;")

    def _set_device_info(self, info: DeviceInfo) -> None:
        self.lbl_product.setText(info.product or "—")
        self.lbl_firmware.setText(f"{info.firmware} (app {info.app_version})" if info.firmware else "—")
        self.lbl_serial.setText(info.serial or "—")
        self.lbl_port.setText(info.port or "—")

    # ---------- actions ----------
    def _upload_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Upload media", "", MEDIA_FILTER)
        if not path:
            return
        self.upload_file(path)

    def upload_file(self, path: str) -> None:
        if self._busy:
            self.statusBar().showMessage("Another operation is in progress.", 4000)
            return
        self._busy = True
        self.statusBar().showMessage(f"Uploading {Path(path).name}…")
        worker = UploadWorker(self.backend, path)
        run_worker(self, worker, self._upload_done)

    def _upload_done(self, ok: bool, msg: str) -> None:
        self._busy = False
        self.statusBar().showMessage(msg, 6000)
        if ok:
            self.refresh_media()
        else:
            QMessageBox.warning(self, "Upload failed", msg)

    def _display_selected(self) -> None:
        items = self.media_list.selectedItems()
        if not items:
            self.statusBar().showMessage("Select one or more media items first.", 4000)
            return
        if self._busy:
            return
        files = [i.text() for i in items]
        ratio = "1:1" if self.chk_square.isChecked() else "2:1"
        brightness = self.slider_brightness.value()
        self._busy = True
        self.statusBar().showMessage(f"Setting display to {', '.join(files)}…")
        worker = DisplayWorker(self.backend, files, ratio, brightness)
        run_worker(self, worker, self._display_done)

    def _display_done(self, ok: bool, msg: str) -> None:
        self._busy = False
        self.statusBar().showMessage(msg, 6000)
        if not ok:
            QMessageBox.warning(self, "Display failed", msg)

    def _delete_selected(self) -> None:
        items = self.media_list.selectedItems()
        if not items:
            return
        files = [i.text() for i in items]
        if QMessageBox.question(
            self, "Delete", f"Delete {len(files)} file(s) from device?",
            QMessageBox.Yes | QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        if self._busy:
            return
        self._busy = True
        self.statusBar().showMessage(f"Deleting {len(files)} file(s)…")
        worker = DeleteWorker(self.backend, files)
        run_worker(self, worker, self._delete_done)

    def _delete_done(self, ok: bool, msg: str) -> None:
        self._busy = False
        self.statusBar().showMessage(msg, 6000)
        if ok:
            self.refresh_media()
        else:
            QMessageBox.warning(self, "Delete failed", msg)

    def _apply_brightness(self) -> None:
        value = self.slider_brightness.value()
        try:
            self.backend.set_brightness(value)
        except BackendError as e:
            QMessageBox.warning(self, "Brightness failed", str(e))
            return
        self.statusBar().showMessage(f"Brightness set to {value}.", 4000)

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()
