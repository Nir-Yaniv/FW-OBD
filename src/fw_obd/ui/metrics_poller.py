"""Background poller that keeps an SSH session open and streams live metrics."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QThread, pyqtSignal

from fw_obd.connection.ssh_handler import SSHConnectionError, SSHCredentials, SSHHandler
from fw_obd.services.metrics import DeviceMetrics, fetch_metrics

logger = logging.getLogger(__name__)


class MetricsPoller(QThread):
    """Polls one device's performance counters on an interval until stopped.

    Emits ``updated(DeviceMetrics)`` each cycle and ``failed(str)`` if the SSH
    session cannot be established or is lost.
    """

    updated = pyqtSignal(object)   # DeviceMetrics
    failed = pyqtSignal(str)

    def __init__(
        self,
        credentials: SSHCredentials,
        interval_secs: int = 5,
        vdoms: int = 1,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._credentials = credentials
        self._interval_ms = max(1, interval_secs) * 1000
        self._vdoms = vdoms
        self._running = True

    def run(self) -> None:
        handler = SSHHandler(self._credentials)
        try:
            handler.connect()
        except SSHConnectionError as exc:
            self.failed.emit(str(exc))
            return
        try:
            while self._running:
                try:
                    metrics = fetch_metrics(handler, vdoms=self._vdoms)
                    self.updated.emit(metrics)
                except SSHConnectionError as exc:
                    self.failed.emit(str(exc))
                    break
                except Exception as exc:  # noqa: BLE001 — keep the poller alive-ish
                    logger.warning("metrics poll error: %s", exc)
                # interruptible wait so stop() returns promptly
                if self._running:
                    self.msleep(self._interval_ms)
        finally:
            handler.disconnect()

    def stop(self) -> None:
        self._running = False
        self.wait(3000)
