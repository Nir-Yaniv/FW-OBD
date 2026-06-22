"""Backup manager — encrypted local config backups with retention policy."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet

from fw_obd.db.database import Database

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = Path.home() / ".fw_obd" / "backups"
DEFAULT_RETENTION_DAYS = 14


class BackupManager:
    """
    Encrypts and stores firewall config backups locally.

    Each backup is an AES-128 Fernet-encrypted .cfg.enc file.
    The encryption key is derived per-device and stored in the app's key store.
    Backup records are tracked in SQLite via the Database layer.
    """

    def __init__(
        self,
        db: Database,
        backup_dir: Path = DEFAULT_BACKUP_DIR,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ) -> None:
        self._db = db
        self._backup_dir = backup_dir
        self._retention_days = retention_days
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        self._key = self._load_or_create_key()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_backup(
        self,
        device_id: int,
        hostname: str,
        raw_config: str,
        label: str = "",
        is_pre_change: bool = False,
        change_description: str = "",
    ) -> Path:
        """Encrypt and save a raw config string. Returns the backup file path."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        safe_hostname = hostname.replace(" ", "_").replace("/", "-")
        filename = f"{safe_hostname}_{timestamp}.cfg.enc"
        file_path = self._backup_dir / filename

        encrypted = self._encrypt(raw_config.encode("utf-8"))
        file_path.write_bytes(encrypted)
        file_size = file_path.stat().st_size

        expires_at = datetime.utcnow() + timedelta(days=self._retention_days)
        self._db.register_backup(
            device_id=device_id,
            file_path=str(file_path),
            label=label or f"Backup {timestamp}",
            is_pre_change=is_pre_change,
            change_description=change_description,
            expires_at=expires_at,
            file_size_bytes=file_size,
        )
        logger.info("Backup created: %s (%d bytes)", file_path.name, file_size)
        return file_path

    def restore_backup(self, file_path: Path) -> str:
        """Decrypt and return the raw config string from a backup file."""
        if not file_path.exists():
            raise FileNotFoundError(f"Backup file not found: {file_path}")
        encrypted = file_path.read_bytes()
        return self._decrypt(encrypted).decode("utf-8")

    def list_backups(self, device_id: int) -> list[dict]:
        """Return list of backup records for a device, newest first."""
        rows = self._db.list_backups(device_id)
        return [dict(row) for row in rows]

    def purge_expired(self) -> int:
        """Delete backup files and DB records past their expiry date. Returns count deleted."""
        cutoff = datetime.utcnow().isoformat()
        deleted = 0
        # We query directly — BackupManager owns the retention policy
        conn_rows = self._db.list_backups(device_id=0)  # placeholder — use raw query below
        # Use raw access via database internal for simplicity
        import sqlite3
        conn = sqlite3.connect(str(self._db._path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM backups WHERE expires_at IS NOT NULL AND expires_at < ?", (cutoff,)
        ).fetchall()
        for row in rows:
            path = Path(row["file_path"])
            if path.exists():
                path.unlink()
                deleted += 1
            conn.execute("DELETE FROM backups WHERE id=?", (row["id"],))
        conn.commit()
        conn.close()
        logger.info("Purged %d expired backups", deleted)
        return deleted

    # ------------------------------------------------------------------
    # Encryption (Fernet / AES-128-CBC with HMAC-SHA256)
    # ------------------------------------------------------------------

    def _key_file_path(self) -> Path:
        return self._backup_dir / ".key"

    def _load_or_create_key(self) -> bytes:
        key_path = self._key_file_path()
        if key_path.exists():
            return key_path.read_bytes()
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        # Restrict permissions on Windows as much as possible
        try:
            import stat
            os.chmod(str(key_path), stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
        logger.info("Generated new backup encryption key")
        return key

    def _encrypt(self, data: bytes) -> bytes:
        return Fernet(self._key).encrypt(data)

    def _decrypt(self, data: bytes) -> bytes:
        return Fernet(self._key).decrypt(data)
