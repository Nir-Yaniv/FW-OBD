"""Tests for Database device-status semantics."""

import pytest

from fw_obd.db.database import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "t.db")


@pytest.fixture
def device_id(db):
    return db.upsert_device(name="fw-test", management_ip="10.0.0.1")


def test_status_update_stamps_last_seen_on_success(db, device_id):
    db.update_device_status(device_id, "healthy")
    row = db.get_device(device_id)
    assert row["status"] == "healthy"
    assert row["last_seen"]


def test_failed_connect_does_not_stamp_last_seen(db, device_id):
    db.update_device_status(device_id, "offline", touch_last_seen=False)
    row = db.get_device(device_id)
    assert row["status"] == "offline"
    assert row["last_seen"] is None  # never reached -> never "seen"


def test_failed_connect_preserves_previous_last_seen(db, device_id):
    db.update_device_status(device_id, "healthy")
    seen_at = db.get_device(device_id)["last_seen"]

    db.update_device_status(device_id, "offline", touch_last_seen=False)
    row = db.get_device(device_id)
    assert row["status"] == "offline"
    assert row["last_seen"] == seen_at  # timestamp of last real contact kept
