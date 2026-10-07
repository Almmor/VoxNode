"""系统信息查询：主机名、系统、CPU、内存、磁盘、网卡、运行时长。"""
from __future__ import annotations

import platform
import socket

import psutil

from . import monitor


def _gb(n: float) -> float:
    return round(n / 1024 ** 3, 1)


def hostname() -> str:
    return socket.gethostname()


def os_name() -> str:
    return f"{platform.system()} {platform.release()} ({platform.version()})"


def cpu_model() -> str:
    m = platform.processor()
    return m or platform.machine()


def summary() -> dict:
    mem = monitor.memory()
    return {
        "hostname": hostname(),
        "os": os_name(),
        "cpu_model": cpu_model(),
        "cpu_cores": psutil.cpu_count(logical=True),
        "cpu_percent": monitor.cpu_percent(),
        "mem_total_gb": _gb(mem["total"]),
        "mem_used_gb": _gb(mem["used"]),
        "mem_percent": mem["percent"],
        "uptime": monitor.uptime_text(),
        "boot_time": monitor.boot_time().strftime("%Y-%m-%d %H:%M:%S"),
    }


def interfaces() -> list[dict]:
    """本机网卡：名称 / IPv4 / MAC，用于 WOL 配置提示。"""
    out = []
    stats = psutil.net_if_stats()
    for name, addrs in psutil.net_if_addrs().items():
        entry = {"name": name, "ipv4": "", "mac": "", "up": stats.get(name).isup if name in stats else False}
        for a in addrs:
            if a.family == socket.AF_INET and not entry["ipv4"]:
                entry["ipv4"] = a.address
            elif hasattr(psutil, "AF_LINK") and a.family == psutil.AF_LINK and a.address != "00:00:00:00:00:00":
                entry["mac"] = a.address
        if entry["ipv4"] or entry["mac"]:
            out.append(entry)
    return out


def status_text() -> str:
    """生成语音播报用的状态摘要。"""
    s = summary()
    return (
        f"电脑运行正常，已开机{s['uptime']}。"
        f"处理器占用{s['cpu_percent']:.0f}%，"
        f"内存占用{s['mem_percent']:.0f}%，"
        f"总内存{s['mem_total_gb']}G。"
    )
