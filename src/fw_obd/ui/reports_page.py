"""Reports page — scan history across all devices, view a report, export to CSV."""

from __future__ import annotations

import csv
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fw_obd.db.database import Database
from fw_obd.models.serialize import audit_report_from_json
from fw_obd.ui.audit_report_dialog import AuditReportDialog
from fw_obd.ui.dashboard import STATUS_COLORS

COLUMNS = ["Scanned At", "Device", "IP", "Region", "Type", "Findings", "Status", ""]


def _report_of(findings_json: str):
    if not findings_json:
        return None
    try:
        return audit_report_from_json(findings_json)
    except Exception:  # noqa: BLE001 — tolerate legacy/partial rows
        return None


class ReportsPageWidget(QWidget):
    """Scan history table with per-row view and CSV export."""

    status_message = pyqtSignal(str)

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._rows: list[dict] = []
        self._build()
        self.reload()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        toolbar = QHBoxLayout()
        title = QLabel("Reports")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        toolbar.addWidget(title)
        toolbar.addStretch()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        export = QPushButton("Export CSV")
        export.clicked.connect(self._export_csv)
        toolbar.addWidget(refresh)
        toolbar.addWidget(export)
        root.addLayout(toolbar)

        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Device
        root.addWidget(self._table, stretch=1)

        self._empty = QLabel("No scans yet. Connect a device from the Devices page to run an audit.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet("color:#7f8c8d; padding:8px;")
        root.addWidget(self._empty)

    def reload(self) -> None:
        self._rows = [dict(r) for r in self._db.list_scans()]
        self._table.setRowCount(0)
        for scan in self._rows:
            self._append_row(scan)
        self._empty.setVisible(not self._rows)

    def _append_row(self, scan: dict) -> None:
        report = _report_of(scan.get("findings_json", ""))
        findings = len(report.findings) if report else 0
        status = report.overall_status if report else "unknown"

        row = self._table.rowCount()
        self._table.insertRow(row)
        cells = [
            (scan.get("scanned_at") or "").replace("T", " ")[:19],
            scan.get("name", ""),
            scan.get("management_ip", ""),
            scan.get("region", "") or "—",
            scan.get("scan_type", ""),
            str(findings),
            status.title(),
        ]
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            if col == 6:
                item.setForeground(QColor(STATUS_COLORS.get(status, STATUS_COLORS["unknown"])))
            self._table.setItem(row, col, item)

        view = QPushButton("View")
        view.setEnabled(report is not None)
        view.clicked.connect(lambda _=False, sid=scan["id"]: self._view(sid))
        self._table.setCellWidget(row, 7, view)

    def _view(self, scan_id: int) -> None:
        scan = self._db.get_scan(scan_id)
        if not scan:
            return
        report = _report_of(scan["findings_json"])
        if report is None:
            QMessageBox.information(self, "No details", "This scan has no stored findings.")
            return
        AuditReportDialog(report, self).exec()

    def _export_csv(self) -> None:
        if not self._rows:
            QMessageBox.information(self, "Nothing to export", "There are no scans to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export scan history", "scan_history.csv", "CSV Files (*.csv)"
        )
        if not path:
            return
        with Path(path).open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Scanned At", "Device", "IP", "Region", "Location", "Type",
                             "Findings", "Status"])
            for scan in self._rows:
                report = _report_of(scan.get("findings_json", ""))
                writer.writerow([
                    scan.get("scanned_at", ""), scan.get("name", ""),
                    scan.get("management_ip", ""), scan.get("region", ""),
                    scan.get("location", ""), scan.get("scan_type", ""),
                    len(report.findings) if report else 0,
                    report.overall_status if report else "unknown",
                ])
        self.status_message.emit(f"Exported {len(self._rows)} scans to {Path(path).name}")
