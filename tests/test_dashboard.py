"""Tests for the live-monitoring Dashboard widgets."""

import pytest

from fw_obd.db.database import Database
from fw_obd.services.metrics import DeviceMetrics
from fw_obd.ui.dashboard import DashboardWidget, DevicePanel


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "t.db")


def test_dashboard_starts_empty(db, qtbot):
    dash = DashboardWidget(db)
    qtbot.addWidget(dash)
    assert dash._empty.isVisibleTo(dash)
    assert not dash._panels


def test_device_panel_updates_metrics(qtbot):
    panel = DevicePanel({"id": 1, "name": "FW-1", "management_ip": "10.0.0.1"})
    qtbot.addWidget(panel)
    panel.update_metrics(
        DeviceMetrics(cpu_pct=42, mem_pct=61, sessions=12345,
                      bw_in_kbps=145000, bw_out_kbps=38000, vdoms=3, uptime="3 days")
    )
    assert panel._cpu._value == 42
    assert panel._mem._value == 61
    assert panel._vdom.text() == "3"
    assert panel._sessions.text() == "12,345"
    assert "145.0" in panel._bw_in.text()


def test_relayout_shows_and_hides_empty_state(db, qtbot):
    dash = DashboardWidget(db)
    qtbot.addWidget(dash)
    # inject two panels directly (avoid starting real SSH pollers)
    for did in (1, 2):
        dash._panels[did] = DevicePanel({"id": did, "name": f"FW-{did}", "management_ip": "1.1.1.1"})
    dash._relayout()
    assert not dash._empty.isVisibleTo(dash)
    assert dash._grid.count() == 2

    dash._panels.clear()
    dash._relayout()
    assert dash._empty.isVisibleTo(dash)
