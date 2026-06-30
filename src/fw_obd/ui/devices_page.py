"""Devices page — full inventory table with edit / delete / connect row actions."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fw_obd.db.database import Database
from fw_obd.ui.audit_report_dialog import AuditReportDialog
from fw_obd.ui.connect_dialog import ConnectDialog
from fw_obd.ui.dashboard import STATUS_COLORS, STATUS_LABELS
from fw_obd.ui.import_devices_dialog import ImportDevicesDialog
from fw_obd.ui.scan_worker import DeviceScanWorker

VENDORS = ["Fortinet", "Palo Alto", "Cisco", "Check Point"]

COLUMNS = ["Name", "IP", "Vendor", "Model", "Location", "Status", "Last Seen", "Actions"]


class DeviceDialog(QDialog):
    """Add or edit a device. Pre-fills fields when an existing row is passed."""

    def __init__(self, device: dict | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._editing = device is not None
        self.setWindowTitle("Edit Device" if self._editing else "Add Device")
        self.setMinimumWidth(380)
        self._build(device or {})

    def _build(self, device: dict) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._name = QLineEdit(device.get("name", ""))
        self._ip = QLineEdit(device.get("management_ip", ""))
        self._ip.setPlaceholderText("e.g. 192.168.1.1")
        self._vendor = QComboBox()
        self._vendor.addItems(VENDORS)
        current_vendor = device.get("vendor", "Fortinet")
        if current_vendor and current_vendor not in VENDORS:
            self._vendor.addItem(current_vendor)
        self._vendor.setCurrentText(current_vendor or "Fortinet")
        self._model = QLineEdit(device.get("model", ""))
        self._location = QLineEdit(device.get("location", ""))
        self._region = QLineEdit(device.get("region", ""))

        form.addRow("Device Name *", self._name)
        form.addRow("Management IP *", self._ip)
        form.addRow("Vendor", self._vendor)
        form.addRow("Model", self._model)
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
            "vendor": self._vendor.currentText().strip(),
            "model": self._model.text().strip(),
            "location": self._location.text().strip(),
            "region": self._region.text().strip(),
        }

    def is_valid(self) -> bool:
        return bool(self._name.text().strip() and self._ip.text().strip())


class DevicesPageWidget(QWidget):
    """Inventory table of all devices with edit / delete / connect actions."""

    status_message = pyqtSignal(str)

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._scan_worker: DeviceScanWorker | None = None
        self._build()
        self.reload()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        toolbar = QHBoxLayout()
        title = QLabel("Devices")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        toolbar.addWidget(title)
        toolbar.addStretch()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search devices...")
        self._search.setFixedWidth(220)
        self._search.textChanged.connect(self._filter_rows)
        toolbar.addWidget(self._search)

        add_btn = QPushButton("+ Add Device")
        add_btn.clicked.connect(self._add_device)
        toolbar.addWidget(add_btn)

        import_btn = QPushButton("Import CSV/Excel")
        import_btn.clicked.connect(self._import_devices)
        toolbar.addWidget(import_btn)

        root.addLayout(toolbar)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)        # Name
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)        # Location
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)  # Actions
        root.addWidget(self._table, stretch=1)

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def reload(self) -> None:
        devices = [dict(row) for row in self._db.list_devices()]
        self._table.setRowCount(0)
        for device in devices:
            self._append_row(device)
        self._filter_rows(self._search.text())

    def _append_row(self, device: dict) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)

        status = device.get("status", "unknown")
        last_seen = (device.get("last_seen") or "").replace("T", " ")[:19] or "Never"
        cells = [
            device.get("name", ""),
            device.get("management_ip", ""),
            device.get("vendor", ""),
            device.get("model", ""),
            device.get("location", ""),
            STATUS_LABELS.get(status, status.title()),
            last_seen,
        ]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            if col == 5:  # Status column — colorize
                from PyQt6.QtGui import QColor

                item.setForeground(QColor(STATUS_COLORS.get(status, STATUS_COLORS["unknown"])))
            self._table.setItem(row, col, item)

        self._table.setCellWidget(row, 7, self._build_actions(device))

    def _build_actions(self, device: dict) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        for label, slot in (
            ("Connect", lambda: self._connect_device(device)),
            ("Edit", lambda: self._edit_device(device)),
            ("Delete", lambda: self._delete_device(device)),
        ):
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.clicked.connect(slot)
            layout.addWidget(btn)
        return wrapper

    def _filter_rows(self, text: str) -> None:
        query = text.lower()
        for row in range(self._table.rowCount()):
            name = (self._table.item(row, 0).text() if self._table.item(row, 0) else "").lower()
            ip = (self._table.item(row, 1).text() if self._table.item(row, 1) else "").lower()
            self._table.setRowHidden(row, bool(query) and query not in name and query not in ip)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _add_device(self) -> None:
        dialog = DeviceDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.is_valid():
            v = dialog.values()
            self._db.upsert_device(
                name=v["name"],
                management_ip=v["management_ip"],
                vendor=v["vendor"],
                model=v["model"],
                location=v["location"],
                region=v["region"],
            )
            self.reload()
            self.status_message.emit(f"Added device {v['name']}")

    def _import_devices(self) -> None:
        dialog = ImportDevicesDialog(self._db, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()
            self.status_message.emit("Devices imported")

    def _edit_device(self, device: dict) -> None:
        dialog = DeviceDialog(device=device, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.is_valid():
            v = dialog.values()
            self._db.update_device(
                device_id=device["id"],
                name=v["name"],
                management_ip=v["management_ip"],
                vendor=v["vendor"],
                model=v["model"],
                location=v["location"],
                region=v["region"],
            )
            self.reload()
            self.status_message.emit(f"Updated device {v['name']}")

    def _delete_device(self, device: dict) -> None:
        confirm = QMessageBox.question(
            self,
            "Delete device",
            f"Delete '{device.get('name', '')}' ({device.get('management_ip', '')})?\n"
            "This removes it from the inventory.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._db.delete_device(device["id"])
            self.reload()
            self.status_message.emit(f"Deleted device {device.get('name', '')}")

    def _connect_device(self, device: dict) -> None:
        device_id = device["id"]
        management_ip = device.get("management_ip", "")
        cred_dialog = ConnectDialog(management_ip, device.get("name", management_ip), self)
        if cred_dialog.exec() != QDialog.DialogCode.Accepted or not cred_dialog.is_valid():
            return

        if self._scan_worker and self._scan_worker.isRunning():
            QMessageBox.warning(self, "Scan in progress", "Wait for the current scan to finish.")
            return

        self.status_message.emit(f"Connecting to {management_ip}…")
        self._scan_worker = DeviceScanWorker(cred_dialog.credentials(), self._db, device_id, self)
        self._scan_worker.progress.connect(self.status_message.emit)
        self._scan_worker.finished_ok.connect(self._on_scan_finished)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.start()

    def _on_scan_finished(self, result: object) -> None:
        from fw_obd.services.device_scan import ScanResult

        assert isinstance(result, ScanResult)
        self.reload()
        self.status_message.emit(
            f"Audit complete — {len(result.report.findings)} finding(s), "
            f"status: {result.report.overall_status}"
        )
        AuditReportDialog(result.report, self).exec()

    def _on_scan_failed(self, message: str) -> None:
        self.status_message.emit("Connection failed")
        QMessageBox.critical(self, "Connection failed", message)
        self._db.log_action(
            action="connect",
            description=message,
            success=False,
            error_detail=message,
        )
