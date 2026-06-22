"""Import device inventory from CSV (SolarWinds, PRTG, or generic exports)."""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Common column aliases from monitoring tools → canonical field names
COLUMN_ALIASES: dict[str, list[str]] = {
    "management_ip": [
        "site ip",
        "ip",
        "ip address",
        "management ip",
        "mgmt ip",
        "device ip",
        "node ip",
    ],
    "name": [
        "site name",
        "device name",
        "hostname",
        "caption",
        "name",
        "node name",
    ],
    "vendor": ["vendor", "brand", "manufacturer", "device type"],
    "location": ["location", "site", "city"],
    "region": ["region", "group", "custom property"],
}


@dataclass
class ImportRow:
    name: str
    management_ip: str
    vendor: str = "Fortinet"
    location: str = ""
    region: str = ""


@dataclass
class ImportPreview:
    rows: list[ImportRow]
    skipped: int
    column_map: dict[str, str]


def _normalize_header(header: str) -> str:
    return header.strip().lower()


def _map_headers(fieldnames: list[str]) -> dict[str, str]:
    """Map CSV headers to canonical fields using alias table."""
    normalized = {_normalize_header(h): h for h in fieldnames}
    mapping: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[canonical] = normalized[alias]
                break
    return mapping


def parse_csv_text(
    text: str,
    column_map: Optional[dict[str, str]] = None,
) -> ImportPreview:
    """
    Parse CSV content into ImportRow objects.

    If column_map is None, headers are auto-mapped via COLUMN_ALIASES.
    column_map keys are canonical fields; values are exact CSV header names.
    """
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        return ImportPreview(rows=[], skipped=0, column_map={})

    auto_map = _map_headers(reader.fieldnames)
    effective_map = column_map or auto_map

    ip_col = effective_map.get("management_ip")
    name_col = effective_map.get("name")
    if not ip_col or not name_col:
        raise ValueError(
            "CSV must include management IP and device name columns. "
            f"Detected headers: {reader.fieldnames}"
        )

    rows: list[ImportRow] = []
    skipped = 0
    for line in reader:
        ip = (line.get(ip_col) or "").strip()
        name = (line.get(name_col) or "").strip()
        if not ip or not name:
            skipped += 1
            continue
        vendor_col = effective_map.get("vendor")
        location_col = effective_map.get("location")
        region_col = effective_map.get("region")
        vendor = (line.get(vendor_col) or "Fortinet").strip() if vendor_col else "Fortinet"
        if vendor.lower() in ("fortigate", "fortinet"):
            vendor = "Fortinet"
        rows.append(
            ImportRow(
                name=name,
                management_ip=ip,
                vendor=vendor,
                location=(line.get(location_col) or "").strip() if location_col else "",
                region=(line.get(region_col) or "").strip() if region_col else "",
            )
        )

    return ImportPreview(rows=rows, skipped=skipped, column_map=effective_map)


def parse_csv_file(path: Path, column_map: Optional[dict[str, str]] = None) -> ImportPreview:
    text = path.read_text(encoding="utf-8-sig")
    return parse_csv_text(text, column_map=column_map)
