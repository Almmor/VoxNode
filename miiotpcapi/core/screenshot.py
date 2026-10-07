"""屏幕截取：基于 mss，支持全屏 / 指定显示器，保存为 PNG 或 JPEG。"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import mss

try:  # mss >= 10 提供 MSS 类，旧版本用 mss()
    from mss import MSS as _MSS
except ImportError:  # pragma: no cover - 兼容旧版本
    _MSS = mss.mss

# 支持保存的图片格式 -> 扩展名
FORMATS: dict[str, str] = {"png": ".png", "jpeg": ".jpg", "jpg": ".jpg"}

# 所有截图文件名的匹配模式（历史记录、清理、遥控台取图都按这个找）
PATTERNS: tuple[str, ...] = ("screenshot_*.png", "screenshot_*.jpg", "screenshot_*.jpeg")

JPEG_QUALITY = 92


def list_monitors() -> list[dict]:
    with _MSS() as sct:
        return [dict(m) for m in sct.monitors]


def _grab(monitor: int):
    """抓一帧，返回 (截图对象, 上下文已关闭) 的原始数据副本。"""
    with _MSS() as sct:
        if monitor < 0:
            shot = sct.grab(sct.monitors[0])
        else:
            idx = monitor if monitor < len(sct.monitors) else 0
            shot = sct.grab(sct.monitors[idx])
        # 复制出像素数据，确保离开 with 之后仍然有效
        return bytes(shot.rgb), tuple(shot.size)


def _save_jpeg(rgb: bytes, size: tuple[int, int], path: Path) -> bool:
    """用 Qt 编码 JPEG。核心库刻意不依赖 PyQt6，所以这里延迟导入。"""
    try:
        from PyQt6.QtGui import QImage
    except ImportError:  # pragma: no cover - 无 GUI 环境
        return False
    w, h = size
    if w <= 0 or h <= 0:
        return False
    img = QImage(rgb, w, h, w * 3, QImage.Format.Format_RGB888)
    return bool(img.save(str(path), "JPEG", JPEG_QUALITY))


def capture(save_dir: str | Path, monitor: int = -1, fmt: str = "png") -> Path:
    """截取指定显示器（-1 表示全部拼接为一张全屏图），返回保存路径。

    fmt 支持 png / jpeg；无法编码 JPEG 时（缺 Qt）自动退回 PNG，保证截图不失败。
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "full" if monitor < 0 else f"mon{monitor}"
    key = (fmt or "png").strip().lower()
    ext = FORMATS.get(key, ".png")
    path = save_dir / f"screenshot_{ts}_{suffix}{ext}"

    rgb, size = _grab(monitor)
    if ext != ".png" and _save_jpeg(rgb, size, path):
        return path

    # PNG 兜底（也是默认格式）
    path = path.with_suffix(".png")
    mss.tools.to_png(rgb, size, output=str(path))
    return path


def recent(save_dir: str | Path, limit: int = 20) -> list[Path]:
    save_dir = Path(save_dir)
    if not save_dir.is_dir():
        return []
    files: list[Path] = []
    for pattern in PATTERNS:
        files.extend(save_dir.glob(pattern))
    return sorted(set(files), reverse=True)[:limit]


def latest(save_dir: str | Path) -> Path | None:
    files = recent(save_dir, limit=1)
    return files[0] if files else None


def cleanup(save_dir: str | Path, days: int) -> int:
    """删除 days 天前的截图，返回删除数量；days <= 0 表示不清理。"""
    try:
        days = int(days)
    except (TypeError, ValueError):
        return 0
    if days <= 0:
        return 0
    save_dir = Path(save_dir)
    if not save_dir.is_dir():
        return 0

    cutoff = time.time() - days * 86400
    removed = 0
    for pattern in PATTERNS:
        for f in save_dir.glob(pattern):
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
                    removed += 1
            except OSError:
                pass
    return removed
