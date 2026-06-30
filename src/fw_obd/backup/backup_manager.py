"""Backup manager — encrypted local config backups with retention policy."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fw_obd.db.database import Database
from fw_obd.security.crypto import Cipher

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = Path.home() / ".fw_obd" / "backups"
DEFAULT_RETENTION_DAYS = 14


class BackupManager:
    """
    Encrypts and stores firewall config backups locally.

    Each backup is an AES-128 Fernet-encrypted .cfg.enc file.
    The encryption key is held in the OS keystore (see fw_obd.security.crypto),
    never co-located with the ciphertext. Backup records are tracked in SQLite
    via the Database layer.
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
        self._cipher = Cipher()

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
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
        safe_hostname = hostname.replace(" ", "_").replace("/", "-")
        filename = f"{safe_hostname}_{timestamp}.cfg.enc"
        file_path = self._backup_dir / filename

        encrypted = self._cipher.encrypt(raw_config.encode("utf-8"))
        file_path.write_bytes(encrypted)
        file_size = file_path.stat().st_size

        expires_at = now + timedelta(days=self._retention_days)
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
        return self._cipher.decrypt(encrypted).decode("utf-8")

    def list_backups(self, device_id: int) -> list[dict]:
        """Return list of backup records for a device, newest first."""
        rows = self._db.list_backups(device_id)
        return [dict(row) for row in rows]

    def purge_expired(self) -> int:
        """Delete backup files and DB records past their expiry date. Returns count deleted."""
        cutoff = datetime.now(timezone.utc).isoformat()
        # Database layer owns the SQL/transaction; it returns the file paths to remove.
        file_paths = self._db.purge_expired_backups(cutoff)
        deleted = 0
        for fp in file_paths:
            path = Path(fp)
            if path.exists():
                try:
                    path.unlink()
                    deleted += 1
                except OSError:
                    logger.warning("Could not delete expired backup file %s", path)
        logger.info("Purged %d expired backups (%d records)", deleted, len(file_paths))
        return deleted
