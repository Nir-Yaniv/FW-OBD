"""Dashboard — live monitoring wall for the devices you are connected to.

Each connected device gets a panel (site name + CPU/memory gauges + VDOM /
sessions / bandwidth stats), and the grid splits to fit the number of devices.
Panels update live from a MetricsPoller. The full inventory lives on the Devices
page — this page only shows what is actively connected.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from fw_obd.connection.ssh_handler import SSHCredentials
from fw_obd.db.database import Database
from fw_obd.services.metrics import DeviceMetrics
from fw_obd.ui.metrics_poller import MetricsPoller

# Kept for other modules (devices_page imports these).
STATUS_COLORS = {
    "healthy": "#27ae60", "warning": "#f39c12", "critical": "#e74c3c",
    "offline": "#7f8c8d", "unknown": "#95a5a6", "online": "#27ae60",
}
STATUS_LABELS = {
    "healthy": "Healthy", "warning": "Warning", "critical": "Critical",
    "offline": "Offline", "unknown": "Unknown", "online": "Online",
}


def _load_color(pct: float) -> QColor:
    if pct < 60:
        return QColor("#27ae60")
    if pct < 85:
        return QColor("#f39c12")
    return QColor("#e74c3c")


class Gauge(QWidget):
    """Circular arc gauge showing a 0-100 percentage."""

    def __init__(self, label: str) -> None:
        super().__init__()
        self._label = label
        self._value = 0
        self.setMinimumSize(120, 120)

    def set_value(self, value: float) -> None:
        self._value = max(0, min(100, int(round(value))))
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height() - 18)
        m = 10
        rect = QRectF((self.width() - side) / 2 + m, m, side - 2 * m, side - 2 * m)
        p.setPen(QPen(QColor("#e6eaef"), 10, cap=Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 225 * 16, -270 * 16)
        p.setPen(QPen(_load_color(self._value), 10, cap=Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 225 * 16, int(-270 * 16 * self._value / 100))
        p.setPen(QColor("#2c3e50"))
        f = QFont(); f.setBold(True); f.setPointSize(20); p.setFont(f)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self._value}%")
        f2 = QFont(); f2.setPointSize(9); p.setFont(f2)
        p.setPen(QColor("#7f8c8d"))
        p.drawText(self.rect().adjusted(0, self.height() - 18, 0, 0),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self._label)
        p.end()


def _stat_card(label: str, color: str = "#2c3e50") -> tuple[QWidget, QLabel]:
    w = QWidget()
    lay = QVBoxLayout(w); lay.setSpacing(0); lay.setContentsMargins(4, 4, 4, 4)
    value = QLabel("—"); value.setAlignment(Qt.AlignmentFlag.AlignCenter)
    value.setStyleSheet(f"font-size:19px;font-weight:bold;color:{color};")
    cap = QLabel(label); cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cap.setStyleSheet("font-size:10px;color:#7f8c8d;")
    lay.addWidget(value); lay.addWidget(cap)
    return w, value


class DevicePanel(QFrame):
    """Live metrics panel for one connected device."""

    closed = pyqtSignal(int)  # device_id

    def __init__(self, device: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._device_id = int(device["id"])
        self.setObjectName("panel")
        self.setStyleSheet(
            "#panel{background:#ffffff;border:1px solid #dde3e9;border-radius:10px;}"
        )
        self.setMinimumSize(360, 250)
        self._build(device)

    def _build(self, device: dict) -> None:
        root = QVBoxLayout(self); root.setContentsMargins(16, 12, 16, 14); root.setSpacing(10)

        header = QHBoxLayout()
        self._dot = QLabel("●"); self._dot.setStyleSheet("color:#f39c12;font-size:14px;")
        name = QLabel(device.get("name") or device.get("management_ip", ""))
        name.setStyleSheet("font-size:15px;font-weight:bold;color:#16324f;")
        ip = QLabel(device.get("management_ip", "")); ip.setStyleSheet("color:#7f8c8d;")
        close = QPushButton("✕"); close.setFixedSize(22, 22)
        close.setStyleSheet("border:none;color:#95a5a6;font-weight:bold;")
        close.clicked.connect(lambda: self.closed.emit(self._device_id))
        header.addWidget(self._dot); header.addWidget(name); header.addStretch()
        header.addWidget(ip); header.addWidget(close)
        root.addLayout(header)

        gauges = QHBoxLayout()
        self._cpu = Gauge("CPU"); self._mem = Gauge("Memory")
        gauges.addWidget(self._cpu); gauges.addWidget(self._mem)
        root.addLayout(gauges)

        stats = QHBoxLayout()
        vdom_w, self._vdom = _stat_card("VDOMs")
        sess_w, self._sessions = _stat_card("Sessions")
        in_w, self._bw_in = _stat_card("Mbps in", "#2471a3")
        out_w, self._bw_out = _stat_card("Mbps out", "#8e44ad")
        for w in (vdom_w, sess_w, in_w, out_w):
            stats.addWidget(w)
        root.addLayout(stats)

        self._footer = QLabel("Connecting… waiting for first sample")
        self._footer.setStyleSheet("color:#7f8c8d;font-size:11px;")
        root.addWidget(self._footer)

    def update_metrics(self, m: DeviceMetrics) -> None:
        self._dot.setStyleSheet("color:#2ecc71;font-size:14px;")  # green — live
        self._cpu.set_value(m.cpu_pct)
        self._mem.set_value(m.mem_pct)
        self._vdom.setText(str(m.vdoms))
        self._sessions.setText(f"{m.sessions:,}")
        self._bw_in.setText(f"↓ {m.bw_in_kbps / 1000:.1f}")
        self._bw_out.setText(f"↑ {m.bw_out_kbps / 1000:.1f}")
        self._footer.setText(f"Live · uptime {m.uptime}" if m.uptime else "Live")

    def set_offline(self, message: str) -> None:
        self._dot.setStyleSheet("color:#e74c3c;font-size:14px;")  # red — lost
        self._footer.setText(f"⚠ {message}")

    @property
    def device_id(self) -> int:
        return self._device_id


class DashboardWidget(QWidget):
    """Live monitoring grid of connected devices."""

    status_message = pyqtSignal(str)
    device_scanned = pyqtSignal(object)  # kept for smart-terminal context wiring

    def __init__(self, db: Database, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db = db
        self._panels: dict[int, DevicePanel] = {}
        self._pollers: dict[int, MetricsPoller] = {}
        self._build()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        title = QLabel("Live Monitoring")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        root.addWidget(title)

        self._empty = QLabel(
            "No devices connected yet.\n\nConnect a device from the Devices page "
            "to see its live CPU, memory, VDOM, sessions and bandwidth here."
        )
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet("color:#7f8c8d; font-size:14px; padding:60px;")
        root.addWidget(self._empty, stretch=1)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setSpacing(14)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._scroll.setWidget(self._grid_host)
        self._scroll.hide()
        root.addWidget(self._scroll, stretch=1)

    # --------------------------------------------------------------- monitors
    def add_monitor(
        self,
        device: dict,
        credentials: SSHCredentials,
        udm: object | None = None,
        vdoms: int = 1,
        interval_secs: int = 5,
    ) -> None:
        """Start (or restart) live monitoring for a device and show its panel."""
        device_id = int(device["id"])
        if device_id in self._pollers:
            self._stop_poller(device_id)  # restart with a fresh session

        panel = self._panels.get(device_id)
        if panel is None:
            panel = DevicePanel(device)
            panel.closed.connect(self._remove_monitor)
            self._panels[device_id] = panel

        poller = MetricsPoller(credentials, interval_secs=interval_secs, vdoms=vdoms)
        poller.updated.connect(panel.update_metrics)
        poller.failed.connect(lambda msg, pid=device_id: self._on_poll_failed(pid, msg))
        self._pollers[device_id] = poller
        poller.start()

        self._relayout()
        self.status_message.emit(f"Monitoring {device.get('name', device_id)}")
        if udm is not None:
            self.device_scanned.emit(udm)

    def _on_poll_failed(self, device_id: int, message: str) -> None:
        panel = self._panels.get(device_id)
        if panel:
            panel.set_offline(message)
        self._db.update_device_status(device_id, "offline")
        self.status_message.emit(f"Lost connection: {message}")

    def _remove_monitor(self, device_id: int) -> None:
        self._stop_poller(device_id)
        panel = self._panels.pop(device_id, None)
        if panel:
            self._grid.removeWidget(panel)
            panel.deleteLater()
        self._relayout()

    def _stop_poller(self, device_id: int) -> None:
        poller = self._pollers.pop(device_id, None)
        if poller:
            poller.stop()

    def _relayout(self) -> None:
        panels = list(self._panels.values())
        for p in panels:
            self._grid.removeWidget(p)
        if not panels:
            self._scroll.hide()
            self._empty.show()
            return
        self._empty.hide()
        self._scroll.show()
        cols = 1 if len(panels) == 1 else 2
        for i, panel in enumerate(panels):
            self._grid.addWidget(panel, i // cols, i % cols)

    def stop_all(self) -> None:
        """Stop every poller — call on application close."""
        for device_id in list(self._pollers):
            self._stop_poller(device_id)
