"""Smart Terminal — conversational AI interface backed by Anthropic Claude.

Privacy note: device context (IPs, hostnames, config excerpts) is sent to
the Anthropic API. Users must be informed of this. A local-LLM path
(Ollama) should be added in a future phase for air-gapped environments.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Iterator, Optional

import anthropic

from fw_obd.models.udm import Device

logger = logging.getLogger(__name__)

# System prompt that defines the assistant's role and behavior
_SYSTEM_PROMPT = """You are the Firewall OBD assistant — an expert network security engineer \
with deep knowledge of Fortinet FortiGate (and future: Palo Alto, Cisco, Check Point) firewalls.

Your role:
- Help IT administrators configure, troubleshoot, and optimize firewalls using plain language
- Translate technical firewall operations into clear, step-by-step guidance
- Always explain the WHY behind each recommendation, not just the WHAT
- Cite official vendor documentation when making recommendations
- Ask clarifying questions before proposing changes that could affect connectivity
- NEVER execute changes without explicit user confirmation
- Flag compliance implications (HIPAA, PCI-DSS) when relevant
- When describing CLI commands, show exact FortiGate syntax

Current device context will be provided in the user messages.
Always reason about the specific device state before making recommendations.
"""


@dataclass
class Message:
    role: str   # "user" or "assistant"
    content: str


@dataclass
class ConversationContext:
    """Holds the conversation history and device state for one Smart Terminal session."""
    device: Optional[Device] = None
    messages: list[Message] = field(default_factory=list)

    def add_user(self, text: str) -> None:
        self.messages.append(Message(role="user", content=text))

    def add_assistant(self, text: str) -> None:
        self.messages.append(Message(role="assistant", content=text))

    def to_api_messages(self) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in self.messages]

    def device_summary(self) -> str:
        """Build a compact device-state block to inject into user messages."""
        if not self.device:
            return ""
        d = self.device
        lines = [
            f"[DEVICE CONTEXT]",
            f"Vendor: {d.vendor.value} | Model: {d.model} | Hostname: {d.hostname}",
            f"Management IP: {d.management_ip} | FortiOS: {d.software_version}",
            f"Interfaces: {len(d.interfaces)} | Policies: {len(d.policies)} | VPN Tunnels: {len(d.vpn_tunnels)}",
            f"VDOMs: {[v.name for v in d.virtual_domains] or ['root']}",
        ]
        if d.expiring_licenses:
            lines.append(f"License alerts: {[l.feature + ' (' + str(l.days_remaining) + 'd)' for l in d.expiring_licenses]}")
        if d.health.cpu_usage_pct:
            lines.append(f"Health: CPU {d.health.cpu_usage_pct:.0f}% | Mem {d.health.memory_usage_pct:.0f}%")
        return "\n".join(lines)


class SmartTerminal:
    """
    Manages a multi-turn conversation with Claude for firewall assistance.

    Usage:
        terminal = SmartTerminal()
        context = ConversationContext(device=parsed_device)
        for chunk in terminal.chat_stream(context, "I need to set up a VPN to Tel Aviv"):
            print(chunk, end="", flush=True)
    """

    MODEL = "claude-sonnet-4-6"
    MAX_TOKENS = 2048

    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY not set. Add it to your .env file or set the environment variable."
            )
        self._client = anthropic.Anthropic(api_key=key)

    def chat_stream(self, context: ConversationContext, user_message: str) -> Iterator[str]:
        """
        Send a user message and stream the assistant response as text chunks.
        Updates context.messages in-place when the full response is received.
        """
        # Prepend device context to first message or if context is mentioned
        full_message = user_message
        if context.device and not context.messages:
            full_message = f"{context.device_summary()}\n\n{user_message}"

        context.add_user(full_message)

        full_response = ""
        with self._client.messages.stream(
            model=self.MODEL,
            max_tokens=self.MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=context.to_api_messages(),
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                yield text

        context.add_assistant(full_response)
        logger.debug("Smart Terminal response: %d chars", len(full_response))

    def chat_once(self, context: ConversationContext, user_message: str) -> str:
        """Non-streaming version — returns complete response string."""
        return "".join(self.chat_stream(context, user_message))

    def reset(self, context: ConversationContext) -> None:
        """Clear conversation history while keeping device context."""
        context.messages.clear()
