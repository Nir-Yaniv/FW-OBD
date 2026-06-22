"""Abstract base class for all vendor parsers."""

from __future__ import annotations
from abc import ABC, abstractmethod
from fw_obd.models.udm import Device


class BaseParser(ABC):
    """Every vendor parser must implement parse()."""

    @abstractmethod
    def parse(self, raw_outputs: dict[str, str]) -> Device:
        """Convert raw CLI outputs into a Device UDM object."""
        ...
