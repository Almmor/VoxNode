"""深色主题：Fusion + QSS，小米橙点缀。"""
from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

C = {
    "bg": "#14161a",
    "panel": "#1d2026",
    "card": "#22262e",
    "card_hover": "#282d36",
    "border": "#2e333d",
    "text": "#e8eaed",
    "muted": "#9aa0aa",
    "accent": "#ff6900",
    "accent_hover": "#ff8534",
    "accent_pressed": "#e65c00",
    "danger": "#e5484d",
    "ok": "#46c46c",
    "warn": "#f5a623",
    "selection": "#3a2c1a",
}

QSS = f"""
* {{
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
    color: {C["text"]};
    outline: none;
}}
QMainWindow, QDialog, QWizard {{
    background: {C["bg"]};
}}
QLabel {{
    color: {C["text"]};
    background: transparent;
}}
QLabel[muted="true"] {{ color: {C["muted"]}; }}
QLabel[accent="true"] {{ color: {C["accent"]}; font-weight: 600; }}
QLabel[h1="true"] {{ font-size: 22px; font-weight: 700; }}
QLabel[h2="true"] {{ font-size: 16px; font-weight: 600; }}

QWidget#sidebar {{
    background: {C["panel"]};
    border-right: 1px solid {C["border"]};
}}
QListWidget#navList {{
    background: transparent;
    border: none;
    padding: 8px 6px;
    font-size: 14px;
}}
QListWidget#navList::item {{
    padding: 12px 16px;
    border-radius: 8px;
    margin: 2px 8px;
    color: {C["muted"]};
}}
QListWidget#navList::item:selected {{
    background: {C["selection"]};
    color: {C["accent"]};
    font-weight: 600;
}}
QListWidget#navList::item:hover {{
    background: {C["card"]};
}}

QFrame.card, QFrame[TCard="true"] {{
    background: {C["card"]};
    border: 1px solid {C["border"]};
    border-radius: 12px;
}}
QFrame[HSep="true"] {{
    background: {C["border"]};
    max-height: 1px;
    border: none;
}}

QPushButton {{
    background: {C["card"]};
    border: 1px solid {C["border"]};
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 500;
}}
QPushButton:hover {{ background: {C["card_hover"]}; }}
QPushButton:pressed {{ background: {C["panel"]}; }}
QPushButton:disabled {{ color: {C["muted"]}; background: {C["panel"]}; }}

QPushButton[kind="primary"] {{
    background: {C["accent"]};
    border: none;
    color: #ffffff;
    font-weight: 600;
}}
QPushButton[kind="primary"]:hover {{ background: {C["accent_hover"]}; }}
QPushButton[kind="primary"]:pressed {{ background: {C["accent_pressed"]}; }}
QPushButton[kind="primary"]:disabled {{ background: #6b4a2a; color: #cbb9a8; }}

QPushButton[kind="danger"] {{
    background: transparent;
    border: 1px solid {C["danger"]};
    color: {C["danger"]};
    font-weight: 600;
}}
QPushButton[kind="danger"]:hover {{ background: {C["danger"]}; color: #ffffff; }}

QPushButton[kind="ghost"] {{
    background: transparent;
    border: 1px solid {C["border"]};
    color: {C["muted"]};
}}
QPushButton[kind="ghost"]:hover {{ color: {C["text"]}; border-color: {C["muted"]}; }}

QLineEdit, QSpinBox, QTimeEdit, QComboBox {{
    background: {C["panel"]};
    border: 1px solid {C["border"]};
    border-radius: 8px;
    padding: 7px 10px;
    selection-background-color: {C["accent"]};
}}
QLineEdit:focus, QSpinBox:focus, QTimeEdit:focus, QComboBox:focus {{
    border-color: {C["accent"]};
}}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {C["panel"]};
    border: 1px solid {C["border"]};
    selection-background-color: {C["selection"]};
}}

QTableWidget {{
    background: {C["card"]};
    alternate-background-color: {C["card_hover"]};
    border: 1px solid {C["border"]};
    border-radius: 10px;
    gridline-color: {C["border"]};
}}
QHeaderView::section {{
    background: {C["panel"]};
    color: {C["muted"]};
    border: none;
    border-bottom: 1px solid {C["border"]};
    padding: 8px 10px;
    font-weight: 600;
}}
QTableWidget::item {{ padding: 6px 8px; }}
QTableWidget::item:selected {{ background: {C["selection"]}; color: {C["accent"]}; }}

QListWidget {{
    background: {C["card"]};
    border: 1px solid {C["border"]};
    border-radius: 10px;
}}
QListWidget::item {{ padding: 8px 10px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {C["selection"]}; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 17px; height: 17px;
    border-radius: 5px;
    border: 1px solid {C["border"]};
    background: {C["panel"]};
}}
QCheckBox::indicator:checked {{
    background: {C["accent"]};
    border-color: {C["accent"]};
}}

QProgressBar {{
    background: {C["panel"]};
    border: none;
    border-radius: 5px;
    height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {C["accent"]}; border-radius: 5px; }}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C["border"]};
    border-radius: 5px;
    min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{ background: {C["muted"]}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {C["border"]};
    border-radius: 5px;
    min-width: 40px;
}}

QToolTip {{
    background: {C["panel"]};
    color: {C["text"]};
    border: 1px solid {C["border"]};
    padding: 6px;
}}

QWizard {{
    background: {C["bg"]};
}}
QWizard QWizardPage {{
    background: {C["bg"]};
}}
QWizard QLabel {{
    color: {C["text"]};
}}
QWizard QPushButton {{
    background: {C["card"]};
    border: 1px solid {C["border"]};
    border-radius: 8px;
    padding: 8px 20px;
    min-width: 90px;
}}
QWizard QPushButton:hover {{ background: {C["card_hover"]}; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(C["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(C["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(C["panel"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(C["card"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(C["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(C["card"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(C["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(C["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(C["muted"]))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(C["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(QSS)
