"""屏幕截取：全屏 / 指定显示器截图，预览与历史列表。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QVBoxLayout,
)

from miiotpcapi.config import Config
from miiotpcapi.core import screenshot

from ..ui import card, page


class ScreenshotPage(QFrame):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._current_path: str = ""
        _, lay = page("屏幕截取", "对小爱说「截屏」即可保存到图片文件夹", root=self)

        top_card, top_lay = card("截取")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.monitor_combo = QComboBox()
        self.monitor_combo.setMinimumWidth(160)
        btn_shot = QPushButton("截图")
        btn_shot.setProperty("kind", "primary")
        btn_shot.clicked.connect(self._shot)
        self.btn_folder = QPushButton("打开保存文件夹")
        self.btn_folder.clicked.connect(self._open_folder)
        row.addWidget(QLabel("目标"))
        row.addWidget(self.monitor_combo)
        row.addWidget(btn_shot)
        row.addWidget(self.btn_folder)
        row.addStretch(1)
        self.path_label = QLabel("保存位置：")
        self.path_label.setProperty("muted", True)
        top_lay.addLayout(row)
        top_lay.addWidget(self.path_label)
        lay.addWidget(top_card)

        preview_card, preview_lay = card("预览")
        self.preview = QLabel("（点击右侧历史记录查看）")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(320)
        self.preview.setStyleSheet("border: 1px dashed #2e333d; border-radius: 10px;")
        preview_lay.addWidget(self.preview)
        lay.addWidget(preview_card, 1)

        history_card, history_lay = card("最近截图")
        self.history = QListWidget()
        self.history.itemClicked.connect(self._show_preview)
        history_lay.addWidget(self.history)
        lay.addWidget(history_card, 1)

        self._refresh()

    def on_shown(self) -> None:
        self._refresh()

    # ----------------------------------------------------------------------
    def _refresh(self) -> None:
        save_dir = self.config.get("screenshot_dir", "")
        self.path_label.setText(f"保存位置：{save_dir}")
        try:
            monitors = screenshot.list_monitors()
        except Exception:
            monitors = []
        self.monitor_combo.clear()
        self.monitor_combo.addItem("全屏", -1)
        for i in range(1, len(monitors)):
            m = monitors[i]
            self.monitor_combo.addItem(f"显示器 {i}（{m['width']}x{m['height']}）", i)

        self.history.clear()
        for p in screenshot.recent(save_dir, 20):
            item = QListWidgetItem(p.name)
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            self.history.addItem(item)

    def _shot(self) -> None:
        monitor = self.monitor_combo.currentData()
        save_dir = self.config.get("screenshot_dir", "")
        fmt = str(self.config.get("screenshot.format", "png"))
        try:
            path = screenshot.capture(save_dir, monitor if monitor is not None else -1, fmt=fmt)
        except Exception as e:
            QMessageBox.critical(self, "截图失败", str(e))
            return
        self._current_path = str(path)
        self._show_path(str(path))
        self._refresh()

    def _show_preview(self, item) -> None:
        self._show_path(item.data(Qt.ItemDataRole.UserRole))

    def _show_path(self, path: str) -> None:
        pm = QPixmap(path)
        if pm.isNull():
            return
        scaled = pm.scaled(
            self.preview.width() - 20, self.preview.height() - 20,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self.preview.setPixmap(scaled)

    def _open_folder(self) -> None:
        save_dir = self.config.get("screenshot_dir", "")
        Path(save_dir).mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(save_dir)  # noqa: S606
