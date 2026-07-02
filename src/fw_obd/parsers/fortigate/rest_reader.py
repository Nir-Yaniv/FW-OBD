"""FortiGate REST reader — builds a Device UDM from /api/v2 responses (issue #27).

Same read_audit_config / read_raw_backup surface as the SSH FortiGateReader so
services.device_scan can drive either transport.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Optional

from fw_obd.connection.rest_client import FortiGateRESTClient, RESTConnectionError
from fw_obd.models.udm import (
    AdminStatus,
    Device,
    Interface,
    License,
    LicenseStatus,
    PolicyAction,
    SecurityPolicy,
    SystemHealth,
    Vendor,
    VPNTunnel,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int], None]

# (label, method, path) — the REST equivalent of commands.AUDIT_SEQUENCE
_AUDIT_STEPS = [
    ("system status", "get_monitor", "system/status"),
    ("resource usage", "get_monitor", "system/resource/usage"),
    ("license status", "get_monitor", "license/status"),
    ("interfaces", "get_cmdb", "system/interface"),
    ("firewall policies", "get_cmdb", "firewall/policy"),
    ("VPN phase1", "get_cmdb", "vpn.ipsec/phase1-interface"),
]


class FortiGateRESTReader:
    """Reads audit data over the FortiOS REST API and maps it to the UDM."""

    def __init__(self, client: FortiGateRESTClient) -> None:
        self._client = client
        self._host = client._creds.host

    # ------------------------------------------------------------------

    def read_audit_config(self, progress_cb: Optional[ProgressCallback] = None) -> Device:
        raw: dict[str, object] = {}
        total = len(_AUDIT_STEPS)
        failures = 0
        for idx, (label, method, path) in enumerate(_AUDIT_STEPS, start=1):
            if progress_cb:
                progress_cb(label, idx, total)
            logger.debug("REST [%d/%d]: %s", idx, total, path)
            try:
                raw[path] = getattr(self._client, method)(path)
            except RESTConnectionError as exc:
                logger.warning("REST call failed '%s': %s", path, exc)
                raw[path] = None
                failures += 1

        # The identity endpoint is required: a device with no identity would
        # produce the misleading "healthy on empty config" audit (issue #31).
        if raw.get("system/status") is None:
            raise RESTConnectionError(
                "Required endpoint monitor/system/status failed — refusing to audit "
                "a device without identity data"
            )
        if failures == total:
            raise RESTConnectionError("Every REST endpoint failed — nothing to audit")

        return self._build_device(raw)

    def read_raw_backup(self) -> str:
        """Full configuration backup via the REST backup endpoint."""
        logger.info("Reading full configuration for backup via REST")
        return self._client.get_text(
            "monitor/system/config/backup", params={"scope": "global"}, read_timeout=120.0
        )

    # ------------------------------------------------------------------
    # UDM mapping
    # ------------------------------------------------------------------

    def _build_device(self, raw: dict) -> Device:
        status = raw.get("system/status") or {}
        model = " ".join(
            p for p in (status.get("model_name"), status.get("model_number")) if p
        ) or str(status.get("model", ""))
        device = Device(
            vendor=Vendor.FORTINET,
            model=model,
            hostname=str(status.get("hostname", "")),
            management_ip=self._host,
            software_version=str(status.get("version", "")),
            serial_number=str(status.get("serial", status.get("serial_number", ""))),
            last_read=datetime.now(timezone.utc),
        )
        device.health = self._parse_health(raw.get("system/resource/usage"))
        device.licenses = self._parse_licenses(raw.get("license/status"))
        device.interfaces = self._parse_interfaces(raw.get("system/interface"))
        device.policies = self._parse_policies(raw.get("firewall/policy"))
        device.vpn_tunnels = self._parse_vpn(raw.get("vpn.ipsec/phase1-interface"))
        return device

    @staticmethod
    def _parse_health(usage: object) -> SystemHealth:
        health = SystemHealth()
        if not isinstance(usage, dict):
            return health

        def current(metric: str) -> Optional[float]:
            entries = usage.get(metric)
            if isinstance(entries, list) and entries and isinstance(entries[0], dict):
                value = entries[0].get("current")
                return float(value) if value is not None else None
            return None

        health.cpu_usage_pct = current("cpu")
        health.memory_usage_pct = current("mem")
        health.disk_usage_pct = current("disk")
        return health

    @staticmethod
    def _parse_licenses(payload: object) -> list[License]:
        if not isinstance(payload, dict):
            return []
        licenses: list[License] = []
        for feature, info in payload.items():
            if not isinstance(info, dict) or "status" not in info:
                continue
            raw_status = str(info.get("status", "")).lower()
            status = LicenseStatus.UNKNOWN
            if raw_status in ("licensed", "registered", "valid"):
                status = LicenseStatus.ACTIVE
            elif raw_status in ("expired", "expires"):
                status = LicenseStatus.EXPIRED
            expiry = None
            days_remaining = None
            expires = info.get("expires")
            if isinstance(expires, (int, float)) and expires > 0:
                expiry = datetime.fromtimestamp(expires, tz=timezone.utc)
                days_remaining = (expiry - datetime.now(timezone.utc)).days
                if status == LicenseStatus.ACTIVE and days_remaining <= 30:
                    status = LicenseStatus.EXPIRING_SOON
            licenses.append(
                License(
                    feature=feature,
                    status=status,
                    expiry_date=expiry,
                    days_remaining=days_remaining,
                )
            )
        return licenses

    @staticmethod
    def _parse_interfaces(payload: object) -> list[Interface]:
        if not isinstance(payload, list):
            return []
        interfaces = []
        for row in payload:
            if not isinstance(row, dict) or not row.get("name"):
                continue
            ip_address = netmask = None
            ip_field = str(row.get("ip", "")).strip()
            if ip_field and ip_field != "0.0.0.0 0.0.0.0":
                parts = ip_field.split()
                ip_address = parts[0]
                netmask = parts[1] if len(parts) > 1 else None
            interfaces.append(
                Interface(
                    name=row["name"],
                    ip_address=ip_address,
                    netmask=netmask,
                    admin_status=(
                        AdminStatus.UP if row.get("status") == "up" else AdminStatus.DOWN
                    ),
                    description=str(row.get("description", "") or ""),
                    mtu=row.get("mtu"),
                    vdom=str(row.get("vdom", "root")),
                )
            )
        return interfaces

    @staticmethod
    def _parse_policies(payload: object) -> list[SecurityPolicy]:
        if not isinstance(payload, list):
            return []

        def names(row: dict, key: str) -> list[str]:
            return [e.get("name", "") for e in row.get(key, []) if isinstance(e, dict)]

        policies = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            src_if = names(row, "srcintf")
            dst_if = names(row, "dstintf")
            policies.append(
                SecurityPolicy(
                    policy_id=int(row.get("policyid", 0)),
                    name=str(row.get("name", "")),
                    source_interface=src_if[0] if src_if else "",
                    destination_interface=dst_if[0] if dst_if else "",
                    source_addresses=names(row, "srcaddr"),
                    destination_addresses=names(row, "dstaddr"),
                    services=names(row, "service"),
                    action=(
                        PolicyAction.ALLOW if row.get("action") == "accept" else PolicyAction.DENY
                    ),
                    logging_enabled=row.get("logtraffic") in ("all", "utm"),
                    nat_enabled=row.get("nat") == "enable",
                    enabled=row.get("status", "enable") == "enable",
                )
            )
        return policies

    @staticmethod
    def _parse_vpn(payload: object) -> list[VPNTunnel]:
        if not isinstance(payload, list):
            return []
        tunnels = []
        for row in payload:
            if not isinstance(row, dict) or not row.get("name"):
                continue
            # proposal: "aes256-sha256 aes128-sha1" — join all offered algos so
            # the audit's weak-crypto substring checks see every proposal.
            encs: list[str] = []
            auths: list[str] = []
            for prop in str(row.get("proposal", "")).split():
                enc, _, auth = prop.partition("-")
                if enc and enc not in encs:
                    encs.append(enc)
                if auth and auth not in auths:
                    auths.append(auth)
            dh_groups = [int(g) for g in str(row.get("dhgrp", "")).split() if g.isdigit()]
            tunnels.append(
                VPNTunnel(
                    name=row["name"],
                    local_gateway=str(row.get("interface", "") or ""),
                    remote_gateway=str(row.get("remote-gw", "") or ""),
                    ike_version=int(row.get("ike-version", 2) or 2),
                    encryption=" ".join(encs) or "unknown",
                    authentication=" ".join(auths) or "unknown",
                    # audit flags weak groups — report the weakest one offered
                    dh_group=min(dh_groups) if dh_groups else 14,
                )
            )
        return tunnels
