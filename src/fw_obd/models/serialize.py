"""Serialize UDM objects and audit reports to JSON for SQLite storage."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from fw_obd.audit.quick_audit import AuditReport, Finding, Severity
from fw_obd.models.udm import Device


def _default(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def device_to_json(device: Device) -> str:
    return json.dumps(asdict(device), default=_default)


def audit_report_to_json(report: AuditReport) -> str:
    return json.dumps(asdict(report), default=_default)


def audit_report_from_json(data: str) -> AuditReport:
    raw = json.loads(data)
    findings = [
        Finding(
            severity=Severity(f["severity"]),
            title=f["title"],
            detail=f["detail"],
            recommendation=f["recommendation"],
            source=f.get("source", ""),
            auto_fixable=f.get("auto_fixable", False),
        )
        for f in raw.get("findings", [])
    ]
    return AuditReport(
        device_hostname=raw.get("device_hostname", ""),
        device_model=raw.get("device_model", ""),
        management_ip=raw.get("management_ip", ""),
        findings=findings,
    )
