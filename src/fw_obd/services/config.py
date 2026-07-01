"""Application configuration — persisted settings + keyring-backed API key.

Non-secret settings live in ~/.fw_obd/settings.json. The Anthropic API key is
stored in the OS keyring (Windows Credential Manager / Keychain / Secret Service),
never on disk, consistent with fw_obd.security.crypto.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".fw_obd" / "settings.json"
DEFAULT_BACKUP_DIR = Path.home() / ".fw_obd" / "backups"

KEYRING_SERVICE = "fw_obd"
KEYRING_API_USER = "anthropic-api-key"


@dataclass
class AppConfig:
    backup_dir: str = str(DEFAULT_BACKUP_DIR)
    retention_days: int = 14
    poll_interval_secs: int = 5
    ai_model: str = "claude-sonnet-4-6"

    @classmethod
    def load(cls) -> "AppConfig":
        cfg = cls()
        try:
            if CONFIG_PATH.exists():
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                for f in cls().__dict__:
                    if f in data:
                        setattr(cfg, f, data[f])
        except (OSError, ValueError) as exc:
            logger.warning("Could not read settings (%s); using defaults", exc)
        return cfg

    def save(self) -> None:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


# ---------------------------------------------------------------- API key (keyring)
def get_api_key() -> Optional[str]:
    """Return the Anthropic API key from the keyring, falling back to the env var."""
    try:
        import keyring

        key = keyring.get_password(KEYRING_SERVICE, KEYRING_API_USER)
        if key:
            return key
    except Exception as exc:  # keyring unavailable
        logger.debug("keyring unavailable for API key (%s)", exc)
    return os.environ.get("ANTHROPIC_API_KEY")


def set_api_key(key: str) -> bool:
    """Store the Anthropic API key in the OS keyring. Returns True on success."""
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, KEYRING_API_USER, key)
        return True
    except Exception as exc:  # keyring unavailable
        logger.warning("Could not store API key in keyring (%s)", exc)
        return False


def api_key_is_set() -> bool:
    return bool(get_api_key())
