"""FortiGate config parser — reads raw SSH output and builds UDM Device objects."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from fw_obd.models.udm import (
    AdminStatus,
    Device,
    Interface,
    License,
    LicenseStatus,
    PolicyAction,
    SecurityPolicy,
    StaticRoute,
    SystemHealth,
    Vendor,
    VirtualDomain,
    VPNStatus,
    VPNTunnel,
)

logger = logging.getLogger(__name__)


class FortiGateParser:
    """
    Parses raw CLI output from a FortiGate device into a Device UDM object.

    Usage:
        parser = FortiGateParser(management_ip="10.0.0.1")
        device = parser.parse(raw_outputs)

    raw_outputs is a dict mapping command string -> raw output string,
    as collected by FortiGateReader.
    """

    def __init__(self, management_ip: str) -> None:
        self._ip = management_ip

    def parse(self, raw_outputs: dict[str, str]) -> Device:
        """Entry point: build a full Device from a dict of command outputs."""
        from fw_obd.parsers.fortigate.commands import (
            GET_LICENSE_INFO,
            GET_SYSTEM_PERFORMANCE,
            GET_SYSTEM_STATUS,
            GET_VPN_IPSEC_TUNNEL_STATUS,
            SHOW_FIREWALL_POLICY,
            SHOW_ROUTER_STATIC,
            SHOW_SYSTEM_INTERFACE,
            SHOW_SYSTEM_VDOM,
            SHOW_VPN_IPSEC_PHASE1,
        )

        device = Device(
            vendor=Vendor.FORTINET,
            model="",
            hostname="",
            management_ip=self._ip,
            last_read=datetime.now(timezone.utc),
        )

        if GET_SYSTEM_STATUS in raw_outputs:
            self._parse_system_status(raw_outputs[GET_SYSTEM_STATUS], device)

        if GET_SYSTEM_PERFORMANCE in raw_outputs:
            self._parse_performance(raw_outputs[GET_SYSTEM_PERFORMANCE], device)

        if GET_LICENSE_INFO in raw_outputs:
            self._parse_licenses(raw_outputs[GET_LICENSE_INFO], device)

        if SHOW_SYSTEM_VDOM in raw_outputs:
            self._parse_vdoms(raw_outputs[SHOW_SYSTEM_VDOM], device)

        if SHOW_SYSTEM_INTERFACE in raw_outputs:
            self._parse_interfaces(raw_outputs[SHOW_SYSTEM_INTERFACE], device)

        if SHOW_ROUTER_STATIC in raw_outputs:
            self._parse_static_routes(raw_outputs[SHOW_ROUTER_STATIC], device)

        if SHOW_FIREWALL_POLICY in raw_outputs:
            self._parse_policies(raw_outputs[SHOW_FIREWALL_POLICY], device)

        if SHOW_VPN_IPSEC_PHASE1 in raw_outputs:
            self._parse_vpn_tunnels(
                raw_outputs[SHOW_VPN_IPSEC_PHASE1],
                raw_outputs.get(GET_VPN_IPSEC_TUNNEL_STATUS, ""),
                device,
            )

        return device

    # ------------------------------------------------------------------
    # System status
    # ------------------------------------------------------------------

    def _parse_system_status(self, output: str, device: Device) -> None:
        patterns = {
            "hostname": r"Hostname:\s+(.+)",
            "model": r"Platform Full Name:\s+(.+)|Version:\s+\S+\s+\((.+?)\)",
            "version": r"Version:\s+(\S+)",
            "serial": r"Serial-Number:\s+(\S+)",
            "firmware": r"Firmware Signature:\s+(.+)|Branch point:\s+(\d+)",
        }

        hostname = re.search(patterns["hostname"], output)
        if hostname:
            device.hostname = hostname.group(1).strip()

        # FortiOS "get system status" has platform in different fields
        model_match = re.search(r"Platform Full Name:\s+(.+)", output)
        if not model_match:
            model_match = re.search(r"Version:\s+\S+,Build\S+,\S+\s+\((.+?)\)", output)
        if model_match:
            device.model = model_match.group(1).strip()

        # FortiOS format: "Version: FortiGate-90G v7.4.2,build2571,..."
        version_match = re.search(r"Version:.*?v([\d.]+)", output)
        if version_match:
            device.software_version = version_match.group(1).strip()

        serial_match = re.search(r"Serial-Number:\s+(\S+)", output)
        if serial_match:
            device.serial_number = serial_match.group(1).strip()

    # ------------------------------------------------------------------
    # Performance / health
    # ------------------------------------------------------------------

    def _parse_performance(self, output: str, device: Device) -> None:
        cpu_match = re.search(r"CPU states:\s+(\d+)%", output)
        mem_match = re.search(r"Memory:\s+\S+\s+total.*?(\d+)%\s+used", output)
        uptime_match = re.search(r"Uptime:\s+(\d+)\s+days.*?(\d+)\s+hours.*?(\d+)\s+mins", output)

        health = SystemHealth()
        if cpu_match:
            health.cpu_usage_pct = float(cpu_match.group(1))
        if mem_match:
            health.memory_usage_pct = float(mem_match.group(1))
        if uptime_match:
            days, hours, mins = int(uptime_match.group(1)), int(uptime_match.group(2)), int(uptime_match.group(3))
            health.uptime_seconds = days * 86400 + hours * 3600 + mins * 60
        device.health = health

    # ------------------------------------------------------------------
    # Licenses
    # ------------------------------------------------------------------

    def _parse_licenses(self, output: str, device: Device) -> None:
        licenses: list[License] = []

        # FortiGate license output lists features with expiry dates
        # Pattern: "Feature Name: YYYY-MM-DD" or "expires YYYY-MM-DD"
        feature_pattern = re.compile(
            r"([\w\-]+)\s*:\s*(?:expires?\s+)?(\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|never|n/a|permanent)",
            re.IGNORECASE,
        )
        today = datetime.utcnow().date()

        for match in feature_pattern.finditer(output):
            feature_name = match.group(1).strip()
            expiry_raw = match.group(2).strip().lower()

            if expiry_raw in ("never", "n/a", "permanent"):
                lic = License(feature=feature_name, status=LicenseStatus.ACTIVE)
            else:
                try:
                    expiry_date = datetime.strptime(expiry_raw, "%Y-%m-%d")
                    days_left = (expiry_date.date() - today).days
                    if days_left < 0:
                        status = LicenseStatus.EXPIRED
                    elif days_left <= 30:
                        status = LicenseStatus.EXPIRING_SOON
                    else:
                        status = LicenseStatus.ACTIVE
                    lic = License(
                        feature=feature_name,
                        status=status,
                        expiry_date=expiry_date,
                        days_remaining=days_left,
                    )
                except ValueError:
                    lic = License(feature=feature_name, status=LicenseStatus.UNKNOWN)

            licenses.append(lic)

        device.licenses = licenses

    # ------------------------------------------------------------------
    # VDOMs
    # ------------------------------------------------------------------

    def _parse_vdoms(self, output: str, device: Device) -> None:
        vdoms: list[VirtualDomain] = []
        # "show system vdom" lists vdom entries with "edit <name>"
        vdom_names = re.findall(r'edit\s+"([^"]+)"', output)

        for name in vdom_names:
            is_root = name.lower() == "root"
            vdoms.append(VirtualDomain(name=name, is_root=is_root))

        if not vdoms:
            # Device may not have multi-VDOM enabled — add implicit root
            vdoms.append(VirtualDomain(name="root", is_root=True))

        device.virtual_domains = vdoms

    # ------------------------------------------------------------------
    # Interfaces
    # ------------------------------------------------------------------

    def _parse_interfaces(self, output: str, device: Device) -> None:
        interfaces: list[Interface] = []

        # Each interface block starts with "edit <name>" and ends with "next"
        blocks = re.split(r'\bedit\s+"([^"]+)"', output)

        for i in range(1, len(blocks), 2):
            name = blocks[i].strip()
            body = blocks[i + 1] if i + 1 < len(blocks) else ""

            iface = Interface(name=name)

            ip_match = re.search(r'set ip (\S+)\s+(\S+)', body)
            if ip_match:
                iface.ip_address = ip_match.group(1)
                iface.netmask = ip_match.group(2)

            status_match = re.search(r'set status (up|down)', body, re.IGNORECASE)
            if status_match:
                iface.admin_status = AdminStatus(status_match.group(1).lower())

            desc_match = re.search(r'set description "([^"]*)"', body)
            if desc_match:
                iface.description = desc_match.group(1)

            vlan_match = re.search(r'set vlanid (\d+)', body)
            if vlan_match:
                iface.vlan_id = int(vlan_match.group(1))

            mtu_match = re.search(r'set mtu (\d+)', body)
            if mtu_match:
                iface.mtu = int(mtu_match.group(1))

            vdom_match = re.search(r'set vdom "([^"]+)"', body)
            if vdom_match:
                iface.vdom = vdom_match.group(1)

            interfaces.append(iface)

        device.interfaces = interfaces

    # ------------------------------------------------------------------
    # Static routes
    # ------------------------------------------------------------------

    def _parse_static_routes(self, output: str, device: Device) -> None:
        routes: list[StaticRoute] = []
        blocks = re.split(r'\bedit\s+(\d+)', output)

        for i in range(1, len(blocks), 2):
            body = blocks[i + 1] if i + 1 < len(blocks) else ""

            dst_match = re.search(r'set dst (\S+)\s+(\S+)', body)
            gw_match = re.search(r'set gateway (\S+)', body)
            dev_match = re.search(r'set device "([^"]+)"', body)
            dist_match = re.search(r'set distance (\d+)', body)
            vdom_match = re.search(r'set vdom "([^"]+)"', body)

            if dst_match:
                route = StaticRoute(
                    destination=dst_match.group(1),
                    netmask=dst_match.group(2),
                    gateway=gw_match.group(1) if gw_match else None,
                    interface=dev_match.group(1) if dev_match else None,
                    distance=int(dist_match.group(1)) if dist_match else 10,
                    vdom=vdom_match.group(1) if vdom_match else "root",
                )
                routes.append(route)

        device.routes = routes

    # ------------------------------------------------------------------
    # Firewall policies
    # ------------------------------------------------------------------

    def _parse_policies(self, output: str, device: Device) -> None:
        policies: list[SecurityPolicy] = []
        blocks = re.split(r'\bedit\s+(\d+)', output)

        for i in range(1, len(blocks), 2):
            try:
                policy_id = int(blocks[i].strip())
            except ValueError:
                continue
            body = blocks[i + 1] if i + 1 < len(blocks) else ""

            name_match = re.search(r'set name "([^"]*)"', body)
            srcintf_match = re.search(r'set srcintf "([^"]+)"', body)
            dstintf_match = re.search(r'set dstintf "([^"]+)"', body)
            action_match = re.search(r'set action (\w+)', body)
            logtraffic_match = re.search(r'set logtraffic (\w+)', body)
            nat_match = re.search(r'set nat (enable|disable)', body)
            status_match = re.search(r'set status (enable|disable)', body)
            vdom_match = re.search(r'# vdom="([^"]+)"', body)

            src_addrs = re.findall(r'set srcaddr "([^"]+)"', body)
            dst_addrs = re.findall(r'set dstaddr "([^"]+)"', body)
            services = re.findall(r'set service "([^"]+)"', body)

            # FortiGate uses "accept" not "allow"
            _action_map = {"accept": "allow", "deny": "deny", "drop": "drop"}
            raw_action = action_match.group(1).lower() if action_match else "deny"
            action = PolicyAction(_action_map.get(raw_action, "deny"))

            log_value = logtraffic_match.group(1) if logtraffic_match else "disable"
            logging_on = log_value in ("all", "utm", "enable")

            policy = SecurityPolicy(
                policy_id=policy_id,
                name=name_match.group(1) if name_match else f"policy-{policy_id}",
                source_interface=srcintf_match.group(1) if srcintf_match else "",
                destination_interface=dstintf_match.group(1) if dstintf_match else "",
                source_addresses=src_addrs,
                destination_addresses=dst_addrs,
                services=services,
                action=action,
                logging_enabled=logging_on,
                nat_enabled=(nat_match.group(1) == "enable" if nat_match else False),
                enabled=(status_match.group(1) == "enable" if status_match else True),
                vdom=vdom_match.group(1) if vdom_match else "root",
            )
            policies.append(policy)

        device.policies = policies

    # ------------------------------------------------------------------
    # VPN tunnels
    # ------------------------------------------------------------------

    def _parse_vpn_tunnels(self, phase1_output: str, status_output: str, device: Device) -> None:
        tunnels: list[VPNTunnel] = []
        up_tunnels: set[str] = set()

        # Parse tunnel status output to know which are UP
        for line in status_output.splitlines():
            if "ESTABLISHED" in line or "up" in line.lower():
                name_match = re.search(r'"([^"]+)"', line)
                if name_match:
                    up_tunnels.add(name_match.group(1))

        blocks = re.split(r'\bedit\s+"([^"]+)"', phase1_output)
        for i in range(1, len(blocks), 2):
            name = blocks[i].strip()
            body = blocks[i + 1] if i + 1 < len(blocks) else ""

            remote_gw = re.search(r'set remote-gw (\S+)', body)
            local_gw = re.search(r'set local-gw (\S+)', body)
            ike_ver = re.search(r'set ike-version (\d)', body)
            enc_match = re.search(r'set proposal (\S+)', body)
            dhgrp = re.search(r'set dhgrp (\d+)', body)

            status = VPNStatus.UP if name in up_tunnels else VPNStatus.DOWN

            tunnel = VPNTunnel(
                name=name,
                local_gateway=local_gw.group(1) if local_gw else "",
                remote_gateway=remote_gw.group(1) if remote_gw else "",
                status=status,
                ike_version=int(ike_ver.group(1)) if ike_ver else 1,
                encryption=enc_match.group(1).split("-")[0] if enc_match else "aes256",
                dh_group=int(dhgrp.group(1)) if dhgrp else 14,
            )
            tunnels.append(tunnel)

        device.vpn_tunnels = tunnels
