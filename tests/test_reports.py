"""Tests for scan-history listing and the Reports page."""

import pytest

from fw_obd.audit.quick_audit import AuditReport, Finding, Severity
from fw_obd.db.database import Database
from fw_obd.models.serialize import audit_report_to_json


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "t.db")


def _seed_scan(db, name="FW-1", ip="10.0.0.1", severities=(Severity.HIGH,)):
    did = db.upsert_device(name=name, management_ip=ip, region="US")
    report = AuditReport(
        device_hostname=name, device_model="FG-60F", management_ip=ip,
        findings=[Finding(severity=s, title="t", detail="d", recommendation="r") for s in severities],
    )
    db.save_scan(did, "audit", findings_json=audit_report_to_json(report))


def test_list_scans_joins_device(db):
    _seed_scan(db)
    scans = db.list_scans()
    assert len(scans) == 1
    assert scans[0]["name"] == "FW-1"
    assert scans[0]["management_ip"] == "10.0.0.1"


def test_reports_page_shows_findings_and_status(db, qtbot):
    from fw_obd.ui.reports_page import ReportsPageWidget

    _seed_scan(db, severities=(Severity.HIGH, Severity.MEDIUM))
    page = ReportsPageWidget(db)
    qtbot.addWidget(page)
    assert page._table.rowCount() == 1
    assert page._table.item(0, 5).text() == "2"          # findings count
    assert page._table.item(0, 1).text() == "FW-1"        # device name
    assert not page._empty.isVisible()


def test_reports_page_empty_state(db, qtbot):
    from fw_obd.ui.reports_page import ReportsPageWidget

    page = ReportsPageWidget(db)
    qtbot.addWidget(page)
    assert page._table.rowCount() == 0
    assert page._empty.isVisibleTo(page)
