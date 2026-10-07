"""深色主题：Fusion + 动态 QSS。

支持两件以前写死的事：
  1. **强调色**可在「设置 → 外观」里切换（橙 / 蓝 / 绿 / 紫 / 品红），
     选中态底色由强调色与面板色混合算出，不需要为每种颜色单独配色表。
  2. **界面缩放**按比例作用于字号与控件高度，适配高 DPI 或偏好大字号的用户。

换主题走 `set_theme()` 单一入口：重建调色板 → 应用 QSS → 通过 `theme_bus.changed`
通知界面刷新（导航栏图标需要重新染色）。
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

# 强调色预设： (主色, 悬停, 按下)
ACCENTS: dict[str, tuple[str, str, str]] = {
    "orange": ("#ff6900", "#ff8534", "#e65c00"),
    "blue": ("#2f7df6", "#4d92f8", "#1f6ae0"),
    "green": ("#2fbf71", "#45cf83", "#25a860"),
    "violet": ("#8b5cf6", "#9d78f7", "#7746e8"),
    "magenta": ("#e0409a", "#ea5cad", "#c72f86"),
}

ACCENT_LABELS: dict[str, str] = {
    "orange": "科技橙",
    "blue": "深海蓝",
    "green": "青草绿",
    "violet": "紫罗兰",
    "magenta": "品红",
}

# 界面缩放档位（仅影响字号与控件高度，不改窗口尺寸）
SCALE_STEPS: list[float] = [0.9, 1.0, 1.1, 1.25]
SCALE_LABELS: dict[float, str] = {
    0.9: "紧凑 90%",
    1.0: "标准 100%",
    1.1: "较大 110%",
    1.25: "特大 125%",
}

DEFAULT_ACCENT = "orange"
DEFAULT_SCALE = 1.0

# 与强调色无关的基础配色
BASE: dict[str, str] = {
    "bg": "#14161a",
    "panel": "#1d2026",
    "card": "#22262e",
    "card_hover": "#282d36",
    "border": "#2e333d",
    "text": "#e8eaed",
    "muted": "#9aa0aa",
    "danger": "#e5484d",
    "ok": "#46c46c",
    "warn": "#f5a623",
}

# 向后兼容：默认（橙色）调色板
C: dict[str, str] = {**BASE, "accent": ACCENTS[DEFAULT_ACCENT][0]}


def _mix(fg: str, bg: str, t: float) -> str:
    """把 fg 按比例 t 混进 bg，用于从强调色推导选中态底色。"""
    try:
        f, b = QColor(fg), QColor(bg)
    except Exception:
        return bg
    ch = lambda a, c: round(a * t + c * (1 - t))  # noqa: E731
    return QColor(ch(f.red(), b.red()), ch(f.green(), b.green()),
                  ch(f.blue(), b.blue())).name()


def make_palette(accent: str = DEFAULT_ACCENT) -> dict[str, str]:
    """按强调色生成整套调色板。未知名称回退到默认色，不抛异常。"""
    key = accent if accent in ACCENTS else DEFAULT_ACCENT
    a, ah, ap = ACCENTS[key]
    c = dict(BASE)
    c["accent"] = a
    c["accent_hover"] = ah
    c["accent_pressed"] = ap
    # 选中态：强调色压暗后作底，文字用强调色，保证对比度
    c["selection"] = _mix(a, c["panel"], 0.22)
    c["accent_soft"] = _mix(a, c["panel"], 0.13)
    c["accent_key"] = key
    return c


def build_qss(c: dict[str, str], scale: float = 1.0) -> str:
    """生成 QSS。scale 只作用于字号与控件高度。"""
    s = scale if scale and scale > 0 else 1.0

    def u(v: float) -> str:
        return f"{round(v * s)}px"

    return f"""
* {{
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: {u(13)};
    color: {c["text"]};
    outline: none;
}}
QMainWindow, QDialog, QWizard {{
    background: {c["bg"]};
}}
QLabel {{
    color: {c["text"]};
    background: transparent;
}}
QLabel[muted="true"] {{ color: {c["muted"]}; }}
QLabel[accent="true"] {{ color: {c["accent"]}; font-weight: 600; }}
QLabel[h1="true"] {{ font-size: {u(22)}; font-weight: 700; }}
QLabel[h2="true"] {{ font-size: {u(16)}; font-weight: 600; }}
QLabel[kicker="true"] {{
    color: {c["muted"]};
    font-size: {u(11)};
    font-weight: 600;
    letter-spacing: 1px;
}}

/* ---- 顶部自定义导航栏 ---- */
QWidget#topNav {{
    background: {c["panel"]};
    border-bottom: 1px solid {c["border"]};
}}
QLabel#brandName {{
    font-size: {u(17)};
    font-weight: 700;
    color: {c["text"]};
}}
QLabel#brandSub {{
    font-size: {u(10)};
    color: {c["muted"]};
    letter-spacing: 2px;
}}
QWidget#navStatus {{
    background: {c["card"]};
    border: 1px solid {c["border"]};
    border-radius: {u(11)};
}}
QLabel#navStatusText {{
    font-size: {u(11)};
    color: {c["muted"]};
}}
QWidget#pageHeader {{
    background: transparent;
}}
QFrame#navDivider {{
    background: {c["border"]};
    border: none;
}}
QScrollArea#settingsScroll {{
    background: transparent;
    border: none;
}}
QScrollArea#settingsScroll > QWidget > QWidget {{
    background: transparent;
}}

QFrame.card, QFrame[TCard="true"] {{
    background: {c["card"]};
    border: 1px solid {c["border"]};
    border-radius: {u(12)};
}}
QFrame[HSep="true"] {{
    background: {c["border"]};
    max-height: 1px;
    border: none;
}}

QPushButton {{
    background: {c["card"]};
    border: 1px solid {c["border"]};
    border-radius: {u(8)};
    padding: {u(8)} {u(18)};
    font-weight: 500;
}}
QPushButton:hover {{ background: {c["card_hover"]}; }}
QPushButton:pressed {{ background: {c["panel"]}; }}
QPushButton:disabled {{ color: {c["muted"]}; background: {c["panel"]}; }}

QPushButton[kind="primary"] {{
    background: {c["accent"]};
    border: none;
    color: #ffffff;
    font-weight: 600;
}}
QPushButton[kind="primary"]:hover {{ background: {c["accent_hover"]}; }}
QPushButton[kind="primary"]:pressed {{ background: {c["accent_pressed"]}; }}
QPushButton[kind="primary"]:disabled {{ background: #6b4a2a; color: #cbb9a8; }}

QPushButton[kind="danger"] {{
    background: transparent;
    border: 1px solid {c["danger"]};
    color: {c["danger"]};
    font-weight: 600;
}}
QPushButton[kind="danger"]:hover {{ background: {c["danger"]}; color: #ffffff; }}
QPushButton[kind="danger"]:disabled {{
    border-color: {c["border"]};
    color: {c["muted"]};
    background: {c["panel"]};
}}

QPushButton[kind="ghost"] {{
    background: transparent;
    border: 1px solid {c["border"]};
    color: {c["muted"]};
}}
QPushButton[kind="ghost"]:hover {{ color: {c["text"]}; border-color: {c["muted"]}; }}

/* 强调色色板按钮（设置 → 外观） */
QPushButton[swatch="true"] {{
    border-radius: {u(9)};
    border: 2px solid transparent;
    min-width: {u(38)};
    min-height: {u(38)};
    max-width: {u(38)};
    max-height: {u(38)};
    padding: 0;
}}
QPushButton[swatch="true"]:checked {{
    border-color: {c["text"]};
}}

QLineEdit, QSpinBox, QTimeEdit, QComboBox {{
    background: {c["panel"]};
    border: 1px solid {c["border"]};
    border-radius: {u(8)};
    padding: {u(7)} {u(10)};
    selection-background-color: {c["accent"]};
}}
QLineEdit:focus, QSpinBox:focus, QTimeEdit:focus, QComboBox:focus {{
    border-color: {c["accent"]};
}}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {c["panel"]};
    border: 1px solid {c["border"]};
    selection-background-color: {c["selection"]};
}}

QTableWidget {{
    background: {c["card"]};
    alternate-background-color: {c["card_hover"]};
    border: 1px solid {c["border"]};
    border-radius: 10px;
    gridline-color: {c["border"]};
}}
QHeaderView::section {{
    background: {c["panel"]};
    color: {c["muted"]};
    border: none;
    border-bottom: 1px solid {c["border"]};
    padding: {u(8)} {u(10)};
    font-weight: 600;
}}
QTableWidget::item {{ padding: 6px 8px; }}
QTableWidget::item:selected {{ background: {c["selection"]}; color: {c["accent"]}; }}

QListWidget {{
    background: {c["card"]};
    border: 1px solid {c["border"]};
    border-radius: 10px;
}}
QListWidget::item {{ padding: 8px 10px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {c["selection"]}; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: {u(17)}; height: {u(17)};
    border-radius: 5px;
    border: 1px solid {c["border"]};
    background: {c["panel"]};
}}
QCheckBox::indicator:checked {{
    background: {c["accent"]};
    border-color: {c["accent"]};
}}

QProgressBar {{
    background: {c["panel"]};
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {c["accent"]}; border-radius: 5px; }}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c["border"]};
    border-radius: 5px;
    min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{ background: {c["muted"]}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {c["border"]};
    border-radius: 5px;
    min-width: 40px;
}}

QToolTip {{
    background: {c["panel"]};
    color: {c["text"]};
    border: 1px solid {c["border"]};
    padding: 6px;
}}

QWizard {{
    background: {c["bg"]};
}}
QWizard QWizardPage {{
    background: {c["bg"]};
}}
QWizard QLabel {{
    color: {c["text"]};
}}
QWizard QPushButton {{
    background: {c["card"]};
    border: 1px solid {c["border"]};
    border-radius: 8px;
    padding: 8px 20px;
    min-width: 90px;
}}
QWizard QPushButton:hover {{ background: {c["card_hover"]}; }}
"""


class _ThemeBus(QObject):
    """主题变更广播：导航栏等需要重新染色的控件订阅它。"""

    changed = pyqtSignal(dict)


theme_bus = _ThemeBus()

_state: dict = {"accent": DEFAULT_ACCENT, "scale": DEFAULT_SCALE, "palette": make_palette()}


def current_palette() -> dict[str, str]:
    return dict(_state["palette"])


def current_accent() -> str:
    return str(_state["accent"])


def current_scale() -> float:
    return float(_state["scale"])


def apply_palette(app: QApplication, c: dict[str, str], scale: float) -> None:
    """把调色板写进 Fusion 调色板与样式表。"""
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(c["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(c["panel"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(c["card"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(c["card"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(c["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(c["muted"]))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(c["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(build_qss(c, scale))


def apply_theme(app: QApplication, accent: str = DEFAULT_ACCENT,
                scale: float = DEFAULT_SCALE) -> dict[str, str]:
    """首次应用主题（app.run 与自检用）。"""
    app.setStyle("Fusion")
    c = make_palette(accent)
    _state.update({"accent": accent if accent in ACCENTS else DEFAULT_ACCENT,
                   "scale": scale, "palette": c})
    apply_palette(app, c, scale)
    return c


def set_theme(accent: str | None = None, scale: float | None = None) -> dict[str, str]:
    """运行时换肤：应用并广播，导航栏据此重新染色图标。"""
    app = QApplication.instance()
    if app is None:
        return current_palette()
    if accent is not None:
        _state["accent"] = accent if accent in ACCENTS else DEFAULT_ACCENT
    if scale is not None and scale > 0:
        _state["scale"] = scale
    c = make_palette(_state["accent"])
    _state["palette"] = c
    apply_palette(app, c, float(_state["scale"]))
    theme_bus.changed.emit(dict(c))
    return c
