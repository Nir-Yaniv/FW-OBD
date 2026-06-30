"""Tests for the Devices page widget and update_device DB method."""

import pytest

from fw_obd.db.database import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "t.db")


def test_update_device_changes_ip(db):
    did = db.upsert_device(name="fw1", management_ip="10.0.0.1", vendor="Fortinet")
    db.update_device(
        device_id=did,
        name="fw1-renamed",
        management_ip="10.0.0.99",
        vendor="Palo Alto",
        model="PA-220",
        location="HQ",
        region="US",
    )
    row = db.get_device(did)
    assert row["name"] == "fw1-renamed"
    assert row["management_ip"] == "10.0.0.99"  # IP edit works (upsert could not do this)
    assert row["vendor"] == "Palo Alto"
    assert row["model"] == "PA-220"


def test_devices_page_lists_and_filters(db, qtbot):
    from fw_obd.ui.devices_page import DevicesPageWidget

    db.upsert_device(name="FG-NJ", management_ip="10.0.1.1")
    db.upsert_device(name="FG-TLV", management_ip="203.0.113.50")

    page = DevicesPageWidget(db)
    qtbot.addWidget(page)
    assert page._table.rowCount() == 2

    page._search.setText("NJ")
    visible = [r for r in range(page._table.rowCount()) if not page._table.isRowHidden(r)]
    assert len(visible) == 1
    assert page._table.item(visible[0], 0).text() == "FG-NJ"


def test_devices_page_delete(db, qtbot):
    from fw_obd.ui.devices_page import DevicesPageWidget

    did = db.upsert_device(name="Doomed", management_ip="10.0.0.5")
    page = DevicesPageWidget(db)
    qtbot.addWidget(page)
    assert page._table.rowCount() == 1

    # Bypass the confirm dialog: delete via DB + reload (what the slot does on "Yes")
    db.delete_device(did)
    page.reload()
    assert page._table.rowCount() == 0
