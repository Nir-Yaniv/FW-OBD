"""Tests for the settings/config service."""

from fw_obd.services import config
from fw_obd.services.config import AppConfig


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "settings.json")
    c = AppConfig(
        backup_dir=str(tmp_path / "bk"), retention_days=30,
        poll_interval_secs=10, ai_model="claude-opus-4-8",
    )
    c.save()
    loaded = AppConfig.load()
    assert loaded.retention_days == 30
    assert loaded.poll_interval_secs == 10
    assert loaded.ai_model == "claude-opus-4-8"


def test_config_defaults_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "nope.json")
    loaded = AppConfig.load()
    assert loaded.retention_days == 14
    assert loaded.poll_interval_secs == 5


def test_settings_page_builds(qtbot):
    from fw_obd.ui.settings_page import SettingsPageWidget

    w = SettingsPageWidget()
    qtbot.addWidget(w)
    assert w._retention.value() >= 1
    assert w._interval.value() >= 1
    assert w._model.currentText()
