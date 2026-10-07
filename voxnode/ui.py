"""页面通用构件：标准页头、卡片容器、工具行，以及危险操作的安全策略。"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QVBoxLayout, QWidget,
)


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


def section(title: str) -> QLabel:
    """分组小标题（设置页用来切分多组配置）。"""
    lab = QLabel(title)
    lab.setProperty("kicker", True)
    return lab


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


# ---------------------------------------------------------------- 危险操作策略
def dangerous_blocked(parent: QWidget, config) -> bool:
    """危险操作总开关打开时给出提示并返回 True（调用方应直接 return）。"""
    if config is not None and bool(config.get("safety.block_dangerous", False)):
        QMessageBox.information(
            parent, "已被禁止",
            "危险操作已在「设置 → 电源与安全」中被禁止。\n"
            "如需执行，请先到设置里关掉「禁止危险操作」。",
        )
        return True
    return False


def confirm_dangerous(parent: QWidget, name: str, config=None,
                      extra: str = "") -> bool:
    """危险操作二次确认；设置里关掉确认时直接放行。"""
    if config is not None and not bool(config.get("safety.confirm_dangerous", True)):
        return True
    ret = QMessageBox.warning(
        parent, "确认操作",
        f"确定要「{name}」{extra}吗？",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return ret == QMessageBox.StandardButton.Yes
