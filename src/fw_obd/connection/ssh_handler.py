"""SSH connection handler using Netmiko for firewall communication."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator, Optional

from netmiko import ConnectHandler, NetmikoAuthenticationException, NetmikoTimeoutException
from netmiko.exceptions import NetmikoBaseException

logger = logging.getLogger(__name__)

# Netmiko device_type mappings per vendor
VENDOR_DEVICE_TYPES = {
    "Fortinet": "fortinet",
    "Palo Alto": "paloalto_panos",
    "Cisco": "cisco_asa",
    "Check Point": "checkpoint_gaia",
}


@dataclass
class SSHCredentials:
    host: str
    username: str
    password: str
    port: int = 22
    device_type: str = "fortinet"
    use_keys: bool = False
    key_file: Optional[str] = None
    passphrase: Optional[str] = None


class SSHConnectionError(Exception):
    pass


class SSHAuthenticationError(SSHConnectionError):
    pass


class SSHTimeoutError(SSHConnectionError):
    pass


class SSHHandler:
    """Manages a single SSH session to a firewall device."""

    # FortiGate pager must be disabled before running show commands
    _FORTIGATE_PAGER_OFF = "config system console\n set output standard\n end"

    def __init__(self, credentials: SSHCredentials, timeout: int = 30) -> None:
        self._creds = credentials
        self._timeout = timeout
        self._connection: Optional[ConnectHandler] = None

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the SSH connection. Raises SSHConnectionError variants on failure."""
        params: dict = {
            "device_type": self._creds.device_type,
            "host": self._creds.host,
            "username": self._creds.username,
            "port": self._creds.port,
            "timeout": self._timeout,
            "session_timeout": self._timeout * 2,
            "blocking_timeout": self._timeout,
            "fast_cli": False,
        }
        if self._creds.use_keys and self._creds.key_file:
            params["use_keys"] = True
            params["key_file"] = self._creds.key_file
            if self._creds.passphrase:
                params["passphrase"] = self._creds.passphrase
        else:
            params["password"] = self._creds.password

        logger.info("Connecting to %s:%s as %s", self._creds.host, self._creds.port, self._creds.username)
        try:
            self._connection = ConnectHandler(**params)
            self._disable_pager()
            logger.info("Connected to %s", self._creds.host)
        except NetmikoAuthenticationException as exc:
            raise SSHAuthenticationError(f"Authentication failed for {self._creds.host}: {exc}") from exc
        except NetmikoTimeoutException as exc:
            raise SSHTimeoutError(f"Connection timed out to {self._creds.host}: {exc}") from exc
        except NetmikoBaseException as exc:
            raise SSHConnectionError(f"SSH error connecting to {self._creds.host}: {exc}") from exc

    def disconnect(self) -> None:
        if self._connection:
            try:
                self._connection.disconnect()
            except Exception:
                pass
            finally:
                self._connection = None
            logger.info("Disconnected from %s", self._creds.host)

    @property
    def is_connected(self) -> bool:
        if not self._connection:
            return False
        try:
            return self._connection.is_alive()
        except Exception:
            return False

    def ensure_connected(self) -> None:
        if not self.is_connected:
            logger.info("Connection lost, reconnecting to %s", self._creds.host)
            self.connect()

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    def send_command(self, command: str, expect_string: Optional[str] = None, delay_factor: float = 1.0) -> str:
        """Execute a command and return the output as a string."""
        self.ensure_connected()
        assert self._connection is not None
        try:
            kwargs: dict = {"command_string": command, "delay_factor": delay_factor}
            if expect_string:
                kwargs["expect_string"] = expect_string
            output: str = self._connection.send_command(**kwargs)
            logger.debug("CMD [%s] -> %d chars", command, len(output))
            return output
        except NetmikoBaseException as exc:
            raise SSHConnectionError(f"Command failed '{command}': {exc}") from exc

    def send_command_timing(self, command: str, delay: float = 1.0) -> str:
        """Use timing-based (non-prompt-wait) command for config mode sequences."""
        self.ensure_connected()
        assert self._connection is not None
        output: str = self._connection.send_command_timing(command_string=command, delay_factor=delay)
        return output

    def send_config_commands(self, commands: list[str]) -> str:
        """Send a block of config-mode commands sequentially and return all output."""
        results = []
        for cmd in commands:
            out = self.send_command_timing(cmd)
            results.append(f"# {cmd}\n{out}")
            time.sleep(0.2)
        return "\n".join(results)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _disable_pager(self) -> None:
        """Disable FortiGate's --More-- pager so full output is returned."""
        if self._creds.device_type == "fortinet":
            try:
                self.send_command_timing(self._FORTIGATE_PAGER_OFF)
            except Exception:
                logger.warning("Could not disable FortiGate pager on %s", self._creds.host)


@contextmanager
def ssh_session(credentials: SSHCredentials, timeout: int = 30) -> Generator[SSHHandler, None, None]:
    """Context manager that opens and auto-closes an SSH session."""
    handler = SSHHandler(credentials, timeout=timeout)
    handler.connect()
    try:
        yield handler
    finally:
        handler.disconnect()
