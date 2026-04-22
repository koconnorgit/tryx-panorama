from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from tryx_panorama.backend import HUD_LABELS, Backend, BackendError, DeviceInfo, HudState
from tryx_panorama.workers import (
    DeleteWorker,
    DisplayWorker,
    HudClearWorker,
    HudConfigureWorker,
    UploadWorker,
    run_worker,
)

MEDIA_FILTER = (
    "Media files (*.mp4 *.mov *.webm *.mkv *.avi *.gif *.png *.jpg *.jpeg *.bmp);;"
    "Videos (*.mp4 *.mov *.webm *.mkv *.avi);;"
    "Images (*.png *.jpg *.jpeg *.bmp);;"
    "GIFs (*.gif);;"
    "All files (*)"
)

HUD_MAX_METRICS = 3

# 3×3 grid cell → (firmware position, firmware align).
# Laid out so clicking "top-left" picks Top/Left, visually matching where the
# overlay will render on the display.
HUD_PLACEMENT_GRID: list[list[tuple[str, str]]] = [
    [("Top", "Left"),    ("Top", "Center"),    ("Top", "Right")],
    [("Center", "Left"), ("Center", "Center"), ("Center", "Right")],
    [("Bottom", "Left"), ("Bottom", "Center"), ("Bottom", "Right")],
]


class MainWindow(QMainWindow):
    daemon_action_requested = Signal(str)  # "start" | "stop" | "restart"

    def __init__(self, backend: Backend):
        super().__init__()
        self.backend = backend
        self._busy = False

        self.setWindowTitle("Tryx Panorama")
        self.resize(680, 820)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        root.addWidget(self._build_device_group())
        root.addWidget(self._build_media_group(), 1)
        root.addWidget(self._build_display_group())
        root.addWidget(self._build_hud_group())
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

    def _build_hud_group(self) -> QGroupBox:
        g = QGroupBox("System HUD overlay")
        root = QVBoxLayout(g)

        # Metrics: 13 checkboxes in a 3-column grid. Hard-capped at 3 selected.
        metrics_label = QLabel(f"Metrics (pick up to {HUD_MAX_METRICS}):")
        root.addWidget(metrics_label)

        metrics_frame = QFrame()
        metrics_grid = QGridLayout(metrics_frame)
        metrics_grid.setContentsMargins(0, 0, 0, 0)
        self._hud_metric_boxes: dict[str, QCheckBox] = {}
        cols = 3
        for i, label in enumerate(HUD_LABELS):
            cb = QCheckBox(label)
            cb.toggled.connect(self._on_hud_metric_toggled)
            metrics_grid.addWidget(cb, i // cols, i % cols)
            self._hud_metric_boxes[label] = cb
        root.addWidget(metrics_frame)

        self.lbl_hud_metric_count = QLabel(f"Selected: 0 / {HUD_MAX_METRICS}")
        self.lbl_hud_metric_count.setStyleSheet("color: #888;")
        root.addWidget(self.lbl_hud_metric_count)

        # Render order is fixed by the cooler firmware, not by what we send —
        # we verified this empirically. Show a read-only list so the user can
        # see which metrics are currently selected without implying we control
        # the arrangement.
        order_note = QLabel(
            "Render order on the LCD is determined by the cooler firmware."
        )
        order_note.setStyleSheet("color: #888; font-style: italic;")
        order_note.setWordWrap(True)
        root.addWidget(order_note)

        # Placement + look row: 3×3 grid on the left, color/badges/interval/unit on the right.
        settings_row = QHBoxLayout()
        root.addLayout(settings_row)

        # Placement grid, styled to loosely resemble a 2:1 display.
        placement_box = QGroupBox("Placement")
        placement_lay = QVBoxLayout(placement_box)
        grid_frame = QFrame()
        grid_frame.setFrameShape(QFrame.StyledPanel)
        grid_frame.setMinimumSize(180, 90)
        grid_frame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        placement_grid = QGridLayout(grid_frame)
        placement_grid.setContentsMargins(4, 4, 4, 4)
        placement_grid.setSpacing(2)
        self._hud_placement_group = QButtonGroup(self)
        self._hud_placement_buttons: dict[tuple[str, str], QRadioButton] = {}
        for r, row in enumerate(HUD_PLACEMENT_GRID):
            for c, (pos, align) in enumerate(row):
                rb = QRadioButton()
                rb.setToolTip(f"{pos} {align}")
                rb.setFixedSize(40, 20)
                placement_grid.addWidget(rb, r, c, Qt.AlignCenter)
                self._hud_placement_group.addButton(rb)
                self._hud_placement_buttons[(pos, align)] = rb
        # Default: Top / Left
        self._hud_placement_buttons[("Top", "Left")].setChecked(True)
        placement_lay.addWidget(grid_frame)
        settings_row.addWidget(placement_box)

        # Right column: color, badges, interval, unit
        right_col = QVBoxLayout()
        settings_row.addLayout(right_col, 1)

        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Color:"))
        self.btn_hud_color = QPushButton("")
        self.btn_hud_color.setFixedWidth(60)
        self._hud_color = "#FFFFFF"
        self._apply_color_swatch()
        self.btn_hud_color.clicked.connect(self._choose_hud_color)
        color_row.addWidget(self.btn_hud_color)
        color_row.addStretch(1)
        right_col.addLayout(color_row)

        badges_row = QHBoxLayout()
        self.chk_hud_cpu_badge = QCheckBox("CPU name badge")
        self.chk_hud_gpu_badge = QCheckBox("GPU name badge")
        badges_row.addWidget(self.chk_hud_cpu_badge)
        badges_row.addWidget(self.chk_hud_gpu_badge)
        badges_row.addStretch(1)
        right_col.addLayout(badges_row)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("Push every:"))
        self.spin_hud_interval = QSpinBox()
        self.spin_hud_interval.setRange(1, 60)
        self.spin_hud_interval.setValue(5)
        self.spin_hud_interval.setSuffix(" s")
        interval_row.addWidget(self.spin_hud_interval)
        interval_row.addWidget(QLabel("Temp unit:"))
        self.combo_hud_unit = QComboBox()
        self.combo_hud_unit.addItems(["Celsius", "Fahrenheit"])
        interval_row.addWidget(self.combo_hud_unit)
        interval_row.addStretch(1)
        right_col.addLayout(interval_row)

        right_col.addStretch(1)

        # Bottom: Apply / Clear / status
        action_row = QHBoxLayout()
        self.btn_hud_apply = QPushButton("Apply HUD")
        self.btn_hud_apply.clicked.connect(self._apply_hud)
        self.btn_hud_clear = QPushButton("Clear HUD")
        self.btn_hud_clear.clicked.connect(self._clear_hud)
        action_row.addWidget(self.btn_hud_apply)
        action_row.addWidget(self.btn_hud_clear)
        action_row.addStretch(1)
        root.addLayout(action_row)

        self.lbl_hud_state = QLabel("HUD: unknown")
        self.lbl_hud_state.setStyleSheet("color: #888;")
        root.addWidget(self.lbl_hud_state)

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
        self.refresh_hud()

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

    # ---------- HUD ----------
    def _selected_hud_metrics(self) -> list[str]:
        """Checked metrics in HUD_LABELS iteration order. Firmware ignores array
        order when rendering, so we just send them in a stable order."""
        return [l for l, cb in self._hud_metric_boxes.items() if cb.isChecked()]

    def _on_hud_metric_toggled(self) -> None:
        """Enforce the firmware's 3-metric cap by disabling unchecked boxes once 3 are picked."""
        count = sum(1 for cb in self._hud_metric_boxes.values() if cb.isChecked())
        self.lbl_hud_metric_count.setText(f"Selected: {count} / {HUD_MAX_METRICS}")
        cap_reached = count >= HUD_MAX_METRICS
        for cb in self._hud_metric_boxes.values():
            if not cb.isChecked():
                cb.setEnabled(not cap_reached)

    def _apply_color_swatch(self) -> None:
        self.btn_hud_color.setText(self._hud_color)
        # Pick a contrasting text color so the hex stays readable.
        c = QColor(self._hud_color)
        luminance = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        fg = "#000000" if luminance > 140 else "#FFFFFF"
        self.btn_hud_color.setStyleSheet(
            f"background-color: {self._hud_color}; color: {fg};"
        )

    def _choose_hud_color(self) -> None:
        color = QColorDialog.getColor(QColor(self._hud_color), self, "HUD text color")
        if not color.isValid():
            return
        self._hud_color = color.name().upper()
        self._apply_color_swatch()

    def _selected_placement(self) -> tuple[str, str]:
        for key, rb in self._hud_placement_buttons.items():
            if rb.isChecked():
                return key
        return ("Top", "Left")

    def _apply_hud(self) -> None:
        metrics = self._selected_hud_metrics()
        if not metrics:
            self.statusBar().showMessage("Select at least one metric.", 4000)
            return
        if self._busy:
            self.statusBar().showMessage("Another operation is in progress.", 4000)
            return
        position, align = self._selected_placement()
        badges = []
        if self.chk_hud_cpu_badge.isChecked():
            badges.append("cpu")
        if self.chk_hud_gpu_badge.isChecked():
            badges.append("gpu")

        self._busy = True
        self.statusBar().showMessage("Applying HUD…")
        worker = HudConfigureWorker(
            self.backend,
            metrics=metrics,
            position=position,
            align=align,
            color=self._hud_color,
            badges=badges,
            interval=self.spin_hud_interval.value(),
            unit=self.combo_hud_unit.currentText(),
        )
        run_worker(self, worker, self._hud_apply_done)

    def _hud_apply_done(self, ok: bool, msg: str) -> None:
        self._busy = False
        self.statusBar().showMessage(msg, 6000)
        if not ok:
            QMessageBox.warning(self, "HUD apply failed", msg)
            return
        # Restart the daemon so it picks up the new push interval / metric set.
        # Harmless flicker; same pattern as other applied state changes.
        try:
            self.backend.daemon_restart()
        except BackendError as e:
            self.statusBar().showMessage(f"HUD saved but daemon restart failed: {e}", 6000)
        self.refresh_hud()

    def _clear_hud(self) -> None:
        if self._busy:
            return
        self._busy = True
        self.statusBar().showMessage("Clearing HUD…")
        worker = HudClearWorker(self.backend)
        run_worker(self, worker, self._hud_clear_done)

    def _hud_clear_done(self, ok: bool, msg: str) -> None:
        self._busy = False
        self.statusBar().showMessage(msg, 6000)
        if not ok:
            QMessageBox.warning(self, "HUD clear failed", msg)
            return
        try:
            self.backend.daemon_restart()
        except BackendError as e:
            self.statusBar().showMessage(f"HUD cleared but daemon restart failed: {e}", 6000)
        self.refresh_hud()

    def refresh_hud(self) -> None:
        try:
            state = self.backend.hud_status()
        except BackendError as e:
            self.statusBar().showMessage(f"HUD status failed: {e}", 6000)
            return
        self._hydrate_hud_controls(state)

    def _hydrate_hud_controls(self, state: HudState) -> None:
        for label, cb in self._hud_metric_boxes.items():
            cb.blockSignals(True)
            cb.setChecked(label in state.metrics)
            cb.blockSignals(False)
        self._on_hud_metric_toggled()

        # Placement
        key = (state.position, state.align)
        if key in self._hud_placement_buttons:
            self._hud_placement_buttons[key].setChecked(True)

        # Color
        self._hud_color = state.color or "#FFFFFF"
        self._apply_color_swatch()

        # Badges
        self.chk_hud_cpu_badge.setChecked("CPU Badge" in state.badges)
        self.chk_hud_gpu_badge.setChecked("GPU Badge" in state.badges)

        # Interval / unit
        self.spin_hud_interval.setValue(state.push_interval_sec)
        idx = self.combo_hud_unit.findText(state.temperature_unit)
        if idx >= 0:
            self.combo_hud_unit.setCurrentIndex(idx)

        # Status line
        if state.enabled and state.metrics:
            pretty = ", ".join(state.metrics)
            self.lbl_hud_state.setText(
                f"HUD: on · {pretty} · {state.position}/{state.align} · every {state.push_interval_sec}s"
            )
            self.lbl_hud_state.setStyleSheet("color: #33cc66;")
        else:
            self.lbl_hud_state.setText("HUD: off")
            self.lbl_hud_state.setStyleSheet("color: #888;")

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
