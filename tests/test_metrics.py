"""Tests for FortiGate performance metrics parsing."""

from fw_obd.services.metrics import parse_performance_status

SAMPLE = """CPU states: 1% user 2% system 0% nice 95% idle 0% iowait 0% irq 2% softirq
CPU0 states: 1% user 2% system 0% nice 95% idle
Memory: 2061640k total, 1148776k used (55.7%), 912864k free (44.3%)
Average network usage: 145 / 38 kbps in 1 minute, 130 / 35 kbps in 10 minutes
Average sessions: 18420 sessions in 1 minute, 17800 sessions in 10 minutes
Uptime: 15 days,  3 hours,  22 minutes
"""


def test_parse_performance_status():
    m = parse_performance_status(SAMPLE)
    assert m.cpu_pct == 5.0            # 100 - 95% idle
    assert m.mem_pct == 55.7
    assert m.bw_in_kbps == 145.0
    assert m.bw_out_kbps == 38.0
    assert m.sessions == 18420
    assert m.uptime.startswith("15 days")


def test_parse_handles_empty_output():
    m = parse_performance_status("")
    assert m.cpu_pct == 0.0
    assert m.mem_pct == 0.0
    assert m.sessions == 0
    assert m.uptime == ""
