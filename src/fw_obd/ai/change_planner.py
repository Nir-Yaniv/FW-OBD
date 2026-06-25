"""Change Planner — turns a natural-language change request into a structured,
reviewable plan of FortiGate CLI commands.

v1 is **plan-and-preview only**: it produces the plan and the exact commands so
the UI can show an approval dialog, but it NEVER pushes anything to a device.
Real SSH execution is a deliberate follow-up once the plan format is proven.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import anthropic

from fw_obd.models.udm import Device

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class ChangeCommand:
    cli: str
    description: str


@dataclass
class ChangePlan:
    """A reviewable, structured plan — never auto-executed in v1."""
    intent: str
    rationale: str
    commands: list[ChangeCommand] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    backup_needed: bool = True
    warnings: list[str] = field(default_factory=list)


_SYSTEM_PROMPT = """You are the Firewall OBD change-planning engine for Fortinet FortiGate firewalls.

Given the current device state and a plain-language change request, produce a precise,
minimal plan of exact FortiGate CLI commands that accomplishes the request.

Rules:
- Output EXACT FortiGate CLI syntax (config/edit/set/next/end blocks).
- Each command entry pairs the raw CLI with a one-line plain-language description.
- Order commands the way they must run (config mode entry, edits, then end).
- Assess risk honestly: HIGH if it touches management access, routing, or VPN that
  could drop connectivity; MEDIUM for policy/logging changes; LOW for read-only or
  cosmetic changes.
- backup_needed must be true for any change that alters running config.
- Add warnings for anything that could interrupt connectivity or lock out management.
- If device context is missing, still produce a template plan but warn that it is
  unverified against the real device.

You only PLAN. You never execute. Always assume a human reviews before anything runs."""


_PLAN_TOOL = {
    "name": "propose_change_plan",
    "description": "Return a structured, reviewable FortiGate change plan.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {
                "type": "string",
                "description": "One-sentence restatement of what the change accomplishes.",
            },
            "rationale": {
                "type": "string",
                "description": "Why this is the right approach, in plain language.",
            },
            "commands": {
                "type": "array",
                "description": "Ordered list of FortiGate CLI commands to run.",
                "items": {
                    "type": "object",
                    "properties": {
                        "cli": {"type": "string", "description": "Exact FortiGate CLI command/line."},
                        "description": {"type": "string", "description": "Plain-language description."},
                    },
                    "required": ["cli", "description"],
                },
            },
            "risk_level": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Connectivity/security risk of applying this plan.",
            },
            "backup_needed": {
                "type": "boolean",
                "description": "Whether a config backup should be taken before applying.",
            },
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Anything that could interrupt connectivity or lock out management.",
            },
        },
        "required": ["intent", "rationale", "commands", "risk_level", "backup_needed"],
    },
}


class ChangePlanner:
    """Generates a structured ChangePlan via Claude tool-use. Plan-only — no SSH."""

    MODEL = "claude-sonnet-4-6"
    MAX_TOKENS = 2048

    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file or set the environment variable."
            )
        self._client = anthropic.Anthropic(api_key=key)

    def plan(self, device: Optional[Device], request: str) -> ChangePlan:
        """Produce a structured plan for `request` against the given device."""
        context_block = self._device_context(device)
        user_content = f"{context_block}\n\nCHANGE REQUEST:\n{request}" if context_block else request

        response = self._client.messages.create(
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            tools=[_PLAN_TOOL],
            tool_choice={"type": "tool", "name": "propose_change_plan"},
            messages=[{"role": "user", "content": user_content}],
        )

        tool_input = self._extract_tool_input(response)
        return self._to_plan(tool_input, device)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _device_context(device: Optional[Device]) -> str:
        if not device:
            return ""
        lines = [
            "[DEVICE CONTEXT]",
            f"Vendor: {device.vendor.value} | Model: {device.model} | Hostname: {device.hostname}",
            f"Management IP: {device.management_ip} | FortiOS: {device.software_version}",
            f"Interfaces: {len(device.interfaces)} | Policies: {len(device.policies)} | "
            f"VPN Tunnels: {len(device.vpn_tunnels)}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _extract_tool_input(response: anthropic.types.Message) -> dict:
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == "propose_change_plan":
                return dict(block.input)  # type: ignore[arg-type]
        raise RuntimeError("Change planner did not return a structured plan.")

    @staticmethod
    def _to_plan(data: dict, device: Optional[Device]) -> ChangePlan:
        commands = [
            ChangeCommand(cli=c.get("cli", ""), description=c.get("description", ""))
            for c in data.get("commands", [])
        ]
        try:
            risk = RiskLevel(data.get("risk_level", "medium"))
        except ValueError:
            risk = RiskLevel.MEDIUM

        warnings = list(data.get("warnings", []))
        if device is None:
            warnings.insert(0, "No device context — commands are templates; verify against the real device.")

        return ChangePlan(
            intent=data.get("intent", ""),
            rationale=data.get("rationale", ""),
            commands=commands,
            risk_level=risk,
            backup_needed=bool(data.get("backup_needed", True)),
            warnings=warnings,
        )
