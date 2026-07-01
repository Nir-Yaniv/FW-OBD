"""Settings page — API key (keyring), backup directory, retention, poll interval."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from fw_obd.services.config import AppConfig, api_key_is_set, set_api_key

AI_MODELS = ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"]


class SettingsPageWidget(QWidget):
    """Edit and persist application settings."""

    status_message = pyqtSignal(str)
    settings_saved = pyqtSignal(object)  # AppConfig

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = AppConfig.load()
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Settings")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(12)

        # --- Anthropic API key (stored in the OS keyring) ---
        key_row = QHBoxLayout()
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.setPlaceholderText(
            "Stored ✓ — leave blank to keep" if api_key_is_set() else "sk-ant-…"
        )
        show = QPushButton("Show")
        show.setCheckable(True)
        show.toggled.connect(
            lambda on: self._api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        key_row.addWidget(self._api_key, 1)
        key_row.addWidget(show)
        form.addRow("Anthropic API Key", key_row)

        self._api_status = QLabel(
            "✓ A key is currently stored (OS keyring)." if api_key_is_set()
            else "⚠ No key set — the Smart Terminal chat will not work until you add one."
        )
        self._api_status.setStyleSheet(
            "color:#27ae60;" if api_key_is_set() else "color:#e67e22;"
        )
        form.addRow("", self._api_status)

        # --- AI model ---
        self._model = QComboBox()
        self._model.addItems(AI_MODELS)
        if self._config.ai_model not in AI_MODELS:
            self._model.addItem(self._config.ai_model)
        self._model.setCurrentText(self._config.ai_model)
        form.addRow("AI Model", self._model)

        # --- Backup directory ---
        dir_row = QHBoxLayout()
        self._backup_dir = QLineEdit(self._config.backup_dir)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_dir)
        dir_row.addWidget(self._backup_dir, 1)
        dir_row.addWidget(browse)
        form.addRow("Backup Directory", dir_row)

        # --- Retention days ---
        self._retention = QSpinBox()
        self._retention.setRange(1, 3650)
        self._retention.setValue(self._config.retention_days)
        self._retention.setSuffix("  days")
        form.addRow("Backup Retention", self._retention)

        # --- Poll interval ---
        self._interval = QSpinBox()
        self._interval.setRange(1, 300)
        self._interval.setValue(self._config.poll_interval_secs)
        self._interval.setSuffix("  seconds")
        form.addRow("Dashboard Refresh", self._interval)

        root.addLayout(form)

        save_row = QHBoxLayout()
        save_row.addStretch()
        self._saved_label = QLabel("")
        self._saved_label.setStyleSheet("color:#27ae60;")
        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self._save)
        save_row.addWidget(self._saved_label)
        save_row.addWidget(save_btn)
        root.addLayout(save_row)
        root.addStretch()

    def _browse_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select backup directory", self._backup_dir.text())
        if path:
            self._backup_dir.setText(path)

    def _save(self) -> None:
        # API key -> keyring (only if the user typed one)
        typed_key = self._api_key.text().strip()
        if typed_key:
            if set_api_key(typed_key):
                self._api_key.clear()
                self._api_key.setPlaceholderText("Stored ✓ — leave blank to keep")
                self._api_status.setText("✓ A key is currently stored (OS keyring).")
                self._api_status.setStyleSheet("color:#27ae60;")
            else:
                self._api_status.setText("⚠ Could not store the key in the OS keyring.")
                self._api_status.setStyleSheet("color:#e74c3c;")

        self._config.ai_model = self._model.currentText().strip()
        self._config.backup_dir = self._backup_dir.text().strip() or self._config.backup_dir
        self._config.retention_days = self._retention.value()
        self._config.poll_interval_secs = self._interval.value()
        self._config.save()
        Path(self._config.backup_dir).mkdir(parents=True, exist_ok=True)

        self._saved_label.setText("Saved ✓")
        self.status_message.emit("Settings saved")
        self.settings_saved.emit(self._config)

    @property
    def config(self) -> AppConfig:
        return self._config
