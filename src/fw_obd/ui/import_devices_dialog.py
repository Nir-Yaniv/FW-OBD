"""Import devices from CSV file."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from fw_obd.db.database import Database
from fw_obd.import_.csv_importer import parse_import_file


class ImportDevicesDialog(QDialog):
    def __init__(self, db: Database, parent=None) -> None:
        super().__init__(parent)
        self._db = db
        self._path: Path | None = None
        self.setWindowTitle("Import Devices")
        self.setMinimumWidth(480)
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Import from SolarWinds, PRTG, or any CSV/Excel file with columns "
                "for device name and management IP."
            )
        )

        row = QHBoxLayout()
        self._path_label = QLabel("No file selected")
        self._path_label.setStyleSheet("color: #666;")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self._path_label, stretch=1)
        row.addWidget(browse)
        layout.addLayout(row)

        self._preview_label = QLabel("")
        self._preview_label.setTextFormat(Qt.TextFormat.RichText)
        self._preview_label.setWordWrap(True)
        layout.addWidget(self._preview_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._import)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select CSV or Excel file",
            "",
            "Device lists (*.csv *.xlsx *.xlsm);;CSV Files (*.csv);;"
            "Excel Files (*.xlsx *.xlsm);;All Files (*)",
        )
        if not path:
            return
        self._path = Path(path)
        self._path_label.setText(self._path.name)
        try:
            preview = parse_import_file(self._path)
            sample = preview.rows[:3]
            lines = [f"{r.name} — {r.management_ip}" for r in sample]
            extra = f" (+{len(preview.rows) - 3} more)" if len(preview.rows) > 3 else ""
            self._preview_label.setText(
                f"Found <b>{len(preview.rows)}</b> devices"
                f"{f', skipped {preview.skipped} empty rows' if preview.skipped else ''}."
                f"<br>{'<br>'.join(lines)}{extra}"
            )
        except ValueError as exc:
            self._preview_label.setText(f"<span style='color:red'>{exc}</span>")

    def _import(self) -> None:
        if not self._path:
            self._preview_label.setText(
                "<span style='color:red'>Select a CSV or Excel file first.</span>"
            )
            return
        try:
            preview = parse_import_file(self._path)
        except ValueError as exc:
            self._preview_label.setText(f"<span style='color:red'>{exc}</span>")
            return
        for row in preview.rows:
            self._db.upsert_device(
                name=row.name,
                management_ip=row.management_ip,
                vendor=row.vendor,
                location=row.location,
                region=row.region,
            )
        self.accept()
