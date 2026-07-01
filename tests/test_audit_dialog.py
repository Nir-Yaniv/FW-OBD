"""Tests for the AuditReportDialog severity summary and rendering."""

from fw_obd.audit.quick_audit import AuditReport, Finding, Severity
from fw_obd.ui.audit_report_dialog import AuditReportDialog


def test_severity_summary_counts(qtbot):
    report = AuditReport(
        device_hostname="FW-1", device_model="FG-60F", management_ip="10.0.0.1",
        findings=[
            Finding(Severity.LOW, "l", "d", "r"),
            Finding(Severity.CRITICAL, "c", "d", "r", auto_fixable=True),
            Finding(Severity.MEDIUM, "m", "d", "r"),
            Finding(Severity.CRITICAL, "c2", "d", "r"),
        ],
    )
    dialog = AuditReportDialog(report)
    qtbot.addWidget(dialog)
    summary = dialog._severity_summary()
    assert "Critical" in summary and "Medium" in summary and "Low" in summary
    assert ">2<" in summary  # two criticals counted


def test_empty_report_has_no_summary(qtbot):
    dialog = AuditReportDialog(
        AuditReport(device_hostname="X", device_model="Y", management_ip="1.1.1.1")
    )
    qtbot.addWidget(dialog)
    assert dialog._severity_summary() == ""
