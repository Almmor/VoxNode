"""电源控制：关机 / 重启 / 锁屏 / 睡眠 / 休眠 / 注销 / 定时关机 / 取消。"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta


def _run(args: list[str]) -> subprocess.CompletedProcess:
    """执行系统命令；输出统一按 UTF-8 容错解码，避免本地化编码导致崩溃。"""
    out = subprocess.run(args, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return subprocess.CompletedProcess(
        args,
        out.returncode,
        (out.stdout or b"").decode("utf-8", errors="replace"),
        (out.stderr or b"").decode("utf-8", errors="replace"),
    )


def shutdown(delay: int = 0, comment: str = "VoxNode 关机") -> subprocess.CompletedProcess:
    """延迟 delay 秒关机，期间可用 cancel() 撤销。"""
    return _run(["shutdown", "/s", "/t", str(int(delay)), "/c", comment])


def restart(delay: int = 0) -> subprocess.CompletedProcess:
    return _run(["shutdown", "/r", "/t", str(int(delay)), "/c", "VoxNode 重启"])


def cancel() -> subprocess.CompletedProcess:
    return _run(["shutdown", "/a"])


def lock() -> subprocess.CompletedProcess:
    return _run(["rundll32.exe", "user32.dll,LockWorkStation"])


def sleep() -> subprocess.CompletedProcess:
    return _run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])


def hibernate() -> subprocess.CompletedProcess:
    return _run(["rundll32.exe", "powrprof.dll,SetSuspendState", "1,1,0"])


def signout() -> subprocess.CompletedProcess:
    return _run(["shutdown", "/l"])


def schedule_at(hhmm: str) -> subprocess.CompletedProcess:
    """在指定 HH:MM（如 23:30）关机；仅支持当天未来时刻。"""
    target = datetime.strptime(hhmm, "%H:%M").time()
    now = datetime.now()
    when = datetime.combine(now.date(), target)
    if when <= now:
        when += timedelta(days=1)
    delay = int((when - now).total_seconds())
    return shutdown(delay, f"VoxNode 定时关机 {hhmm}")


ACTIONS = {
    "shutdown": shutdown,
    "restart": restart,
    "lock": lock,
    "sleep": sleep,
    "hibernate": hibernate,
    "signout": signout,
}


def execute(action: str, delay: int = 0) -> subprocess.CompletedProcess:
    if action not in ACTIONS:
        raise ValueError(f"未知电源操作: {action}")
    return ACTIONS[action](delay)
