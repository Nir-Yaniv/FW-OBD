"""Dialog showing Quick Audit findings after a device scan."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from fw_obd.audit.quick_audit import AuditReport, Finding, Severity

SEVERITY_COLORS = {
    Severity.CRITICAL: "#c0392b",
    Severity.HIGH: "#e67e22",
    Severity.MEDIUM: "#f39c12",
    Severity.LOW: "#2980b9",
    Severity.INFO: "#7f8c8d",
}

SEVERITY_ICONS = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🟡",
    Severity.MEDIUM: "🟢",
    Severity.LOW: "🔵",
    Severity.INFO: "ℹ️",
}


class AuditReportDialog(QDialog):
    def __init__(self, report: AuditReport, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Quick Audit — {report.device_hostname or report.management_ip}")
        self.setMinimumSize(560, 480)
        self._report = report
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        header = QLabel(
            f"<b>{self._report.device_model}</b> &nbsp;|&nbsp; {self._report.management_ip}<br>"
            f"Status: <b>{self._report.overall_status.upper()}</b> &nbsp;|&nbsp; "
            f"{len(self._report.findings)} finding(s)"
        )
        header.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        findings_layout = QVBoxLayout(container)
        findings_layout.setSpacing(12)

        if not self._report.findings:
            findings_layout.addWidget(QLabel("No issues detected. Device looks healthy."))
        else:
            for finding in self._report.findings:
                findings_layout.addWidget(self._finding_widget(finding))

        findings_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _finding_widget(self, finding: Finding) -> QWidget:
        box = QWidget()
        box.setStyleSheet(
            f"background: #fafafa; border-left: 4px solid {SEVERITY_COLORS[finding.severity]}; "
            "padding: 8px; border-radius: 4px;"
        )
        v = QVBoxLayout(box)
        icon = SEVERITY_ICONS.get(finding.severity, "")
        title = QLabel(f"{icon} <b>{finding.title}</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setWordWrap(True)
        detail = QLabel(finding.detail)
        detail.setWordWrap(True)
        detail.setStyleSheet("color: #555;")
        rec = QLabel(f"<i>Recommendation:</i> {finding.recommendation}")
        rec.setTextFormat(Qt.TextFormat.RichText)
        rec.setWordWrap(True)
        v.addWidget(title)
        v.addWidget(detail)
        v.addWidget(rec)
        if finding.source:
            src = QLabel(f"<small>Source: {finding.source}</small>")
            src.setTextFormat(Qt.TextFormat.RichText)
            v.addWidget(src)
        return box
