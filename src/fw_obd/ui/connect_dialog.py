"""SSH credential dialog for connecting to a firewall device."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from fw_obd.connection.ssh_handler import SSHCredentials


class ConnectDialog(QDialog):
    """Collect SSH credentials for a device connection."""

    def __init__(self, management_ip: str, device_name: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Connect — {device_name}")
        self.setMinimumWidth(400)
        self._ip = management_ip
        self._build()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._ip_label = QLineEdit(self._ip)
        self._ip_label.setReadOnly(True)
        self._username = QLineEdit()
        self._username.setPlaceholderText("admin")
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(22)
        self._use_key = QCheckBox("Use SSH key file instead of password")

        form.addRow("Management IP", self._ip_label)
        form.addRow("Username *", self._username)
        form.addRow("Password", self._password)
        form.addRow("SSH Port", self._port)
        form.addRow("", self._use_key)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def is_valid(self) -> bool:
        return bool(self._username.text().strip())

    def credentials(self) -> SSHCredentials:
        return SSHCredentials(
            host=self._ip,
            username=self._username.text().strip(),
            password=self._password.text(),
            port=self._port.value(),
            device_type="fortinet",
        )
