"""Orchestrates SSH connect, config read, quick audit, and DB persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from fw_obd.audit.quick_audit import AuditReport, QuickAuditEngine
from fw_obd.connection.ssh_handler import SSHCredentials, SSHHandler, ssh_session
from fw_obd.db.database import Database
from fw_obd.models.serialize import audit_report_to_json, device_to_json
from fw_obd.models.udm import Device
from fw_obd.parsers.fortigate.reader import FortiGateReader
from fw_obd.security.crypto import Cipher

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]


@dataclass
class ScanResult:
    device: Device
    report: AuditReport
    raw_config: str


def run_quick_audit_scan(
    credentials: SSHCredentials,
    db: Database,
    device_id: int,
    progress: Optional[ProgressCallback] = None,
) -> ScanResult:
    """
    Connect via SSH, run the audit command sequence, parse UDM, run Quick Audit,
    persist scan results, and update device inventory fields.
    """

    def _progress(msg: str) -> None:
        if progress:
            progress(msg)

    _progress("Connecting via SSH…")
    with ssh_session(credentials) as ssh:
        reader = FortiGateReader(ssh)

        def cmd_progress(command: str, idx: int, total: int) -> None:
            _progress(f"Reading config ({idx}/{total}): {command}")

        _progress("Running quick security audit…")
        device = reader.read_audit_config(progress_cb=cmd_progress)

        _progress("Backing up running configuration…")
        raw_config = reader.read_raw_backup()

    report = QuickAuditEngine().run(device)
    status = report.overall_status

    db.upsert_device(
        name=device.hostname or device.management_ip,
        management_ip=device.management_ip,
        vendor=device.vendor.value,
        model=device.model,
        hostname=device.hostname,
        serial_number=device.serial_number,
        software_version=device.software_version,
    )
    db.update_device_status(device_id, status)
    # raw_config contains secrets (PSKs, SNMP communities, RADIUS/LDAP creds), so it
    # is encrypted before persistence. Decrypt with Cipher().decrypt_str when reading.
    encrypted_raw_config = Cipher().encrypt_str(raw_config) if raw_config else ""
    db.save_scan(
        device_id=device_id,
        scan_type="audit",
        udm_json=device_to_json(device),
        raw_config=encrypted_raw_config,
        findings_json=audit_report_to_json(report),
    )
    db.log_action(
        action="scan",
        description=f"Quick audit completed — status: {status}, {len(report.findings)} findings",
        device_id=device_id,
        success=True,
    )
    logger.info(
        "Scan complete for %s: %d findings, status=%s",
        device.management_ip,
        len(report.findings),
        status,
    )
    return ScanResult(device=device, report=report, raw_config=raw_config)
