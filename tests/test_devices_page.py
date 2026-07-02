"""Tests for the Devices page widget and update_device DB method."""

import pytest

from PyQt6.QtCore import Qt

from fw_obd.db.database import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "t.db")


def _leaf_count(item) -> int:
    if item.data(0, Qt.ItemDataRole.UserRole) is not None:
        return 1
    return sum(_leaf_count(item.child(i)) for i in range(item.childCount()))


def _tree_leaves(tree) -> int:
    return sum(_leaf_count(tree.topLevelItem(i)) for i in range(tree.topLevelItemCount()))


def test_update_device_changes_ip(db):
    did = db.upsert_device(name="fw1", management_ip="10.0.0.1", vendor="Fortinet")
    db.update_device(
        device_id=did, name="fw1-renamed", management_ip="10.0.0.99",
        vendor="Palo Alto", model="PA-220", location="HQ", region="US",
    )
    row = db.get_device(did)
    assert row["name"] == "fw1-renamed"
    assert row["management_ip"] == "10.0.0.99"
    assert row["vendor"] == "Palo Alto"


def test_devices_page_builds_tree(db, qtbot):
    from fw_obd.ui.devices_page import DevicesPageWidget

    db.upsert_device(name="RICU - Chennai-1 Main", management_ip="1.1.1.1", region="India", location="Chennai")
    db.upsert_device(name="RICU - Chennai-1 Backup", management_ip="1.1.1.2", region="India", location="Chennai")
    db.upsert_device(name="RICU - Chennai-2 Backup", management_ip="1.1.1.3", region="India", location="Chennai")

    page = DevicesPageWidget(db)
    qtbot.addWidget(page)
    assert _tree_leaves(page._tree) == 3  # all devices present as leaves


def _leaf_items(item) -> list:
    if item.data(0, Qt.ItemDataRole.UserRole) is not None:
        return [item]
    return [leaf for i in range(item.childCount()) for leaf in _leaf_items(item.child(i))]


def _find_row(tree, name: str):
    for i in range(tree.topLevelItemCount()):
        for leaf in _leaf_items(tree.topLevelItem(i)):
            if leaf.text(0) == name:
                return leaf
    raise AssertionError(f"device row {name!r} not found")


def test_vendor_and_model_shown_only_after_successful_contact(db, qtbot):
    from fw_obd.ui.devices_page import DevicesPageWidget

    seen = db.upsert_device(
        name="GS Main", management_ip="10.1.1.1", region="Israel", location="Givat Shmuel",
        vendor="Fortinet", model="FortiGate-60F", software_version="v7.2.8",
    )
    db.update_device_status(seen, "healthy")  # stamps last_seen
    db.upsert_device(
        name="GS Backup", management_ip="10.1.1.2", region="Israel", location="Givat Shmuel",
        vendor="Fortinet", model="FortiGate-40F",
    )  # never contacted

    page = DevicesPageWidget(db)
    qtbot.addWidget(page)

    seen_row = _find_row(page._tree, "GS Main")
    assert seen_row.text(1) == "Main · FortiGate-60F"
    assert "Firmware: v7.2.8" in seen_row.toolTip(0)

    unseen_row = _find_row(page._tree, "GS Backup")
    assert unseen_row.text(1) == "Backup"  # model hidden until confirmed by a connection
    assert unseen_row.toolTip(0) == ""


def test_device_icon_badge_varies_by_vendor(qtbot):
    from fw_obd.ui.devices_page import _device_icon

    plain = _device_icon("healthy").pixmap(56, 22).toImage()
    fortinet = _device_icon("healthy", "Fortinet").pixmap(56, 22).toImage()
    cisco = _device_icon("healthy", "Cisco").pixmap(56, 22).toImage()
    assert plain != fortinet  # badge drawn
    assert fortinet != cisco  # per-vendor colours/text


def test_devices_page_delete(db, qtbot):
    from fw_obd.ui.devices_page import DevicesPageWidget

    did = db.upsert_device(name="Doomed Main", management_ip="10.0.0.5", region="US")
    page = DevicesPageWidget(db)
    qtbot.addWidget(page)
    assert _tree_leaves(page._tree) == 1

    db.delete_device(did)
    page.reload()
    assert _tree_leaves(page._tree) == 0
