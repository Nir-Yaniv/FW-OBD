"""Live device metrics — fetch and parse FortiGate performance counters.

Parses `get system performance status` into a DeviceMetrics snapshot used by the
live monitoring Dashboard (CPU, memory, sessions, bandwidth, uptime).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from fw_obd.parsers.fortigate.commands import GET_SYSTEM_PERFORMANCE

_CPU_IDLE = re.compile(r"CPU states:.*?(\d+)%\s*idle", re.IGNORECASE)
_MEM_USED = re.compile(r"Memory:.*?used\s*\((\d+(?:\.\d+)?)%\)", re.IGNORECASE)
_NET = re.compile(r"Average network usage:\s*(\d+)\s*/\s*(\d+)\s*kbps", re.IGNORECASE)
_SESSIONS = re.compile(r"Average sessions:\s*(\d+)\s*sessions", re.IGNORECASE)
_UPTIME = re.compile(r"Uptime:\s*(.+)", re.IGNORECASE)


@dataclass
class DeviceMetrics:
    cpu_pct: float = 0.0
    mem_pct: float = 0.0
    sessions: int = 0
    bw_in_kbps: float = 0.0
    bw_out_kbps: float = 0.0
    vdoms: int = 1
    uptime: str = ""


def parse_performance_status(output: str) -> DeviceMetrics:
    """Parse `get system performance status` output into a DeviceMetrics."""
    m = DeviceMetrics()
    idle = _CPU_IDLE.search(output)
    if idle:
        m.cpu_pct = max(0.0, min(100.0, 100.0 - float(idle.group(1))))
    mem = _MEM_USED.search(output)
    if mem:
        m.mem_pct = float(mem.group(1))
    net = _NET.search(output)
    if net:
        m.bw_in_kbps = float(net.group(1))
        m.bw_out_kbps = float(net.group(2))
    sess = _SESSIONS.search(output)
    if sess:
        m.sessions = int(sess.group(1))
    up = _UPTIME.search(output)
    if up:
        m.uptime = up.group(1).strip()
    return m


def fetch_metrics(ssh, vdoms: int = 1) -> DeviceMetrics:
    """Run the performance command over an open SSH session and parse it.

    ``ssh`` is an SSHHandler-like object exposing ``send_command``. ``vdoms`` is
    supplied from the device UDM (not present in the performance output).
    """
    output = ssh.send_command(GET_SYSTEM_PERFORMANCE)
    metrics = parse_performance_status(output)
    metrics.vdoms = vdoms
    return metrics
