"""Dashboard page — shows all managed devices with health status."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from fw_obd.db.database import Database
from fw_obd.ui.audit_report_dialog import AuditReportDialog
from fw_obd.ui.connect_dialog import ConnectDialog
from fw_obd.ui.import_devices_dialog import ImportDevicesDialog
from fw_obd.ui.scan_worker import DeviceScanWorker

# Status colour map
STATUS_COLORS = {
    "healthy": "#27ae60",
    "warning": "#f39c12",
    "critical": "#e74c3c",
    "offline": "#7f8c8d",
    "unknown": "#95a5a6",
}

STATUS_LABELS = {
    "healthy": "All Clear",
    "warning": "Warning",
    "critical": "Critical",
    "offline": "Offline",
    "unknown": "Unknown",
}


class DeviceCard(QFrame):
    """A single device summary card shown on the dashboard grid."""

    connect_requested = pyqtSignal(int, str)   # device_id, management_ip

    def __init__(self, device_row: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._device = device_row
        self._build()

    def _build(self) -> None:
        self.setObjectName("deviceCard")
        self.setFixedSize(260, 160)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        status = self._device.get("status", "unknown")
        color = STATUS_COLORS.get(status, STATUS_COLORS["unknown"])
        status_label = STATUS_LABELS.get(status, status.title())

        # Header row: name + status dot
        header = QHBoxLayout()
        name_lbl = QLabel(self._device.get("name", "Unknown"))
        name_lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color}; font-size: 16px;")
        header.addWidget(name_lbl)
        header.addStretch()
        header.addWidget(dot)
        layout.addLayout(header)

        # Vendor + model
        vendor_model = f"{self._device.get('vendor', '')} {self._device.get('model', '')}".strip()
        layout.addWidget(QLabel(vendor_model or "Unknown model"))

        # IP + location
        layout.addWidget(QLabel(f"IP: {self._device.get('management_ip', '-')}"))
        loc = self._device.get("location", "")
        if loc:
            layout.addWidget(QLabel(f"Location: {loc}"))

        # Status text
        status_text = QLabel(status_label)
        status_text.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(status_text)

        layout.addStretch()

        # Connect button
        connect_btn = QPushButton("Connect")
        connect_btn.clicked.connect(self._on_connect)
        layout.addWidget(connect_btn)

        self.setStyleSheet("""
            #deviceCard {
                background-color: #ffffff;
                border: 1px solid #dde3e9;
                border-radius: 8px;
            }
            #deviceCard:hover {
                border-color: #2980b9;
            }
        """)

    def _on_connect(self) -> None:
        self.connect_requested.emit(
            self._device.get("id", 0),
            self._device.get("management_ip", ""),
        )


class AddDeviceDialog(QDialog):
    """Simple dialog to add a new device manually."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Device")
        self.setMinimumWidth(360)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name = QLineEdit()
        self._ip = QLineEdit()
        self._ip.setPlaceholderText("e.g. 192.168.1.1")
        self._location = QLineEdit()
        self._region = QLineEdit()

        form.addRow("Device Name *", self._name)
        form.addRow("Management IP *", self._ip)
        form.addRow("Location", self._location)
        form.addRow("Region", self._region)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> dict:
        return {
            "name": self._name.text().strip(),
            "management_ip": self._ip.text().strip(),
            "location": self._location.text().strip(),
            "region": self._region.text().strip(),
        }

    def is_valid(self) -> bool:
        return bool(self._name.text().strip() and self._ip.text().strip())


class DashboardWidget(QWidget):
    """
    Dashboard page — shows a grid of DeviceCard widgets.
    Toolbar at top: Add Device, Import CSV, search filter.
    """

    status_message = pyqtSignal(str)

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._scan_worker: DeviceScanWorker | None = None
        self._build()
        self._load_devices()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # -- Toolbar --
        toolbar = QHBoxLayout()
        title = QLabel("Device Dashboard")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search devices...")
        self._search.setFixedWidth(220)
        self._search.textChanged.connect(self._filter_cards)
        toolbar.addWidget(self._search)

        add_btn = QPushButton("+ Add Device")
        add_btn.clicked.connect(self._add_device)
        toolbar.addWidget(add_btn)

        import_btn = QPushButton("Import CSV")
        import_btn.clicked.connect(self._import_devices)
        toolbar.addWidget(import_btn)

        root.addLayout(toolbar)

        # -- Scroll area with card grid --
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._card_container = QWidget()
        self._card_grid = QGridLayout(self._card_container)
        self._card_grid.setSpacing(16)
        self._card_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._card_container)
        root.addWidget(scroll, stretch=1)

        self._cards: list[DeviceCard] = []

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def _load_devices(self) -> None:
        devices = self._db.list_devices()
        self._render_cards([dict(row) for row in devices])

    def _render_cards(self, devices: list[dict]) -> None:
        # Clear existing
        for card in self._cards:
            self._card_grid.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

        if not devices:
            empty = QLabel("No devices yet. Click '+ Add Device' to get started.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #7f8c8d; font-size: 14px; padding: 40px;")
            self._card_grid.addWidget(empty, 0, 0)
            return

        cols = 4
        for idx, device_row in enumerate(devices):
            card = DeviceCard(device_row)
            card.connect_requested.connect(self._on_connect_device)
            self._cards.append(card)
            self._card_grid.addWidget(card, idx // cols, idx % cols)

    def _filter_cards(self, text: str) -> None:
        query = text.lower()
        for card in self._cards:
            name = card._device.get("name", "").lower()
            ip = card._device.get("management_ip", "").lower()
            card.setVisible(query in name or query in ip)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _add_device(self) -> None:
        dialog = AddDeviceDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.is_valid():
            values = dialog.values()
            self._db.upsert_device(
                name=values["name"],
                management_ip=values["management_ip"],
                location=values["location"],
                region=values["region"],
            )
            self._load_devices()

    def _import_devices(self) -> None:
        dialog = ImportDevicesDialog(self._db, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_devices()
            self.status_message.emit("Devices imported from CSV")

    def _on_connect_device(self, device_id: int, management_ip: str) -> None:
        from PyQt6.QtWidgets import QMessageBox

        row = self._db.get_device(device_id)
        device_name = row["name"] if row else management_ip

        cred_dialog = ConnectDialog(management_ip, device_name, self)
        if cred_dialog.exec() != QDialog.DialogCode.Accepted or not cred_dialog.is_valid():
            return

        if self._scan_worker and self._scan_worker.isRunning():
            QMessageBox.warning(self, "Scan in progress", "Wait for the current scan to finish.")
            return

        self.status_message.emit(f"Connecting to {management_ip}…")
        self._scan_worker = DeviceScanWorker(
            cred_dialog.credentials(),
            self._db,
            device_id,
            self,
        )
        self._scan_worker.progress.connect(self.status_message.emit)
        self._scan_worker.finished_ok.connect(
            lambda result: self._on_scan_finished(device_id, result)
        )
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.start()

    def _on_scan_finished(self, device_id: int, result: object) -> None:
        from fw_obd.services.device_scan import ScanResult

        assert isinstance(result, ScanResult)
        self._load_devices()
        self.status_message.emit(
            f"Audit complete — {len(result.report.findings)} finding(s), "
            f"status: {result.report.overall_status}"
        )
        AuditReportDialog(result.report, self).exec()

    def _on_scan_failed(self, message: str) -> None:
        from PyQt6.QtWidgets import QMessageBox

        self.status_message.emit("Connection failed")
        QMessageBox.critical(self, "Connection failed", message)
        self._db.log_action(
            action="connect",
            description=message,
            success=False,
            error_detail=message,
        )
