"""自制 SVG 图标的加载与染色。

本目录下的图标全部是手写的线性 SVG（24×24 viewBox、白色描边），
运行时由 QtSvg 渲染成位图，再用 CompositionMode_SourceIn 覆盖成目标颜色。
这样一份 SVG 就能同时服务「未选中（灰）/ 悬停 / 选中（强调色）」等状态，
换强调色时也不需要重新导出任何素材。

图标名与 main_window.NAV 的 key 一一对应，测试会校验两者不漂移。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap

# 与导航项一一对应的图标名（顺序无关，测试会检查集合一致）
ICON_NAMES: tuple[str, ...] = (
    "dashboard",
    "power",
    "screenshot",
    "processes",
    "apps",
    "wol",
    "mijia",
    "mijia_channel",
    "remote",
    "assistant",
    "settings",
)


def assets_dir() -> Path:
    """SVG 资源目录；源码运行与 PyInstaller 打包后都能定位到。"""
    candidates: list[Path] = []
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        candidates.append(Path(mei) / "voxnode" / "assets")
    here = Path(__file__).resolve().parent
    candidates.append(here / "assets")
    candidates.append(here.parent / "voxnode" / "assets")
    for c in candidates:
        if (c / "icons").is_dir():
            return c
    return candidates[-1]


def icon_path(name: str) -> Path:
    return assets_dir() / "icons" / f"{name}.svg"


def svg_text(name: str) -> str:
    """读回 SVG 源码（供测试校验 XML 合法性）。"""
    return icon_path(name).read_text("utf-8")


def svg_pixmap(name: str, size: int, color: str = "#ffffff",
               dpr: float = 1.0) -> QPixmap:
    """把图标渲染为指定颜色与尺寸的位图；文件缺失时返回空位图而不抛异常。"""
    px = max(1, int(round(size * dpr)))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)

    path = icon_path(name)
    if not path.is_file():
        return pm

    try:
        from PyQt6.QtSvg import QSvgRenderer
    except ImportError:  # pragma: no cover - 打包裁剪掉 QtSvg 时不该发生
        return pm

    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return pm

    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(p)
    p.end()

    # 染色：保留 alpha，只替换 RGB
    tinted = QPixmap(px, px)
    tinted.fill(Qt.GlobalColor.transparent)
    p2 = QPainter(tinted)
    p2.drawPixmap(0, 0, pm)
    p2.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    p2.fillRect(tinted.rect(), QColor(color))
    p2.end()
    tinted.setDevicePixelRatio(dpr)
    return tinted


def svg_icon(name: str, size: int, color: str = "#ffffff",
             dpr: float = 1.0) -> QIcon:
    return QIcon(svg_pixmap(name, size, color, dpr))
