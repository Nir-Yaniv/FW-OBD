"""SQLite database layer — device inventory, audit log, scan history."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path.home() / ".fw_obd" / "fw_obd.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS devices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    management_ip   TEXT NOT NULL UNIQUE,
    vendor          TEXT NOT NULL DEFAULT 'Fortinet',
    model           TEXT,
    hostname        TEXT,
    location        TEXT,
    region          TEXT,
    serial_number   TEXT,
    software_version TEXT,
    last_seen       TEXT,
    status          TEXT NOT NULL DEFAULT 'unknown',  -- online/offline/warning/critical
    onsite_contact  TEXT,                             -- main on-site contact person
    notes           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scan_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       INTEGER NOT NULL REFERENCES devices(id),
    scanned_at      TEXT NOT NULL DEFAULT (datetime('now')),
    scan_type       TEXT NOT NULL DEFAULT 'full',     -- full/audit
    udm_json        TEXT,                              -- serialized Device UDM
    raw_config      TEXT,
    findings_json   TEXT                               -- serialized audit findings
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    user_email      TEXT,
    device_id       INTEGER REFERENCES devices(id),
    action          TEXT NOT NULL,                     -- connect/scan/change/backup/rollback
    description     TEXT,
    success         INTEGER NOT NULL DEFAULT 1,
    error_detail    TEXT
);

CREATE TABLE IF NOT EXISTS backups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       INTEGER NOT NULL REFERENCES devices(id),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    label           TEXT,
    file_path       TEXT NOT NULL,
    file_size_bytes INTEGER,
    is_pre_change   INTEGER NOT NULL DEFAULT 0,
    change_description TEXT,
    expires_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_scan_device ON scan_results(device_id);
CREATE INDEX IF NOT EXISTS idx_audit_device ON audit_log(device_id);
CREATE INDEX IF NOT EXISTS idx_backups_device ON backups(device_id);
"""


class Database:
    """Thin wrapper around SQLite for fw_obd persistent storage."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH) -> None:
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    @contextmanager
    def _tx(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def _read(self) -> Generator[sqlite3.Connection, None, None]:
        """Read-only connection that is always closed.

        Note: a sqlite3 connection's own ``with`` block commits/rolls back but does
        NOT close the connection, so reads must go through this helper to avoid
        leaking connections.
        """
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._tx() as conn:
            conn.executescript(SCHEMA_SQL)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        """Add columns introduced after the initial schema to existing databases."""
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(devices)")}
        if "onsite_contact" not in cols:
            conn.execute("ALTER TABLE devices ADD COLUMN onsite_contact TEXT")

    # ------------------------------------------------------------------
    # Device CRUD
    # ------------------------------------------------------------------

    def upsert_device(
        self,
        name: str,
        management_ip: str,
        vendor: str = "Fortinet",
        model: str = "",
        hostname: str = "",
        location: str = "",
        region: str = "",
        serial_number: str = "",
        software_version: str = "",
        onsite_contact: str = "",
    ) -> int:
        """Insert or update a device record. Returns the device id."""
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO devices (name, management_ip, vendor, model, hostname,
                                     location, region, serial_number, software_version,
                                     onsite_contact)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(management_ip) DO UPDATE SET
                    name=excluded.name, vendor=excluded.vendor, model=excluded.model,
                    hostname=excluded.hostname, location=excluded.location,
                    region=excluded.region, serial_number=excluded.serial_number,
                    software_version=excluded.software_version,
                    onsite_contact=COALESCE(NULLIF(excluded.onsite_contact, ''), devices.onsite_contact)
                """,
                (name, management_ip, vendor, model, hostname, location, region,
                 serial_number, software_version, onsite_contact),
            )
            row = conn.execute("SELECT id FROM devices WHERE management_ip=?", (management_ip,)).fetchone()
            return int(row["id"])

    def get_device(self, device_id: int) -> Optional[sqlite3.Row]:
        with self._read() as conn:
            return conn.execute("SELECT * FROM devices WHERE id=?", (device_id,)).fetchone()

    def get_device_by_ip(self, ip: str) -> Optional[sqlite3.Row]:
        with self._read() as conn:
            return conn.execute("SELECT * FROM devices WHERE management_ip=?", (ip,)).fetchone()

    def list_devices(self) -> list[sqlite3.Row]:
        with self._read() as conn:
            return conn.execute("SELECT * FROM devices ORDER BY region, location, name").fetchall()

    def update_device_status(
        self,
        device_id: int,
        status: str,
        last_seen: Optional[datetime] = None,
        *,
        touch_last_seen: bool = True,
    ) -> None:
        """Update device status. last_seen means "last successful contact":
        failure paths (connect failed, poller lost the device) pass
        touch_last_seen=False so a failed attempt is never stamped."""
        with self._tx() as conn:
            if touch_last_seen:
                ts = (last_seen or datetime.now(timezone.utc)).isoformat()
                conn.execute(
                    "UPDATE devices SET status=?, last_seen=? WHERE id=?",
                    (status, ts, device_id),
                )
            else:
                conn.execute("UPDATE devices SET status=? WHERE id=?", (status, device_id))

    def update_device(
        self,
        device_id: int,
        name: str,
        management_ip: str,
        vendor: str = "Fortinet",
        model: str = "",
        location: str = "",
        region: str = "",
        onsite_contact: str = "",
    ) -> None:
        """Update editable inventory fields of a device by id.

        Unlike upsert_device (keyed on management_ip), this updates by primary key,
        so the management IP itself can be edited.
        """
        with self._tx() as conn:
            conn.execute(
                """
                UPDATE devices
                SET name=?, management_ip=?, vendor=?, model=?, location=?, region=?,
                    onsite_contact=?
                WHERE id=?
                """,
                (name, management_ip, vendor, model, location, region, onsite_contact, device_id),
            )

    def delete_device(self, device_id: int) -> None:
        with self._tx() as conn:
            conn.execute("DELETE FROM devices WHERE id=?", (device_id,))

    # ------------------------------------------------------------------
    # Scan results
    # ------------------------------------------------------------------

    def save_scan(
        self,
        device_id: int,
        scan_type: str,
        udm_json: str = "",
        raw_config: str = "",
        findings_json: str = "",
    ) -> int:
        with self._tx() as conn:
            cursor = conn.execute(
                """
                INSERT INTO scan_results (device_id, scan_type, udm_json, raw_config, findings_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (device_id, scan_type, udm_json, raw_config, findings_json),
            )
            return int(cursor.lastrowid)  # type: ignore[arg-type]

    def get_latest_scan(self, device_id: int) -> Optional[sqlite3.Row]:
        with self._read() as conn:
            return conn.execute(
                "SELECT * FROM scan_results WHERE device_id=? ORDER BY scanned_at DESC LIMIT 1",
                (device_id,),
            ).fetchone()

    def get_scan(self, scan_id: int) -> Optional[sqlite3.Row]:
        with self._read() as conn:
            return conn.execute("SELECT * FROM scan_results WHERE id=?", (scan_id,)).fetchone()

    def list_scans(self, limit: int = 200) -> list[sqlite3.Row]:
        """Scan history across all devices, newest first, joined with device info."""
        with self._read() as conn:
            return conn.execute(
                """
                SELECT s.id, s.scanned_at, s.scan_type, s.findings_json,
                       d.id AS device_id, d.name, d.management_ip, d.region, d.location
                FROM scan_results s
                JOIN devices d ON d.id = s.device_id
                ORDER BY s.scanned_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def log_action(
        self,
        action: str,
        description: str = "",
        device_id: Optional[int] = None,
        user_email: Optional[str] = None,
        success: bool = True,
        error_detail: str = "",
    ) -> None:
        with self._tx() as conn:
            conn.execute(
                """
                INSERT INTO audit_log (user_email, device_id, action, description, success, error_detail)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_email, device_id, action, description, 1 if success else 0, error_detail),
            )

    def get_audit_log(self, device_id: Optional[int] = None, limit: int = 100) -> list[sqlite3.Row]:
        with self._read() as conn:
            if device_id:
                return conn.execute(
                    "SELECT * FROM audit_log WHERE device_id=? ORDER BY timestamp DESC LIMIT ?",
                    (device_id, limit),
                ).fetchall()
            return conn.execute(
                "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,)
            ).fetchall()

    # ------------------------------------------------------------------
    # Backups
    # ------------------------------------------------------------------

    def register_backup(
        self,
        device_id: int,
        file_path: str,
        label: str = "",
        is_pre_change: bool = False,
        change_description: str = "",
        expires_at: Optional[datetime] = None,
        file_size_bytes: int = 0,
    ) -> int:
        exp = expires_at.isoformat() if expires_at else None
        with self._tx() as conn:
            cursor = conn.execute(
                """
                INSERT INTO backups (device_id, label, file_path, file_size_bytes,
                                     is_pre_change, change_description, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (device_id, label, file_path, file_size_bytes, 1 if is_pre_change else 0, change_description, exp),
            )
            return int(cursor.lastrowid)  # type: ignore[arg-type]

    def list_backups(self, device_id: int) -> list[sqlite3.Row]:
        with self._read() as conn:
            return conn.execute(
                "SELECT * FROM backups WHERE device_id=? ORDER BY created_at DESC",
                (device_id,),
            ).fetchall()

    def purge_expired_backups(self, cutoff_iso: str) -> list[str]:
        """Delete backup records whose expiry is before ``cutoff_iso``.

        Returns the file paths of the deleted records so the caller can remove the
        corresponding files. The select and delete run in a single transaction.
        """
        with self._tx() as conn:
            rows = conn.execute(
                "SELECT file_path FROM backups WHERE expires_at IS NOT NULL AND expires_at < ?",
                (cutoff_iso,),
            ).fetchall()
            file_paths = [row["file_path"] for row in rows]
            conn.execute(
                "DELETE FROM backups WHERE expires_at IS NOT NULL AND expires_at < ?",
                (cutoff_iso,),
            )
        return file_paths
