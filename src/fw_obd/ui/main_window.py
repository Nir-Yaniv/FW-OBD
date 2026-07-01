"""Main application window — top-level PyQt6 shell."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from fw_obd.db.database import Database
from fw_obd.ui.dashboard import DashboardWidget
from fw_obd.ui.devices_page import DevicesPageWidget
from fw_obd.ui.settings_page import SettingsPageWidget
from fw_obd.ui.smart_terminal_widget import SmartTerminalWidget


class MainWindow(QMainWindow):
    """
    Root window. Layout:
      - Left sidebar: nav buttons (Dashboard, Devices, Reports, Settings)
      - Center: stacked page widget
      - Status bar: connection info + version
    """

    APP_TITLE = "Firewall OBD"
    MIN_WIDTH = 1280
    MIN_HEIGHT = 720

    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db
        self._setup_window()
        self._build_layout()
        self._apply_stylesheet()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.setWindowTitle(self.APP_TITLE)
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.resize(1440, 900)

    def _build_layout(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # -- Sidebar --
        sidebar = self._build_sidebar()
        root_layout.addWidget(sidebar)

        # -- Page stack --
        self._pages = QStackedWidget()
        self._dashboard = DashboardWidget(self._db)
        self._dashboard.status_message.connect(self.set_status)
        self._pages.addWidget(self._dashboard)                         # index 0

        self._terminal = SmartTerminalWidget()
        self._terminal.status_message.connect(self.set_status)
        self._dashboard.device_scanned.connect(self._terminal.set_device)
        self._pages.addWidget(self._terminal)                          # index 1

        self._devices = DevicesPageWidget(self._db)
        self._devices.status_message.connect(self.set_status)
        # Connecting a device from the inventory starts live monitoring on the Dashboard.
        self._devices.monitor_requested.connect(self._on_monitor_requested)
        self._pages.addWidget(self._devices)                           # index 2
        self._pages.addWidget(self._placeholder("Reports (coming soon)"))  # index 3

        self._settings = SettingsPageWidget()
        self._settings.status_message.connect(self.set_status)
        self._pages.addWidget(self._settings)                          # index 4
        root_layout.addWidget(self._pages, stretch=1)

        # -- Status bar --
        self._status = QStatusBar()
        self._status.showMessage("Ready")
        self.setStatusBar(self._status)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo area
        logo = QLabel("🔥 Firewall OBD")
        logo.setObjectName("logo")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedHeight(64)
        layout.addWidget(logo)

        # Nav buttons
        self._nav_buttons: list[QPushButton] = []
        nav_items = [
            ("Dashboard", 0),
            ("Smart Terminal", 1),
            ("Devices", 2),
            ("Reports", 3),
            ("Settings", 4),
        ]
        for label, page_idx in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, idx=page_idx: self._navigate(idx))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        self._nav_buttons[0].setChecked(True)  # Dashboard active by default
        layout.addStretch()

        version = QLabel("v0.1.0")
        version.setObjectName("versionLabel")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(version)
        return sidebar

    def _navigate(self, page_idx: int) -> None:
        self._pages.setCurrentIndex(page_idx)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == page_idx)
        if page_idx == 2:  # refresh inventory on entering the Devices page
            self._devices.reload()

    def _on_monitor_requested(self, device: object, credentials: object, udm: object) -> None:
        """A device was connected — start live monitoring and show the Dashboard."""
        vdoms = len(getattr(udm, "vdoms", None) or []) or 1
        interval = self._settings.config.poll_interval_secs
        self._dashboard.add_monitor(device, credentials, udm=udm, vdoms=vdoms, interval_secs=interval)
        self._navigate(0)  # jump to the live Dashboard

    def closeEvent(self, event) -> None:  # noqa: N802
        self._dashboard.stop_all()
        super().closeEvent(event)

    @staticmethod
    def _placeholder(text: str) -> QWidget:
        w = QWidget()
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(w)
        layout.addWidget(lbl)
        return w

    # ------------------------------------------------------------------
    # Stylesheet (light + dark toggling done via QApplication.setStyleSheet)
    # ------------------------------------------------------------------

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f5;
            }
            #sidebar {
                background-color: #1e2a38;
            }
            #logo {
                color: #ffffff;
                font-size: 16px;
                font-weight: bold;
                padding: 12px;
            }
            #navButton {
                background-color: transparent;
                color: #b0bec5;
                border: none;
                text-align: left;
                padding: 12px 20px;
                font-size: 14px;
            }
            #navButton:hover {
                background-color: #2c3e50;
                color: #ffffff;
            }
            #navButton:checked {
                background-color: #2980b9;
                color: #ffffff;
            }
            #versionLabel {
                color: #546e7a;
                font-size: 11px;
                padding: 8px;
            }
        """)

    def set_status(self, message: str) -> None:
        self._status.showMessage(message)
