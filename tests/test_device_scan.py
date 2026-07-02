"""Tests for the quick-audit scan service and SSHHandler command options."""

import pytest

from fw_obd.connection.ssh_handler import SSHConnectionError, SSHCredentials, SSHHandler
from fw_obd.db.database import Database
from fw_obd.models.udm import Device, Vendor
from fw_obd.parsers.fortigate.reader import FortiGateReader
from fw_obd.services import device_scan


# ---------------------------------------------------------------- SSHHandler

class _FakeNetmiko:
    def __init__(self):
        self.calls: list[dict] = []

    def is_alive(self) -> bool:
        return True

    def send_command(self, **kwargs):
        self.calls.append(kwargs)
        return "output"


def test_send_command_uses_netmiko4_read_timeout():
    handler = SSHHandler(SSHCredentials(host="10.0.0.1", username="u", password="p"))
    handler._connection = _FakeNetmiko()
    handler.send_command("get system status", read_timeout=99.0)
    call = handler._connection.calls[0]
    assert call["read_timeout"] == 99.0
    # delay_factor is silently ignored by Netmiko 4.x — must not be relied on
    assert "delay_factor" not in call


# ------------------------------------------------------- run_quick_audit_scan

class _FakeSSH:
    connect_error: Exception | None = None

    def __init__(self, credentials, timeout: int = 30) -> None:
        pass

    def connect(self) -> None:
        if _FakeSSH.connect_error:
            raise _FakeSSH.connect_error

    def disconnect(self) -> None:
        pass


class _FakeReader:
    backup_error: Exception | None = None
    audit_error: Exception | None = None

    def __init__(self, ssh) -> None:
        pass

    def read_audit_config(self, progress_cb=None) -> Device:
        if _FakeReader.audit_error:
            raise _FakeReader.audit_error
        return Device(vendor=Vendor.FORTINET, model="FortiGate-60F", hostname="fw1", management_ip="10.0.0.1")

    def read_raw_backup(self) -> str:
        if _FakeReader.backup_error:
            raise _FakeReader.backup_error
        return "config ..."


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    _FakeSSH.connect_error = None
    _FakeReader.backup_error = None
    _FakeReader.audit_error = None
    monkeypatch.setattr(device_scan, "SSHHandler", _FakeSSH)
    monkeypatch.setattr(device_scan, "FortiGateReader", _FakeReader)
    db = Database(tmp_path / "t.db")
    device_id = db.upsert_device(name="fw1", management_ip="10.0.0.1")
    creds = SSHCredentials(host="10.0.0.1", username="u", password="p")
    return db, device_id, creds


def test_backup_failure_keeps_audit_results(scan_env):
    db, device_id, creds = scan_env
    _FakeReader.backup_error = SSHConnectionError("Command failed 'show full-configuration': read timeout")

    result = device_scan.run_quick_audit_scan(creds, db, device_id)

    assert result.raw_config == ""  # backup lost, audit kept
    assert len(db.list_scans()) == 1  # scan persisted anyway
    assert db.get_device(device_id)["last_seen"]  # contact still counts


def test_connect_failure_propagates_and_persists_nothing(scan_env):
    db, device_id, creds = scan_env
    _FakeSSH.connect_error = SSHConnectionError("timed out")

    with pytest.raises(SSHConnectionError):
        device_scan.run_quick_audit_scan(creds, db, device_id)

    assert db.list_scans() == []
    assert db.get_device(device_id)["last_seen"] is None


def test_midscan_ssh_failure_is_a_scan_error_not_a_connect_failure(scan_env):
    db, device_id, creds = scan_env
    _FakeReader.audit_error = SSHConnectionError("SSH session lost while running 'get system status'")

    with pytest.raises(device_scan.ScanError):
        device_scan.run_quick_audit_scan(creds, db, device_id)

    # the worker dispatches on type: ScanError must never look like a connect failure
    assert not issubclass(device_scan.ScanError, SSHConnectionError)
    assert db.list_scans() == []


# ------------------------------------------------------------ FortiGateReader

class _FlakySSH:
    """Every command fails; whether the session survives is configurable."""

    def __init__(self, alive: bool) -> None:
        self._creds = SSHCredentials(host="10.0.0.1", username="u", password="p")
        self._alive = alive

    @property
    def is_connected(self) -> bool:
        return self._alive

    def send_command(self, command, **kwargs):
        raise SSHConnectionError(f"Command failed '{command}'")


def test_reader_aborts_when_session_dies():
    reader = FortiGateReader(_FlakySSH(alive=False))
    with pytest.raises(SSHConnectionError, match="session lost"):
        reader.read_audit_config()


def test_reader_refuses_to_parse_all_empty_outputs():
    # Session stays alive but every command fails — a blank config must not
    # be parsed into a bogus "successful" audit.
    reader = FortiGateReader(_FlakySSH(alive=True))
    with pytest.raises(RuntimeError, match="no output"):
        reader.read_audit_config()
