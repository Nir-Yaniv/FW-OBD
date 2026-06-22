"""Tests for FortiGate parser using recorded CLI output fixtures."""

from pathlib import Path

import pytest

from fw_obd.models.udm import AdminStatus, PolicyAction, Vendor
from fw_obd.parsers.fortigate.commands import (
    GET_SYSTEM_STATUS,
    SHOW_FIREWALL_POLICY,
    SHOW_SYSTEM_INTERFACE,
)
from fw_obd.parsers.fortigate.parser import FortiGateParser

FIXTURES = Path(__file__).parent / "fixtures" / "fortigate"


def load_fixture(filename: str) -> str:
    return (FIXTURES / filename).read_text(encoding="utf-8")


@pytest.fixture
def raw_outputs() -> dict[str, str]:
    return {
        GET_SYSTEM_STATUS: load_fixture("system_status.txt"),
        SHOW_FIREWALL_POLICY: load_fixture("firewall_policy.txt"),
        SHOW_SYSTEM_INTERFACE: load_fixture("system_interface.txt"),
    }


@pytest.fixture
def device(raw_outputs):
    parser = FortiGateParser(management_ip="10.0.0.1")
    return parser.parse(raw_outputs)


class TestSystemStatus:
    def test_vendor(self, device):
        assert device.vendor == Vendor.FORTINET

    def test_hostname(self, device):
        assert device.hostname == "FG-90G-NewJersey"

    def test_model(self, device):
        assert "FortiGate-90G" in device.model

    def test_serial(self, device):
        assert device.serial_number.startswith("FG90G")

    def test_software_version(self, device):
        assert device.software_version.startswith("7.4")


class TestInterfaces:
    def test_interface_count(self, device):
        assert len(device.interfaces) == 3

    def test_wan1_ip(self, device):
        wan1 = next(i for i in device.interfaces if i.name == "wan1")
        assert wan1.ip_address == "203.0.113.1"
        assert wan1.netmask == "255.255.255.0"

    def test_internal_status(self, device):
        internal = next(i for i in device.interfaces if i.name == "internal")
        assert internal.admin_status == AdminStatus.UP

    def test_interface_description(self, device):
        wan1 = next(i for i in device.interfaces if i.name == "wan1")
        assert wan1.description == "ISP Primary"


class TestPolicies:
    def test_policy_count(self, device):
        assert len(device.policies) == 3

    def test_lan_to_wan_action(self, device):
        p = next(p for p in device.policies if p.name == "LAN-to-WAN")
        assert p.action == PolicyAction.ALLOW

    def test_lan_to_wan_logging(self, device):
        p = next(p for p in device.policies if p.name == "LAN-to-WAN")
        assert p.logging_enabled is True

    def test_vpn_policy_logging_disabled(self, device):
        p = next(p for p in device.policies if "VPN" in p.name)
        assert p.logging_enabled is False

    def test_nat_on_lan_to_wan(self, device):
        p = next(p for p in device.policies if p.name == "LAN-to-WAN")
        assert p.nat_enabled is True


class TestAuditHelper:
    def test_policies_without_logging(self, device):
        unlogged = device.policies_without_logging
        # VPN-Hospital-to-NJ has logtraffic disable and action accept → flagged
        assert any("VPN" in p.name for p in unlogged)

    def test_lan_to_wan_not_in_unlogged(self, device):
        unlogged = device.policies_without_logging
        assert not any(p.name == "LAN-to-WAN" for p in unlogged)
