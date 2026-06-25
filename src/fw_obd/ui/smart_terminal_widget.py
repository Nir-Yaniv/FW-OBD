"""Smart Terminal chat panel — conversational AI firewall assistant (PyQt6).

Wires the SmartTerminal engine (Anthropic Claude) into a streaming chat UI.
The actual API streaming runs on a background QThread so the GUI never blocks.
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from fw_obd.ai.smart_terminal import ConversationContext, SmartTerminal
from fw_obd.models.udm import Device

logger = logging.getLogger(__name__)


class ChatStreamWorker(QThread):
    """Runs SmartTerminal.chat_stream off the UI thread, emitting tokens."""

    chunk = pyqtSignal(str)
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        terminal: SmartTerminal,
        context: ConversationContext,
        message: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._terminal = terminal
        self._context = context
        self._message = message

    def run(self) -> None:
        try:
            for text in self._terminal.chat_stream(self._context, self._message):
                self.chunk.emit(text)
            self.finished_ok.emit()
        except Exception as exc:  # noqa: BLE001 — surface any API/network error to UI
            logger.exception("Smart Terminal stream failed")
            self.failed.emit(str(exc))


class SmartTerminalWidget(QWidget):
    """
    Conversational chat panel backed by Claude.

    Works standalone (general FortiGate Q&A) and gains device context when
    a scan completes — call set_device(device) to inject the current firewall
    state into the conversation.
    """

    status_message = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._terminal: Optional[SmartTerminal] = None
        self._context = ConversationContext()
        self._worker: Optional[ChatStreamWorker] = None
        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # -- Title --
        title = QLabel("Smart Terminal")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        root.addWidget(title)

        # -- Device context header --
        self._device_header = QLabel("No device connected — general firewall assistant")
        self._device_header.setObjectName("deviceHeader")
        self._device_header.setStyleSheet(
            "#deviceHeader { background-color: #1e2a38; color: #b0bec5; "
            "padding: 10px 14px; border-radius: 6px; font-size: 13px; }"
        )
        root.addWidget(self._device_header)

        # -- Transcript --
        self._transcript = QTextEdit()
        self._transcript.setReadOnly(True)
        self._transcript.setObjectName("transcript")
        self._transcript.setStyleSheet(
            "#transcript { background-color: #ffffff; border: 1px solid #dde3e9; "
            "border-radius: 8px; padding: 10px; font-size: 14px; }"
        )
        root.addWidget(self._transcript, stretch=1)

        # -- Input row --
        input_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask anything about your firewall…")
        self._input.setStyleSheet("padding: 10px; font-size: 14px;")
        self._input.returnPressed.connect(self._on_send)
        input_row.addWidget(self._input, stretch=1)

        self._send_btn = QPushButton("Send")
        self._send_btn.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: white; "
            "padding: 10px 20px; border: none; border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background-color: #2471a3; }"
            "QPushButton:disabled { background-color: #95a5a6; }"
        )
        self._send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self._send_btn)

        reset_btn = QPushButton("↺ Reset")
        reset_btn.setStyleSheet("padding: 10px 14px; border-radius: 6px;")
        reset_btn.clicked.connect(self._on_reset)
        input_row.addWidget(reset_btn)

        root.addLayout(input_row)

        self._append_system(
            "Connect to a device from the Dashboard to give me live context, "
            "or just ask a general FortiGate question to get started."
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_device(self, device: object) -> None:
        """Inject a scanned Device as conversation context (resets the chat)."""
        if not isinstance(device, Device):
            return
        self._context = ConversationContext(device=device)
        self._device_header.setText(
            f"🖥  {device.hostname or device.management_ip} · {device.vendor.value} "
            f"{device.model} · FortiOS {device.software_version}"
        )
        self._transcript.clear()
        self._append_system(
            f"Loaded context for {device.hostname or device.management_ip}. "
            f"Ask me about its policies, VPNs, licenses, or how to fix any findings."
        )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_send(self) -> None:
        message = self._input.text().strip()
        if not message:
            return
        if self._worker and self._worker.isRunning():
            return  # a response is already streaming

        terminal = self._ensure_terminal()
        if terminal is None:
            return  # API key missing — message already shown

        self._input.clear()
        self._append_role("You", "#2471a3")
        self._transcript.insertPlainText(message + "\n\n")
        self._append_role("Assistant", "#27ae60")

        self._set_busy(True)
        self._worker = ChatStreamWorker(terminal, self._context, message, self)
        self._worker.chunk.connect(self._on_chunk)
        self._worker.finished_ok.connect(self._on_stream_done)
        self._worker.failed.connect(self._on_stream_failed)
        self._worker.start()

    def _on_chunk(self, text: str) -> None:
        self._transcript.moveCursor(QTextCursor.MoveOperation.End)
        self._transcript.insertPlainText(text)
        self._transcript.moveCursor(QTextCursor.MoveOperation.End)

    def _on_stream_done(self) -> None:
        self._transcript.insertPlainText("\n\n")
        self._set_busy(False)

    def _on_stream_failed(self, message: str) -> None:
        self._transcript.insertPlainText("\n")
        self._append_system(f"⚠️  {message}")
        self._set_busy(False)

    def _on_reset(self) -> None:
        if self._terminal:
            self._terminal.reset(self._context)
        self._transcript.clear()
        self._append_system("Conversation reset. Device context is preserved.")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_terminal(self) -> Optional[SmartTerminal]:
        if self._terminal is not None:
            return self._terminal
        try:
            self._terminal = SmartTerminal()
            return self._terminal
        except ValueError as exc:
            self._append_system(
                f"⚠️  {exc}\n\nAdd ANTHROPIC_API_KEY to your .env file, "
                "then restart the app."
            )
            return None

    def _set_busy(self, busy: bool) -> None:
        self._send_btn.setEnabled(not busy)
        self._input.setEnabled(not busy)
        self.status_message.emit("Assistant is thinking…" if busy else "Ready")
        if not busy:
            self._input.setFocus()

    def _append_role(self, role: str, color: str) -> None:
        self._transcript.moveCursor(QTextCursor.MoveOperation.End)
        self._transcript.insertHtml(
            f'<b style="color: {color};">{role}:</b> '
        )
        self._transcript.moveCursor(QTextCursor.MoveOperation.End)

    def _append_system(self, text: str) -> None:
        self._transcript.moveCursor(QTextCursor.MoveOperation.End)
        self._transcript.insertHtml(
            f'<p style="color: #7f8c8d; font-style: italic;">{text}</p><br>'
        )
        self._transcript.moveCursor(QTextCursor.MoveOperation.End)
