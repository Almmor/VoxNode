"""屏幕截取：基于 mss，支持全屏 / 指定显示器，保存为 PNG。"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import mss

try:  # mss >= 10 提供 MSS 类，旧版本用 mss()
    from mss import MSS as _MSS
except ImportError:  # pragma: no cover - 兼容旧版本
    _MSS = mss.mss


def list_monitors() -> list[dict]:
    with _MSS() as sct:
        return [dict(m) for m in sct.monitors]


def capture(save_dir: str | Path, monitor: int = -1) -> Path:
    """截取指定显示器（-1 表示全部拼接为一张全屏图），返回保存路径。"""
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "full" if monitor < 0 else f"mon{monitor}"
    path = save_dir / f"screenshot_{ts}_{suffix}.png"
    with _MSS() as sct:
        if monitor < 0:
            shot = sct.grab(sct.monitors[0])
        else:
            idx = monitor if monitor < len(sct.monitors) else 0
            shot = sct.grab(sct.monitors[idx])
        mss.tools.to_png(shot.rgb, shot.size, output=str(path))
    return path


def recent(save_dir: str | Path, limit: int = 20) -> list[Path]:
    save_dir = Path(save_dir)
    if not save_dir.is_dir():
        return []
    files = sorted(save_dir.glob("screenshot_*.png"), reverse=True)
    return files[:limit]
