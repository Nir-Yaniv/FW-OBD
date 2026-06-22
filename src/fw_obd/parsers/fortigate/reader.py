"""FortiGate config reader — executes CLI commands and returns raw outputs."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from fw_obd.connection.ssh_handler import SSHHandler
from fw_obd.models.udm import Device
from fw_obd.parsers.fortigate import commands as cmds
from fw_obd.parsers.fortigate.parser import FortiGateParser

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int], None]


class FortiGateReader:
    """
    Orchestrates SSH command execution and parsing for a FortiGate device.

    Usage:
        reader = FortiGateReader(ssh_handler)
        device = reader.read_full_config(progress_cb=my_callback)
    """

    def __init__(self, ssh: SSHHandler) -> None:
        self._ssh = ssh
        self._parser = FortiGateParser(management_ip=ssh._creds.host)

    def read_full_config(self, progress_cb: Optional[ProgressCallback] = None) -> Device:
        """Run the full command sequence and return a parsed Device."""
        return self._run_sequence(cmds.READ_SEQUENCE, progress_cb)

    def read_audit_config(self, progress_cb: Optional[ProgressCallback] = None) -> Device:
        """Run the minimal audit command sequence (faster, used on first connect)."""
        return self._run_sequence(cmds.AUDIT_SEQUENCE, progress_cb)

    def read_raw_backup(self) -> str:
        """Retrieve the full running configuration as a raw string for backup."""
        logger.info("Reading full configuration for backup")
        return self._ssh.send_command(cmds.SHOW_FULL_CONFIG, delay_factor=4.0)

    # ------------------------------------------------------------------

    def _run_sequence(self, sequence: list[str], progress_cb: Optional[ProgressCallback]) -> Device:
        raw_outputs: dict[str, str] = {}
        total = len(sequence)

        for idx, command in enumerate(sequence, start=1):
            if progress_cb:
                progress_cb(command, idx, total)
            logger.debug("Running [%d/%d]: %s", idx, total, command)
            try:
                output = self._ssh.send_command(command, delay_factor=2.0)
                raw_outputs[command] = output
            except Exception as exc:
                logger.warning("Command failed '%s': %s", command, exc)
                raw_outputs[command] = ""

        return self._parser.parse(raw_outputs)
