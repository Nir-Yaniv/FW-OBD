"""Background worker for SSH device scans (keeps UI responsive)."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal

from fw_obd.connection.ssh_handler import SSHCredentials, SSHConnectionError
from fw_obd.db.database import Database
from fw_obd.services.device_scan import ScanError, ScanResult, run_quick_audit_scan


class DeviceScanWorker(QThread):
    progress = pyqtSignal(str)
    finished_ok = pyqtSignal(object)  # ScanResult
    failed = pyqtSignal(str)          # could not connect — device unreachable
    scan_error = pyqtSignal(str)      # connected fine, but the scan itself broke

    def __init__(
        self,
        credentials: SSHCredentials,
        db: Database,
        device_id: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._credentials = credentials
        self._db = db
        self._device_id = device_id

    def run(self) -> None:
        try:
            result = run_quick_audit_scan(
                self._credentials,
                self._db,
                self._device_id,
                progress=self.progress.emit,
            )
            self.finished_ok.emit(result)
        except ScanError as exc:
            self.scan_error.emit(str(exc))
        except SSHConnectionError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.scan_error.emit(f"Scan failed after connecting: {exc}")
