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

# Coloured dots that match each severity (medium is amber, not green).
SEVERITY_ICONS = {
    Severity.CRITICAL: "🔴",
    Severity.HIGH: "🟠",
    Severity.MEDIUM: "🟡",
    Severity.LOW: "🔵",
    Severity.INFO: "⚪",
}

SEVERITY_ORDER = [
    Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO,
]


class AuditReportDialog(QDialog):
    def __init__(self, report: AuditReport, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Quick Audit — {report.device_hostname or report.management_ip}")
        self.setMinimumSize(580, 500)
        self._report = report
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)

        host = self._report.device_hostname or self._report.management_ip
        header = QLabel(
            f"<b style='font-size:15px'>{host}</b> &nbsp;|&nbsp; "
            f"{self._report.device_model} &nbsp;|&nbsp; {self._report.management_ip}<br>"
            f"Overall status: <b>{self._report.overall_status.upper()}</b> &nbsp;|&nbsp; "
            f"{len(self._report.findings)} finding(s)"
        )
        header.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(header)

        summary = self._severity_summary()
        if summary:
            summary_label = QLabel(summary)
            summary_label.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(summary_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        findings_layout = QVBoxLayout(container)
        findings_layout.setSpacing(12)

        if not self._report.findings:
            ok = QLabel("✅  No issues detected. Device looks healthy.")
            ok.setStyleSheet("color:#27ae60; font-size:14px; padding:20px;")
            findings_layout.addWidget(ok)
        else:
            ordered = sorted(
                self._report.findings,
                key=lambda f: SEVERITY_ORDER.index(f.severity)
                if f.severity in SEVERITY_ORDER else len(SEVERITY_ORDER),
            )
            for finding in ordered:
                findings_layout.addWidget(self._finding_widget(finding))

        findings_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _severity_summary(self) -> str:
        """A colorized 'N Critical · M High · …' line (non-zero severities only)."""
        counts: dict[Severity, int] = {}
        for f in self._report.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        parts = []
        for sev in SEVERITY_ORDER:
            n = counts.get(sev, 0)
            if n:
                color = SEVERITY_COLORS[sev]
                parts.append(
                    f"{SEVERITY_ICONS[sev]} <b style='color:{color}'>{n}</b> {sev.value.title()}"
                )
        return " &nbsp;·&nbsp; ".join(parts)

    def _finding_widget(self, finding: Finding) -> QWidget:
        box = QWidget()
        box.setStyleSheet(
            f"background: #fafafa; border-left: 4px solid {SEVERITY_COLORS[finding.severity]}; "
            "padding: 8px; border-radius: 4px;"
        )
        v = QVBoxLayout(box)
        icon = SEVERITY_ICONS.get(finding.severity, "")
        badge = finding.severity.value.upper()
        fix = "  🔧 <span style='color:#27ae60'>auto-fixable</span>" if finding.auto_fixable else ""
        title = QLabel(
            f"{icon} <b>{finding.title}</b> "
            f"<span style='color:{SEVERITY_COLORS[finding.severity]}'>[{badge}]</span>{fix}"
        )
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
            src.setWordWrap(True)
            v.addWidget(src)
        return box
