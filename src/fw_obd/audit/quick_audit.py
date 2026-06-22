"""Quick Audit engine — runs on first connect and produces prioritized findings."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from fw_obd.models.udm import Device, LicenseStatus, PolicyAction


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class Finding:
    severity: Severity
    title: str
    detail: str
    recommendation: str
    source: str = ""           # e.g. "Fortinet Best Practices Guide 2024 §3.1"
    auto_fixable: bool = False  # True = system can push a fix via Smart Terminal


@dataclass
class AuditReport:
    device_hostname: str
    device_model: str
    management_ip: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def critical(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.CRITICAL]

    @property
    def high(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.HIGH]

    @property
    def medium(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.MEDIUM]

    @property
    def low(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.LOW]

    @property
    def overall_status(self) -> str:
        if self.critical:
            return "critical"
        if self.high:
            return "warning"
        if self.medium:
            return "medium"
        return "healthy"


class QuickAuditEngine:
    """
    Runs a set of security checks against a parsed Device UDM object
    and returns an AuditReport with prioritized findings.

    All checks are stateless functions — add new ones by adding a method
    that starts with _check_ and appending a Finding to the list.
    """

    # Days threshold before expiry is flagged as EXPIRING_SOON
    LICENSE_WARN_DAYS = 30
    LICENSE_CRITICAL_DAYS = 7

    def run(self, device: Device) -> AuditReport:
        report = AuditReport(
            device_hostname=device.hostname,
            device_model=device.model,
            management_ip=device.management_ip,
        )
        findings: list[Finding] = []

        findings.extend(self._check_licenses(device))
        findings.extend(self._check_admin_access(device))
        findings.extend(self._check_logging(device))
        findings.extend(self._check_vpn_encryption(device))
        findings.extend(self._check_unused_policies(device))
        findings.extend(self._check_system_health(device))

        # Sort: critical first, then high, medium, low
        severity_order = {
            Severity.CRITICAL: 0,
            Severity.HIGH: 1,
            Severity.MEDIUM: 2,
            Severity.LOW: 3,
            Severity.INFO: 4,
        }
        findings.sort(key=lambda f: severity_order[f.severity])
        report.findings = findings
        return report

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_licenses(self, device: Device) -> list[Finding]:
        findings = []
        for lic in device.licenses:
            if lic.status == LicenseStatus.EXPIRED:
                findings.append(Finding(
                    severity=Severity.CRITICAL,
                    title=f"License expired: {lic.feature}",
                    detail=f"The {lic.feature} license has expired. Features may be disabled.",
                    recommendation="Renew the license immediately through your Fortinet reseller.",
                    source="Fortinet Support — License Management",
                    auto_fixable=False,
                ))
            elif lic.status == LicenseStatus.EXPIRING_SOON and lic.days_remaining is not None:
                sev = Severity.CRITICAL if lic.days_remaining <= self.LICENSE_CRITICAL_DAYS else Severity.HIGH
                findings.append(Finding(
                    severity=sev,
                    title=f"License expiring in {lic.days_remaining} days: {lic.feature}",
                    detail=f"The {lic.feature} license expires in {lic.days_remaining} days.",
                    recommendation="Plan license renewal with your Fortinet reseller before expiry.",
                    source="Fortinet Support — License Management",
                    auto_fixable=False,
                ))
        return findings

    def _check_admin_access(self, device: Device) -> list[Finding]:
        """Check for admin interfaces that accept connections from any source."""
        findings = []
        # Look for policies that allow management access from "all" sources
        mgmt_open = any(
            p for p in device.policies
            if p.action == PolicyAction.ALLOW
            and "all" in [a.lower() for a in p.source_addresses]
            and any(svc.lower() in ("https", "ssh", "telnet") for svc in p.services)
        )
        if mgmt_open:
            findings.append(Finding(
                severity=Severity.CRITICAL,
                title="Management access open to all source IPs",
                detail=(
                    "A policy allows HTTPS/SSH management access from any source IP. "
                    "This exposes the firewall management interface to the internet."
                ),
                recommendation="Restrict management access to specific trusted admin IPs or subnets.",
                source="Fortinet Security Best Practices Guide 2024 §2.1 — Admin Access Hardening",
                auto_fixable=True,
            ))
        return findings

    def _check_logging(self, device: Device) -> list[Finding]:
        """Flag allow policies that have logging disabled."""
        findings = []
        unlogged = device.policies_without_logging
        if unlogged:
            findings.append(Finding(
                severity=Severity.HIGH,
                title=f"Logging disabled on {len(unlogged)} allow policies",
                detail=(
                    f"{len(unlogged)} allow policies have logging disabled. "
                    "Without logging, traffic is invisible for security monitoring and compliance audits."
                ),
                recommendation="Enable logging ('log traffic all' or 'log traffic utm') on all allow policies.",
                source="Fortinet Security Best Practices Guide 2024 §5.2 — Logging Configuration",
                auto_fixable=True,
            ))
        return findings

    def _check_vpn_encryption(self, device: Device) -> list[Finding]:
        """Flag VPN tunnels using weak encryption or authentication."""
        findings = []
        weak_enc = ["3des", "des", "aes128"]
        weak_auth = ["md5", "sha1"]
        weak_dh = [1, 2, 5]

        for tunnel in device.vpn_tunnels:
            issues = []
            if any(w in tunnel.encryption.lower() for w in weak_enc):
                issues.append(f"weak encryption ({tunnel.encryption})")
            if any(w in tunnel.authentication.lower() for w in weak_auth):
                issues.append(f"weak authentication ({tunnel.authentication})")
            if tunnel.dh_group in weak_dh:
                issues.append(f"weak DH group ({tunnel.dh_group})")

            if issues:
                findings.append(Finding(
                    severity=Severity.HIGH,
                    title=f"VPN tunnel '{tunnel.name}' uses weak cryptography",
                    detail=f"Tunnel {tunnel.name} has: {', '.join(issues)}.",
                    recommendation=(
                        "Upgrade to AES-256 encryption, SHA-256+ authentication, and DH group 14 or higher. "
                        "Required for HIPAA and PCI-DSS compliance."
                    ),
                    source="Fortinet VPN Best Practices — Encryption Standards",
                    auto_fixable=False,
                ))
        return findings

    def _check_unused_policies(self, device: Device) -> list[Finding]:
        """Flag policies with zero hit count (if data available)."""
        findings = []
        zero_hit = [p for p in device.policies if p.hit_count is not None and p.hit_count == 0]
        if len(zero_hit) > 3:
            findings.append(Finding(
                severity=Severity.LOW,
                title=f"{len(zero_hit)} policies have zero traffic hits",
                detail=(
                    f"{len(zero_hit)} firewall policies show no traffic in their hit counters. "
                    "These may be unused rules consuming policy slots and adding noise."
                ),
                recommendation="Review and remove unused policies to keep the policy table clean.",
                source="Fortinet Security Best Practices Guide 2024 §4.1 — Policy Management",
                auto_fixable=False,
            ))
        return findings

    def _check_system_health(self, device: Device) -> list[Finding]:
        findings = []
        h = device.health
        if h.cpu_usage_pct is not None and h.cpu_usage_pct > 85:
            findings.append(Finding(
                severity=Severity.HIGH,
                title=f"High CPU usage: {h.cpu_usage_pct:.0f}%",
                detail="CPU usage is critically high. Performance and security inspection may be degraded.",
                recommendation="Investigate top CPU consumers and consider offloading or upgrading hardware.",
                source="Fortinet Performance Best Practices",
                auto_fixable=False,
            ))
        if h.memory_usage_pct is not None and h.memory_usage_pct > 90:
            findings.append(Finding(
                severity=Severity.CRITICAL,
                title=f"Critical memory usage: {h.memory_usage_pct:.0f}%",
                detail="Memory usage is at a critical level. The firewall may become unstable or reboot.",
                recommendation="Identify memory-intensive processes. Consider firmware upgrade or hardware upgrade.",
                source="Fortinet Performance Best Practices",
                auto_fixable=False,
            ))
        return findings
