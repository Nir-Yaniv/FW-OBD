"""Universal Data Model — vendor-neutral internal representation of firewall state."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Vendor(str, Enum):
    FORTINET = "Fortinet"
    PALO_ALTO = "Palo Alto"
    CISCO = "Cisco"
    CHECK_POINT = "Check Point"
    UNKNOWN = "Unknown"


class AdminStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


class VPNStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    NEGOTIATING = "negotiating"
    UNKNOWN = "unknown"


class PolicyAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    DROP = "drop"


class LicenseStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    EXPIRING_SOON = "expiring_soon"
    UNKNOWN = "unknown"


@dataclass
class Interface:
    name: str
    ip_address: Optional[str] = None
    netmask: Optional[str] = None
    admin_status: AdminStatus = AdminStatus.UNKNOWN
    description: str = ""
    vlan_id: Optional[int] = None
    mtu: Optional[int] = None
    is_physical: bool = True
    vdom: str = "root"


@dataclass
class StaticRoute:
    destination: str
    netmask: str
    gateway: Optional[str] = None
    interface: Optional[str] = None
    distance: int = 10
    vdom: str = "root"


@dataclass
class SecurityProfile:
    name: str
    profile_type: str  # antivirus, ips, webfilter, etc.


@dataclass
class SecurityPolicy:
    policy_id: int
    name: str
    source_interface: str
    destination_interface: str
    source_addresses: list[str] = field(default_factory=list)
    destination_addresses: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    action: PolicyAction = PolicyAction.DENY
    logging_enabled: bool = False
    nat_enabled: bool = False
    security_profiles: list[SecurityProfile] = field(default_factory=list)
    hit_count: Optional[int] = None
    enabled: bool = True
    vdom: str = "root"


@dataclass
class VPNTunnel:
    name: str
    local_gateway: str
    remote_gateway: str
    status: VPNStatus = VPNStatus.UNKNOWN
    ike_version: int = 2
    encryption: str = "aes256"
    authentication: str = "sha256"
    dh_group: int = 14
    local_networks: list[str] = field(default_factory=list)
    remote_networks: list[str] = field(default_factory=list)
    vdom: str = "root"


@dataclass
class License:
    feature: str
    status: LicenseStatus = LicenseStatus.UNKNOWN
    expiry_date: Optional[datetime] = None
    days_remaining: Optional[int] = None


@dataclass
class SystemHealth:
    cpu_usage_pct: Optional[float] = None
    memory_usage_pct: Optional[float] = None
    disk_usage_pct: Optional[float] = None
    uptime_seconds: Optional[int] = None


@dataclass
class VirtualDomain:
    name: str
    is_root: bool = False
    interfaces: list[Interface] = field(default_factory=list)
    policies: list[SecurityPolicy] = field(default_factory=list)
    routes: list[StaticRoute] = field(default_factory=list)
    vpn_tunnels: list[VPNTunnel] = field(default_factory=list)


@dataclass
class Device:
    """Top-level UDM object representing a single managed firewall."""
    vendor: Vendor
    model: str
    hostname: str
    management_ip: str

    software_version: str = ""
    serial_number: str = ""
    firmware_version: str = ""

    health: SystemHealth = field(default_factory=SystemHealth)
    licenses: list[License] = field(default_factory=list)

    interfaces: list[Interface] = field(default_factory=list)
    routes: list[StaticRoute] = field(default_factory=list)
    policies: list[SecurityPolicy] = field(default_factory=list)
    vpn_tunnels: list[VPNTunnel] = field(default_factory=list)
    virtual_domains: list[VirtualDomain] = field(default_factory=list)

    last_read: Optional[datetime] = None
    raw_config: str = ""

    @property
    def has_vdoms(self) -> bool:
        return len(self.virtual_domains) > 0

    @property
    def expiring_licenses(self) -> list[License]:
        return [
            lic for lic in self.licenses
            if lic.status in (LicenseStatus.EXPIRED, LicenseStatus.EXPIRING_SOON)
        ]

    @property
    def policies_without_logging(self) -> list[SecurityPolicy]:
        return [p for p in self.policies if not p.logging_enabled and p.action == PolicyAction.ALLOW]
