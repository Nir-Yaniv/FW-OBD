"""Credential dialog for connecting to a firewall device (SSH or HTTPS/REST)."""

from __future__ import annotations

from typing import Union

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from fw_obd.connection.rest_client import RESTCredentials
from fw_obd.connection.ssh_handler import SSHCredentials

_PROTO_SSH = "SSH (CLI)"
_PROTO_HTTPS = "HTTPS (REST API)"


class ConnectDialog(QDialog):
    """Collect SSH or HTTPS/REST credentials for a device connection."""

    def __init__(self, management_ip: str, device_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Connect — {device_name}")
        self.setMinimumWidth(420)
        self._ip = management_ip
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._ip_label = QLineEdit(self._ip)
        self._ip_label.setReadOnly(True)

        self._protocol = QComboBox()
        self._protocol.addItems([_PROTO_SSH, _PROTO_HTTPS])
        self._protocol.currentTextChanged.connect(self._on_protocol_changed)

        # SSH fields
        self._username = QLineEdit()
        self._username.setPlaceholderText("admin")
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._use_key = QCheckBox("Use SSH key file instead of password")

        # HTTPS fields
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText("REST API key (System → Administrators → REST API Admin)")
        self._allow_self_signed = QCheckBox("Allow self-signed certificate (insecure)")
        self._https_notice = QLabel(
            "HTTPS mode: quick audit and config backup via the FortiOS REST API. "
            "Live dashboard monitoring is not yet available over HTTPS."
        )
        self._https_notice.setWordWrap(True)
        self._https_notice.setStyleSheet("color: #8a6d3b;")

        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(22)

        form.addRow("Management IP", self._ip_label)
        form.addRow("Protocol", self._protocol)
        self._form = form

        # SSH rows
        form.addRow("Username *", self._username)
        form.addRow("Password", self._password)
        form.addRow("", self._use_key)
        # HTTPS rows
        form.addRow("API key *", self._api_key)
        form.addRow("", self._allow_self_signed)
        form.addRow("Port", self._port)

        layout.addLayout(form)
        layout.addWidget(self._https_notice)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._on_protocol_changed(_PROTO_SSH)

    # ------------------------------------------------------------------

    def _is_https(self) -> bool:
        return self._protocol.currentText() == _PROTO_HTTPS

    def _set_row_visible(self, widget, visible: bool) -> None:
        widget.setVisible(visible)
        label = self._form.labelForField(widget)
        if label is not None:
            label.setVisible(visible)

    def _on_protocol_changed(self, _text: str) -> None:
        https = self._is_https()
        for widget in (self._username, self._password, self._use_key):
            self._set_row_visible(widget, not https)
        for widget in (self._api_key, self._allow_self_signed):
            self._set_row_visible(widget, https)
        self._https_notice.setVisible(https)
        self._port.setValue(443 if https else 22)

    # ------------------------------------------------------------------

    def is_valid(self) -> bool:
        if self._is_https():
            return bool(self._api_key.text().strip())
        return bool(self._username.text().strip())

    def credentials(self) -> Union[SSHCredentials, RESTCredentials]:
        if self._is_https():
            return RESTCredentials(
                host=self._ip,
                api_key=self._api_key.text().strip(),
                port=self._port.value(),
                verify_tls=not self._allow_self_signed.isChecked(),
            )
        return SSHCredentials(
            host=self._ip,
            username=self._username.text().strip(),
            password=self._password.text(),
            port=self._port.value(),
            device_type="fortinet",
        )
