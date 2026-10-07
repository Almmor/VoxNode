"""进程与系统监控：CPU / 内存 / 磁盘 / 网络 / 进程表 / 结束进程。"""
from __future__ import annotations

import datetime as _dt
import time

import psutil


def cpu_percent(interval: float = 0.0) -> float:
    return psutil.cpu_percent(interval=interval)


def cpu_per_core(interval: float = 0.0) -> list[float]:
    return psutil.cpu_percent(interval=interval, percpu=True)


def memory() -> dict:
    m = psutil.virtual_memory()
    return {
        "total": m.total,
        "used": m.used,
        "percent": m.percent,
    }


def disk_usage(path: str = "C:\\") -> dict:
    d = psutil.disk_usage(path)
    return {"total": d.total, "used": d.used, "free": d.free, "percent": d.percent}


def disks() -> list[dict]:
    out = []
    for part in psutil.disk_partitions(all=False):
        if part.fstype:
            try:
                d = psutil.disk_usage(part.mountpoint)
            except Exception:
                continue
            out.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total": d.total,
                "used": d.used,
                "percent": d.percent,
            })
    return out


def net_io() -> dict:
    n = psutil.net_io_counters()
    return {"bytes_sent": n.bytes_sent, "bytes_recv": n.bytes_recv}


def boot_time() -> _dt.datetime:
    return _dt.datetime.fromtimestamp(psutil.boot_time())


def uptime_text() -> str:
    up = time.time() - psutil.boot_time()
    h, rem = divmod(int(up), 3600)
    m, s = divmod(rem, 60)
    d, h = divmod(h, 24)
    parts = []
    if d:
        parts.append(f"{d}天")
    parts.append(f"{h}小时{m}分{s}秒")
    return "".join(parts)


def processes(search: str = "") -> list[dict]:
    """返回进程列表（按内存降序），search 过滤名称/用户名。"""
    procs = []
    attrs = ["pid", "name", "username", "memory_info", "cpu_percent"]
    for p in psutil.process_iter(attrs):
        try:
            info = p.info
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        name = info["name"] or ""
        user = info["username"] or ""
        if search and search.lower() not in name.lower() and search.lower() not in user.lower():
            continue
        mem = info["memory_info"].rss if info["memory_info"] else 0
        procs.append({
            "pid": info["pid"],
            "name": name,
            "username": (user.split("\\")[-1] if user else ""),
            "mem": mem,
            "mem_percent": mem / psutil.virtual_memory().total * 100,
            "cpu": info["cpu_percent"] or 0.0,
        })
    procs.sort(key=lambda x: x["mem"], reverse=True)
    return procs


def kill(pid: int) -> None:
    proc = psutil.Process(int(pid))
    for child in proc.children(recursive=True):
        try:
            child.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    proc.kill()


def find_running(pattern: str) -> list[psutil.Process]:
    """按名称（大小写不敏感）查找运行中的进程。"""
    p = pattern.lower()
    if p.endswith(".exe"):
        p = p[:-4]
    out = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if p in (proc.info["name"] or "").lower():
                out.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return out


def kill_by_name(pattern: str) -> int:
    """按名称结束进程，返回结束的数量。"""
    killed = 0
    for proc in find_running(pattern):
        try:
            proc.kill()
            killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return killed
