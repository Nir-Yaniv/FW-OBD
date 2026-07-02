"""Devices page — Region -> City -> Site tree with flags and connectivity status.

Layout:
  * Region rows show a bundled national flag (uniform size, faded, bordered).
  * City and site rows show just their name and a count.
  * Device (leaf) rows show a connectivity dot: green = reachable, red = down /
    SSH failed, grey = not tested yet — plus an On-site Contact column.
  * Once a device has been successfully contacted (last_seen set), a small
    vendor badge (FGT / PAN / CSCO / CHKP) appears between the dot and the
    name, and the Type column gains the detected model (e.g. FortiGate-60F).
Double-click a device to connect; right-click for Edit / Delete.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QRect, Qt, QSize, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fw_obd.db.database import Database
from fw_obd.services.device_grouping import build_device_tree, classify, region_iso
from fw_obd.ui.audit_report_dialog import AuditReportDialog
from fw_obd.ui.connect_dialog import ConnectDialog
from fw_obd.ui.import_devices_dialog import ImportDevicesDialog
from fw_obd.ui.scan_worker import DeviceScanWorker

VENDORS = ["Fortinet", "Palo Alto", "Cisco", "Check Point"]
COLUMNS = ["Site / Device", "Type", "IP Address", "Status", "On-site Contact", "Last Seen"]

_DEVICE_ROLE = Qt.ItemDataRole.UserRole
_FLAG_DIR = Path(__file__).resolve().parent / "assets" / "flags"

ICON_BOX = QSize(56, 22)  # wide enough for connectivity dot + vendor badge
FLAG_CELL = QSize(26, 17)     # every flag is scaled to fit this same cell
FLAG_OPACITY = 0.55

# Connectivity dot colours (fill, edge).
_DOT_COLORS = {
    "offline": ("#e74c3c", "#b23127"),   # red — down / SSH unreachable
    "unknown": ("#c2c8d0", "#a2a9b3"),    # grey — not tested yet
}
_DOT_UP = ("#2ecc71", "#22a35c")           # green — reachable / online

# Vendor badge (abbreviation, fill, edge) in brand colours. Shown only after a
# successful connection, so the badge reflects what was actually detected.
_VENDOR_BADGES = {
    "Fortinet": ("FGT", "#da291c", "#a51f15"),
    "Palo Alto": ("PAN", "#fa582d", "#c74522"),
    "Cisco": ("CSCO", "#049fd9", "#0380ae"),
    "Check Point": ("CHKP", "#e6007e", "#b30063"),
}

_TREE_STYLESHEET = """
QTreeWidget { background: #ffffff; border: 1px solid #dde3e9; border-radius: 6px; outline: 0; }
QTreeWidget::item { height: 28px; }
QTreeWidget::item:selected { background: #e8f2fb; color: #111; }
QHeaderView::section {
    background: #eef2f6; padding: 6px 8px; border: none;
    border-bottom: 1px solid #dde3e9; font-weight: bold; color: #33475b;
}
"""

# Simple icon caches so we render each flag / dot once.
_flag_cache: dict[str, QIcon] = {}
_dot_cache: dict[str, QIcon] = {}


def _flag_icon(region: str) -> QIcon:
    """Uniform, faded, bordered flag for a region (cached)."""
    iso = region_iso(region)
    if not iso:
        return QIcon()
    if iso in _flag_cache:
        return _flag_cache[iso]
    src = QPixmap(str(_FLAG_DIR / f"{iso}.png"))
    if src.isNull():
        _flag_cache[iso] = QIcon()
        return _flag_cache[iso]
    fitted = src.scaled(
        FLAG_CELL, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    canvas = QPixmap(ICON_BOX)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.setOpacity(FLAG_OPACITY)
    x = 3  # left-anchored: the box is wider than a flag to make room for badges
    y = (ICON_BOX.height() - fitted.height()) // 2
    p.drawPixmap(x, y, fitted)
    p.setOpacity(1.0)
    p.setPen(QPen(QColor("#8a929c"), 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(x, y, fitted.width() - 1, fitted.height() - 1)
    p.end()
    icon = QIcon(canvas)
    _flag_cache[iso] = icon
    return icon


def _device_icon(status: str, vendor: str = "") -> QIcon:
    """Connectivity dot (green up / red down / grey untested), plus a small
    vendor badge between the dot and the device name once the vendor is
    confirmed by a successful connection (cached)."""
    key = f"{status}|{vendor}"
    if key in _dot_cache:
        return _dot_cache[key]
    fill, edge = _DOT_COLORS.get(status, _DOT_UP)
    pm = QPixmap(ICON_BOX)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor(edge), 1))
    p.setBrush(QColor(fill))
    d = 12
    p.drawEllipse(6, (ICON_BOX.height() - d) // 2, d, d)
    badge = _VENDOR_BADGES.get(vendor)
    if badge:
        text, b_fill, b_edge = badge
        w, h = 32, 16
        x, y = 22, (ICON_BOX.height() - h) // 2
        p.setPen(QPen(QColor(b_edge), 1))
        p.setBrush(QColor(b_fill))
        p.drawRoundedRect(x, y, w, h, 4, 4)
        f = QFont()
        f.setBold(True)
        f.setPixelSize(9)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(QRect(x, y, w, h), Qt.AlignmentFlag.AlignCenter, text)
    p.end()
    icon = QIcon(pm)
    _dot_cache[key] = icon
    return icon


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
        self._contact = QLineEdit(device.get("onsite_contact", "") or "")
        self._contact.setPlaceholderText("Main on-site contact name")

        form.addRow("Device Name *", self._name)
        form.addRow("Management IP *", self._ip)
        form.addRow("Vendor", self._vendor)
        form.addRow("Model", self._model)
        form.addRow("Location (City)", self._location)
        form.addRow("Region", self._region)
        form.addRow("On-site Contact", self._contact)
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
            "onsite_contact": self._contact.text().strip(),
        }

    def is_valid(self) -> bool:
        return bool(self._name.text().strip() and self._ip.text().strip())


class DevicesPageWidget(QWidget):
    """Region -> City -> Site device tree with flags and connectivity status."""

    status_message = pyqtSignal(str)
    monitor_requested = pyqtSignal(object, object, object)  # device, credentials, udm

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._scan_worker: DeviceScanWorker | None = None
        self._pending_device: dict | None = None
        self._pending_creds = None
        self._build()
        self.reload()

    # ------------------------------------------------------------------ build
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
        self._search.setPlaceholderText("Search name or IP…")
        self._search.setFixedWidth(220)
        self._search.textChanged.connect(self._filter)
        toolbar.addWidget(self._search)

        expand_btn = QPushButton("⊞ Expand all")
        expand_btn.clicked.connect(lambda: self._tree.expandAll())
        collapse_btn = QPushButton("⊟ Collapse all")
        collapse_btn.clicked.connect(lambda: self._tree.collapseAll())
        toolbar.addWidget(expand_btn)
        toolbar.addWidget(collapse_btn)

        add_btn = QPushButton("+ Add Device")
        add_btn.clicked.connect(self._add_device)
        toolbar.addWidget(add_btn)
        import_btn = QPushButton("Import CSV/Excel")
        import_btn.clicked.connect(self._import_devices)
        toolbar.addWidget(import_btn)
        root.addLayout(toolbar)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(COLUMNS))
        self._tree.setHeaderLabels(COLUMNS)
        for i, w in enumerate([430, 150, 140, 90, 160]):
            self._tree.setColumnWidth(i, w)
        self._tree.setIconSize(ICON_BOX)
        self._tree.setIndentation(22)
        self._tree.setAnimated(True)
        self._tree.setStyleSheet(_TREE_STYLESHEET)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._show_context_menu)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        root.addWidget(self._tree, stretch=1)

        hint = QLabel("Double-click a device to connect · right-click for Edit / Delete")
        hint.setStyleSheet("color: #7f8c8d;")
        root.addWidget(hint)

    # ------------------------------------------------------------------- data
    def reload(self) -> None:
        expanded = self._expanded_labels()
        self._tree.clear()
        devices = [dict(row) for row in self._db.list_devices()]

        region_font = QFont(); region_font.setBold(True); region_font.setPointSize(13)
        city_font = QFont(); city_font.setBold(True); city_font.setPointSize(11)
        site_font = QFont(); site_font.setBold(True)

        for region in build_device_tree(devices):
            r_item = QTreeWidgetItem(
                [f"{region.name}    ({region.count} devices · {len(region.cities)} sites)"]
            )
            r_item.setIcon(0, _flag_icon(region.name))
            r_item.setFont(0, region_font)
            r_item.setForeground(0, QColor("#16324f"))
            for col in range(len(COLUMNS)):
                r_item.setBackground(col, QColor("#eef4fa"))
            self._tree.addTopLevelItem(r_item)

            for city in region.cities:
                c_item = QTreeWidgetItem([f"{city.name}    ({city.count})"])
                c_item.setFont(0, city_font)
                c_item.setForeground(0, QColor("#2c3e50"))
                r_item.addChild(c_item)
                for site in city.sites:
                    parent = c_item
                    if site.name is not None:
                        s_item = QTreeWidgetItem([f"{site.name}    ({len(site.devices)})"])
                        s_item.setFont(0, site_font)
                        s_item.setForeground(0, QColor("#5d6d7e"))
                        c_item.addChild(s_item)
                        parent = s_item
                    for device in site.devices:
                        self._add_device_row(parent, device)

        self._restore_expanded(expanded)
        if not devices:
            self._tree.addTopLevelItem(
                QTreeWidgetItem(["No devices yet. Use '+ Add Device' or Import."])
            )

    def _add_device_row(self, parent: QTreeWidgetItem, device: dict) -> None:
        status = device.get("status", "unknown") or "unknown"
        seen = bool(device.get("last_seen"))  # last_seen = last successful contact
        last_seen = (device.get("last_seen") or "").replace("T", " ")[:19] or "Never"
        label = classify(device.get("name", ""))
        # Vendor/model are only trusted once confirmed by a real connection.
        vendor = (device.get("vendor") or "") if seen else ""
        model = (device.get("model") or "") if seen else ""
        type_text = model if label == "Other" and model else (f"{label} · {model}" if model else label)
        from fw_obd.ui.dashboard import STATUS_LABELS

        item = QTreeWidgetItem(
            [
                device.get("name", ""),
                type_text,
                device.get("management_ip", ""),
                STATUS_LABELS.get(status, status.title()),
                device.get("onsite_contact", "") or "—",
                last_seen,
            ]
        )
        item.setIcon(0, _device_icon(status, vendor))  # dot + vendor badge on the equipment only
        if seen:
            tip_lines = [device.get("name", "")]
            if vendor or model:
                tip_lines.append(f"{vendor} {model}".strip())
            if device.get("hostname"):
                tip_lines.append(f"Hostname: {device['hostname']}")
            if device.get("serial_number"):
                tip_lines.append(f"Serial: {device['serial_number']}")
            if device.get("software_version"):
                tip_lines.append(f"Firmware: {device['software_version']}")
            tip_lines.append(f"Last seen: {last_seen}")
            tip = "\n".join(tip_lines)
            for col in range(len(COLUMNS)):
                item.setToolTip(col, tip)
        if label == "Main":  # bold the Main device so it stands out from its backups
            f = QFont(); f.setBold(True)
            item.setFont(0, f); item.setFont(1, f)
        item.setData(0, _DEVICE_ROLE, device)
        parent.addChild(item)

    # --------------------------------------------------------- expand helpers
    def _expanded_labels(self) -> set[str]:
        labels: set[str] = set()

        def walk(item: QTreeWidgetItem) -> None:
            if item.isExpanded():
                labels.add(item.text(0))
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))
        return labels

    def _restore_expanded(self, labels: set[str]) -> None:
        if not labels:
            self._tree.expandToDepth(1)  # first load: regions + cities open
            return

        def walk(item: QTreeWidgetItem) -> None:
            if item.data(0, _DEVICE_ROLE) is None and item.text(0) in labels:
                item.setExpanded(True)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self._tree.topLevelItemCount()):
            walk(self._tree.topLevelItem(i))

    # ------------------------------------------------------------- selection
    def _on_double_click(self, item: QTreeWidgetItem, _col: int) -> None:
        device = item.data(0, _DEVICE_ROLE)
        if device:
            self._connect_device(device)
        else:
            item.setExpanded(not item.isExpanded())

    def _show_context_menu(self, pos) -> None:
        item = self._tree.itemAt(pos)
        if item is None:
            return
        device = item.data(0, _DEVICE_ROLE)
        if not device:
            return
        menu = QMenu(self)
        act_connect = QAction("Connect", self)
        act_connect.triggered.connect(lambda: self._connect_device(device))
        act_edit = QAction("Edit…", self)
        act_edit.triggered.connect(lambda: self._edit_device(device))
        act_delete = QAction("Delete…", self)
        act_delete.triggered.connect(lambda: self._delete_device(device))
        menu.addAction(act_connect)
        menu.addSeparator()
        menu.addAction(act_edit)
        menu.addAction(act_delete)
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    # --------------------------------------------------------------- actions
    def _add_device(self) -> None:
        dialog = DeviceDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.is_valid():
            v = dialog.values()
            self._db.upsert_device(
                name=v["name"], management_ip=v["management_ip"], vendor=v["vendor"],
                model=v["model"], location=v["location"], region=v["region"],
                onsite_contact=v["onsite_contact"],
            )
            self.reload()
            self.status_message.emit(f"Added device {v['name']}")

    def _edit_device(self, device: dict) -> None:
        dialog = DeviceDialog(device=device, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.is_valid():
            v = dialog.values()
            self._db.update_device(
                device_id=device["id"], name=v["name"], management_ip=v["management_ip"],
                vendor=v["vendor"], model=v["model"], location=v["location"], region=v["region"],
                onsite_contact=v["onsite_contact"],
            )
            self.reload()
            self.status_message.emit(f"Updated device {v['name']}")

    def _delete_device(self, device: dict) -> None:
        confirm = QMessageBox.question(
            self, "Delete device",
            f"Delete '{device.get('name', '')}' ({device.get('management_ip', '')})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self._db.delete_device(device["id"])
            self.reload()
            self.status_message.emit(f"Deleted device {device.get('name', '')}")

    def _import_devices(self) -> None:
        dialog = ImportDevicesDialog(self._db, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reload()
            self.status_message.emit("Devices imported")

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
        self._pending_device_id = device_id
        self._pending_device = device
        self._pending_creds = cred_dialog.credentials()
        self._scan_worker = DeviceScanWorker(self._pending_creds, self._db, device_id, self)
        self._scan_worker.progress.connect(self.status_message.emit)
        self._scan_worker.finished_ok.connect(self._on_scan_finished)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.scan_error.connect(self._on_scan_error)
        self._scan_worker.start()

    def _on_scan_finished(self, result: object) -> None:
        from fw_obd.services.device_scan import ScanResult

        assert isinstance(result, ScanResult)
        self.reload()  # device status is now reachable -> dot goes green
        self.status_message.emit(
            f"Audit complete — {len(result.report.findings)} finding(s), "
            f"status: {result.report.overall_status}"
        )
        # Hand off to the live Dashboard: start monitoring this device.
        # The metrics poller is SSH-only — REST connections skip the handoff.
        from fw_obd.connection.ssh_handler import SSHCredentials

        if (
            self._pending_device is not None
            and isinstance(self._pending_creds, SSHCredentials)
        ):
            self.monitor_requested.emit(self._pending_device, self._pending_creds, result.device)
        elif self._pending_creds is not None:
            self.status_message.emit(
                "Connected via HTTPS — live dashboard monitoring is not yet available for REST connections"
            )
        AuditReportDialog(result.report, self).exec()

    def _on_scan_failed(self, message: str) -> None:
        # SSH could not connect -> mark the device offline so its dot goes red.
        device_id = getattr(self, "_pending_device_id", None)
        if device_id is not None:
            self._db.update_device_status(device_id, "offline", touch_last_seen=False)
            self.reload()
        self.status_message.emit("Connection failed")
        QMessageBox.critical(self, "Connection failed", message)
        self._db.log_action(
            action="connect", description=message, device_id=device_id,
            success=False, error_detail=message,
        )

    def _on_scan_error(self, message: str) -> None:
        # The device WAS reachable — record the successful contact (dot goes
        # green, last_seen stamped) even though the scan itself broke.
        device_id = getattr(self, "_pending_device_id", None)
        if device_id is not None:
            self._db.update_device_status(device_id, "online")
            self.reload()
        self.status_message.emit("Scan failed (device was reachable)")
        QMessageBox.warning(self, "Scan failed", message)
        self._db.log_action(
            action="scan", description=message, device_id=device_id,
            success=False, error_detail=message,
        )

    # ------------------------------------------------------------- filtering
    def _filter(self, text: str) -> None:
        q = text.lower().strip()

        def visit(item: QTreeWidgetItem) -> bool:
            device = item.data(0, _DEVICE_ROLE)
            if device is not None:
                match = (
                    not q
                    or q in device.get("name", "").lower()
                    or q in device.get("management_ip", "").lower()
                )
                item.setHidden(not match)
                return match
            any_visible = False
            for i in range(item.childCount()):
                any_visible = visit(item.child(i)) or any_visible
            item.setHidden(not any_visible)
            if q and any_visible:
                item.setExpanded(True)
            return any_visible

        for i in range(self._tree.topLevelItemCount()):
            visit(self._tree.topLevelItem(i))
