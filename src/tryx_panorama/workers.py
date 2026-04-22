from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Signal

from tryx_panorama.backend import Backend, BackendError


class _BaseWorker(QObject):
    finished = Signal(bool, str)  # success, message


class UploadWorker(_BaseWorker):
    def __init__(self, backend: Backend, path: str):
        super().__init__()
        self.backend = backend
        self.path = path

    def run(self) -> None:
        try:
            self.backend.upload(self.path)
        except BackendError as e:
            self.finished.emit(False, str(e))
            return
        self.finished.emit(True, f"Uploaded {self.path}")


class DeleteWorker(_BaseWorker):
    def __init__(self, backend: Backend, files: list[str]):
        super().__init__()
        self.backend = backend
        self.files = files

    def run(self) -> None:
        try:
            self.backend.delete(self.files)
        except BackendError as e:
            self.finished.emit(False, str(e))
            return
        self.finished.emit(True, f"Deleted {', '.join(self.files)}")


class DisplayWorker(_BaseWorker):
    def __init__(self, backend: Backend, files: list[str], ratio: str, brightness: int):
        super().__init__()
        self.backend = backend
        self.files = files
        self.ratio = ratio
        self.brightness = brightness

    def run(self) -> None:
        try:
            self.backend.set_display(self.files, ratio=self.ratio, brightness=self.brightness)
        except BackendError as e:
            self.finished.emit(False, str(e))
            return
        self.finished.emit(True, f"Displaying {', '.join(self.files)}")


class HudConfigureWorker(_BaseWorker):
    def __init__(
        self,
        backend: Backend,
        metrics: list[str],
        position: str,
        align: str,
        color: str,
        badges: list[str],
        interval: int,
        unit: str,
    ):
        super().__init__()
        self.backend = backend
        self.metrics = metrics
        self.position = position
        self.align = align
        self.color = color
        self.badges = badges
        self.interval = interval
        self.unit = unit

    def run(self) -> None:
        try:
            self.backend.hud_configure(
                self.metrics, self.position, self.align, self.color,
                self.badges, self.interval, self.unit,
            )
        except BackendError as e:
            self.finished.emit(False, str(e))
            return
        self.finished.emit(
            True, f"HUD applied ({len(self.metrics)} metrics, push every {self.interval}s)"
        )


class HudClearWorker(_BaseWorker):
    def __init__(self, backend: Backend):
        super().__init__()
        self.backend = backend

    def run(self) -> None:
        try:
            self.backend.hud_clear()
        except BackendError as e:
            self.finished.emit(False, str(e))
            return
        self.finished.emit(True, "HUD cleared")


# QObjects without a Qt parent and no Python reference get garbage-collected by
# PySide6 before their slots run. We anchor every in-flight worker/thread pair
# on a QObject's _active_jobs set so the Python refs survive until completion.
_ACTIVE_JOBS_ATTR = "_tryx_active_jobs"


def run_worker(parent: QObject, worker: _BaseWorker, done_slot) -> QThread:
    thread = QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(done_slot)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)

    active = getattr(parent, _ACTIVE_JOBS_ATTR, None)
    if active is None:
        active = set()
        setattr(parent, _ACTIVE_JOBS_ATTR, active)
    job = (thread, worker)
    active.add(job)
    thread.finished.connect(lambda j=job, a=active: a.discard(j))

    thread.start()
    return thread
