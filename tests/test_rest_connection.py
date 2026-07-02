"""Tests for the HTTPS/REST connection mode (issue #27)."""

from __future__ import annotations

import pytest

from fw_obd.connection import rest_client
from fw_obd.connection.rest_client import (
    FortiGateRESTClient,
    RESTAuthError,
    RESTConnectionError,
    RESTCredentials,
)
from fw_obd.db.database import Database
from fw_obd.models.udm import LicenseStatus, PolicyAction, Vendor
from fw_obd.parsers.fortigate.rest_reader import FortiGateRESTReader
from fw_obd.services import device_scan


# ------------------------------------------------------------------ fixtures

class _FakeResponse:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class _FakeSession:
    """Stands in for requests.Session; routes GETs by URL substring."""

    routes: dict = {}
    raise_on_get: Exception | None = None

    def __init__(self):
        self.headers = {}
        self.verify = True
        self.closed = False

    def get(self, url, params=None, timeout=None):
        if _FakeSession.raise_on_get:
            raise _FakeSession.raise_on_get
        for fragment, resp in _FakeSession.routes.items():
            if fragment in url:
                return resp
        return _FakeResponse(404)

    def close(self):
        self.closed = True


@pytest.fixture
def fake_session(monkeypatch):
    _FakeSession.routes = {
        "monitor/system/status": _FakeResponse(
            200,
            {
                "results": {"model_name": "FortiGate", "model_number": "60F", "hostname": "fw-hq"},
                "serial": "FGT60F000000",
                "version": "v7.2.8",
                "status": "success",
            },
        )
    }
    _FakeSession.raise_on_get = None
    monkeypatch.setattr(rest_client.requests, "Session", _FakeSession)
    return _FakeSession


def _creds(**kw) -> RESTCredentials:
    return RESTCredentials(host="10.0.0.1", api_key="k", **kw)


# ---------------------------------------------------------------- REST client

def test_connect_validates_via_status_endpoint(fake_session):
    client = FortiGateRESTClient(_creds())
    client.connect()
    assert client.is_connected
    client.disconnect()
    assert not client.is_connected


def test_connect_auth_failure_raises_auth_error(fake_session):
    fake_session.routes = {"monitor/system/status": _FakeResponse(401)}
    with pytest.raises(RESTAuthError):
        FortiGateRESTClient(_creds()).connect()


def test_connect_unreachable_raises_connection_error(fake_session):
    fake_session.raise_on_get = rest_client.requests.exceptions.ConnectionError("refused")
    with pytest.raises(RESTConnectionError):
        FortiGateRESTClient(_creds()).connect()


def test_envelope_serial_and_version_are_folded_into_results(fake_session):
    client = FortiGateRESTClient(_creds())
    client.connect()
    results = client.get_monitor("system/status")
    assert results["serial"] == "FGT60F000000"
    assert results["version"] == "v7.2.8"
    assert results["hostname"] == "fw-hq"


def test_self_signed_opt_out_disables_verify(fake_session):
    client = FortiGateRESTClient(_creds(verify_tls=False))
    client.connect()
    assert client._session.verify is False


# ---------------------------------------------------------------- REST reader

class _FakeClient:
    """FortiGateRESTClient stand-in with canned per-path payloads."""

    class _creds:
        host = "10.0.0.1"

    def __init__(self, payloads: dict, text: str = "config ...") -> None:
        self._payloads = payloads
        self._text = text

    def _lookup(self, path):
        if path in self._payloads:
            value = self._payloads[path]
            if isinstance(value, Exception):
                raise value
            return value
        raise RESTConnectionError(f"HTTP 404 on {path}")

    def get_monitor(self, path, params=None):
        return self._lookup(path)

    def get_cmdb(self, path, params=None):
        return self._lookup(path)

    def get_text(self, path, params=None, read_timeout=120.0):
        return self._text


_STATUS = {
    "model_name": "FortiGate",
    "model_number": "60F",
    "hostname": "fw-hq",
    "serial": "FGT60F000000",
    "version": "v7.2.8",
}


def test_reader_maps_identity_policies_vpn_and_licenses():
    payloads = {
        "system/status": _STATUS,
        "system/resource/usage": {"cpu": [{"current": 12}], "mem": [{"current": 55}]},
        "license/status": {
            "forticare": {"status": "licensed"},
            "antivirus": {"status": "expired"},
        },
        "system/interface": [
            {"name": "wan1", "ip": "1.2.3.4 255.255.255.0", "status": "up"},
        ],
        "firewall/policy": [
            {
                "policyid": 7,
                "name": "lan-out",
                "srcintf": [{"name": "lan"}],
                "dstintf": [{"name": "wan1"}],
                "srcaddr": [{"name": "all"}],
                "dstaddr": [{"name": "all"}],
                "service": [{"name": "HTTPS"}],
                "action": "accept",
                "logtraffic": "disable",
                "nat": "enable",
                "status": "enable",
            }
        ],
        "vpn.ipsec/phase1-interface": [
            {"name": "hq-branch", "remote-gw": "5.6.7.8", "proposal": "aes256-sha256 3des-md5", "dhgrp": "14 5"},
        ],
    }
    device = FortiGateRESTReader(_FakeClient(payloads)).read_audit_config()

    assert device.vendor == Vendor.FORTINET
    assert device.hostname == "fw-hq"
    assert device.model == "FortiGate 60F"
    assert device.serial_number == "FGT60F000000"
    assert device.software_version == "v7.2.8"
    assert device.health.cpu_usage_pct == 12
    assert {l.feature: l.status for l in device.licenses} == {
        "forticare": LicenseStatus.ACTIVE,
        "antivirus": LicenseStatus.EXPIRED,
    }
    policy = device.policies[0]
    assert policy.policy_id == 7 and policy.action == PolicyAction.ALLOW
    assert policy.logging_enabled is False and policy.nat_enabled is True
    tunnel = device.vpn_tunnels[0]
    assert "3des" in tunnel.encryption and "md5" in tunnel.authentication
    assert tunnel.dh_group == 5  # weakest offered group is what the audit sees


def test_reader_requires_identity_endpoint():
    payloads = {"system/status": RESTConnectionError("HTTP 500")}
    with pytest.raises(RESTConnectionError, match="identity"):
        FortiGateRESTReader(_FakeClient(payloads)).read_audit_config()


def test_reader_tolerates_partial_endpoint_failures():
    payloads = {"system/status": _STATUS}  # everything else 404s
    device = FortiGateRESTReader(_FakeClient(payloads)).read_audit_config()
    assert device.hostname == "fw-hq"
    assert device.policies == [] and device.vpn_tunnels == []


# ------------------------------------------------------- scan service (REST)

class _FakeRESTScanClient:
    connect_error: Exception | None = None

    def __init__(self, credentials, timeout: float = 15.0) -> None:
        pass

    def connect(self) -> None:
        if _FakeRESTScanClient.connect_error:
            raise _FakeRESTScanClient.connect_error

    def disconnect(self) -> None:
        pass


class _FakeRESTScanReader:
    audit_error: Exception | None = None

    def __init__(self, client) -> None:
        pass

    def read_audit_config(self, progress_cb=None):
        if _FakeRESTScanReader.audit_error:
            raise _FakeRESTScanReader.audit_error
        from fw_obd.models.udm import Device

        return Device(vendor=Vendor.FORTINET, model="FortiGate-60F", hostname="fw1", management_ip="10.0.0.1")

    def read_raw_backup(self) -> str:
        return "config ..."


@pytest.fixture
def rest_scan_env(tmp_path, monkeypatch):
    _FakeRESTScanClient.connect_error = None
    _FakeRESTScanReader.audit_error = None
    monkeypatch.setattr(device_scan, "FortiGateRESTClient", _FakeRESTScanClient)
    monkeypatch.setattr(device_scan, "FortiGateRESTReader", _FakeRESTScanReader)
    db = Database(tmp_path / "t.db")
    device_id = db.upsert_device(name="fw1", management_ip="10.0.0.1")
    return db, device_id, RESTCredentials(host="10.0.0.1", api_key="k")


def test_rest_scan_happy_path_persists(rest_scan_env):
    db, device_id, creds = rest_scan_env
    result = device_scan.run_quick_audit_scan(creds, db, device_id)
    assert result.device.hostname == "fw1"
    assert len(db.list_scans()) == 1
    assert db.get_device(device_id)["last_seen"]


def test_rest_connect_failure_classified_unreachable(rest_scan_env):
    db, device_id, creds = rest_scan_env
    _FakeRESTScanClient.connect_error = RESTConnectionError("refused")
    with pytest.raises(RESTConnectionError):
        device_scan.run_quick_audit_scan(creds, db, device_id)
    assert db.list_scans() == []


def test_rest_midscan_failure_is_scan_error(rest_scan_env):
    db, device_id, creds = rest_scan_env
    _FakeRESTScanReader.audit_error = RESTConnectionError("HTTP 500 mid-scan")
    with pytest.raises(device_scan.ScanError):
        device_scan.run_quick_audit_scan(creds, db, device_id)
    assert db.list_scans() == []
