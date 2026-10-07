"""页面通用构件：标准页头、卡片容器、工具行。"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


def page(title: str, subtitle: str = "", root: QWidget | None = None) -> tuple[QWidget, QVBoxLayout]:
    """标准页面骨架。传入 root（如 QFrame 子类的 self）则直接构建在其上。"""
    root = root if root is not None else QFrame()
    lay = QVBoxLayout(root)
    lay.setContentsMargins(28, 24, 28, 24)
    lay.setSpacing(16)

    h = QLabel(title)
    h.setProperty("h1", True)
    lay.addWidget(h)
    if subtitle:
        s = QLabel(subtitle)
        s.setProperty("muted", True)
        lay.addWidget(s)
    return root, lay


def card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    """卡片容器，返回 (卡片, 内部布局)。"""
    frame = QFrame()
    frame.setProperty("TCard", True)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(18, 16, 18, 16)
    lay.setSpacing(10)
    if title:
        t = QLabel(title)
        t.setProperty("h2", True)
        lay.addWidget(t)
    return frame, lay


def toolbar(*widgets) -> QWidget:
    """水平工具行。"""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    for item in widgets:
        if isinstance(item, int):
            lay.addStretch(item)
        else:
            lay.addWidget(item)
    return w


def hline() -> QFrame:
    f = QFrame()
    f.setProperty("HSep", True)
    f.setFixedHeight(1)
    return f


def kv_row(key: str, value: str = "") -> tuple[QLabel, QLabel]:
    k = QLabel(key)
    k.setProperty("muted", True)
    k.setFixedWidth(110)
    v = QLabel(value)
    v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return k, v
