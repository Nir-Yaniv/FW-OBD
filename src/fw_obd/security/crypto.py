"""Central encryption-key management backed by the OS keystore.

The app uses a single Fernet key for all data at rest (config backups on disk and
sensitive columns such as ``scan_results.raw_config``). The key lives in the OS
keystore — Windows Credential Manager, macOS Keychain, or Secret Service on Linux —
via the ``keyring`` library, so it is never co-located with the ciphertext it
protects.

A one-time migration imports any legacy on-disk ``.key`` into the keystore and
removes the file. If no keystore backend is usable (e.g. a headless CI box), the
code falls back to a file-based key with a loud warning so the app still runs.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

KEYRING_SERVICE = "fw_obd"
KEYRING_USERNAME = "config-encryption-key"

# Legacy location used before keystore migration (BackupManager's old .key file).
DEFAULT_LEGACY_KEY_FILE = Path.home() / ".fw_obd" / "backups" / ".key"


def load_or_create_key(legacy_key_file: Optional[Path] = None) -> bytes:
    """Return the app Fernet key, preferring the OS keystore.

    Resolution order:
      1. Existing key in the OS keystore.
      2. Legacy on-disk key — imported into the keystore, then the file is deleted.
      3. A freshly generated key, stored in the keystore.
    If the keystore is unavailable, fall back to a file-based key.
    """
    legacy = legacy_key_file or DEFAULT_LEGACY_KEY_FILE
    try:
        import keyring

        existing = keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
        if existing:
            return existing.encode("utf-8")

        if legacy.exists():
            key = legacy.read_bytes()
            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, key.decode("utf-8"))
            try:
                legacy.unlink()
            except OSError:
                logger.warning("Migrated key to keystore but could not delete %s", legacy)
            logger.info("Migrated encryption key into the OS keystore")
            return key

        key = Fernet.generate_key()
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, key.decode("utf-8"))
        logger.info("Generated new encryption key in the OS keystore")
        return key
    except Exception as exc:  # keyring import failure or no usable backend
        logger.warning(
            "OS keystore unavailable (%s); falling back to file-based key at %s",
            exc,
            legacy,
        )
        return _load_or_create_file_key(legacy)


def _load_or_create_file_key(key_path: Path) -> bytes:
    """Fallback: read or generate a key on disk (best-effort owner-only perms)."""
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        return key_path.read_bytes()
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    try:
        os.chmod(str(key_path), stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return key


class Cipher:
    """Fernet wrapper bound to the app encryption key (AES-128-CBC + HMAC-SHA256)."""

    def __init__(self, key: Optional[bytes] = None) -> None:
        self._fernet = Fernet(key or load_or_create_key())

    def encrypt(self, data: bytes) -> bytes:
        return self._fernet.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        return self._fernet.decrypt(data)

    def encrypt_str(self, plaintext: str) -> str:
        """Encrypt a string, returning a UTF-8-safe token string for storage."""
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt_str(self, token: str) -> str:
        """Decrypt a token produced by :meth:`encrypt_str`."""
        return self._fernet.decrypt(token.encode("utf-8")).decode("utf-8")
