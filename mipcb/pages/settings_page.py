"""设置：开机自启、启动方式、截图目录、配置文件管理。"""
from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
)

from miiotpcapi.config import APP_DIR, CONFIG_FILE, Config
from miiotpcapi.core import autostart

from ..ui import card, page


class SettingsPage(QFrame):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        _, lay = page("设置", None, root=self)

        boot_card, boot_lay = card("启动")
        self.chk_autostart = QCheckBox("开机自动启动（写入当前用户注册表 Run 键）")
        self.chk_autostart.setChecked(autostart.is_enabled())
        self.chk_autostart.stateChanged.connect(self._toggle_autostart)
        self.chk_minimized = QCheckBox("启动时最小化到系统托盘")
        self.chk_minimized.setChecked(bool(config.get("start_minimized", False)))
        self.chk_minimized.stateChanged.connect(
            lambda _: config.set("start_minimized", self.chk_minimized.isChecked()))
        boot_lay.addWidget(self.chk_autostart)
        boot_lay.addWidget(self.chk_minimized)
        lay.addWidget(boot_card)

        shot_card, shot_lay = card("截图")
        row = QHBoxLayout()
        self.dir_label = QLabel(config.get("screenshot_dir", ""))
        btn_dir = QPushButton("更改目录…")
        btn_dir.clicked.connect(self._choose_dir)
        btn_open = QPushButton("打开目录")
        btn_open.clicked.connect(self._open_dir)
        row.addWidget(self.dir_label, 1)
        row.addWidget(btn_dir)
        row.addWidget(btn_open)
        shot_lay.addLayout(row)
        lay.addWidget(shot_card)

        cfg_card, cfg_lay = card("配置与数据")
        cfg_lay.addWidget(QLabel(f"配置文件：{CONFIG_FILE}"))
        btn_cfg_dir = QPushButton("打开配置文件夹")
        btn_cfg_dir.clicked.connect(self._open_cfg_dir)
        btn_reset = QPushButton("重置全部配置")
        btn_reset.setProperty("kind", "danger")
        btn_reset.clicked.connect(self._reset)
        row2 = QHBoxLayout()
        row2.addWidget(btn_cfg_dir)
        row2.addStretch(1)
        row2.addWidget(btn_reset)
        cfg_lay.addLayout(row2)
        lay.addWidget(cfg_card)

        about = QLabel("MiPC Bridge © 2026 · 基于 miiotpcapi · MIT 开源")
        about.setProperty("muted", True)
        lay.addWidget(about)
        lay.addStretch(1)

    def _toggle_autostart(self, state: int) -> None:
        try:
            if state:
                autostart.enable()
            else:
                autostart.disable()
        except Exception as e:
            QMessageBox.critical(self, "操作失败", str(e))
            self.chk_autostart.setCheckState(Qt.CheckState.Unchecked)

    def _choose_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择截图保存目录",
                                                self.config.get("screenshot_dir", ""))
        if path:
            self.config.set("screenshot_dir", path)
            self.dir_label.setText(path)

    def _open_dir(self) -> None:
        d = self.config.get("screenshot_dir", "")
        Path(d).mkdir(parents=True, exist_ok=True)
        os.startfile(d)  # noqa: S606

    def _open_cfg_dir(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(APP_DIR))  # noqa: S606

    def _reset(self) -> None:
        ret = QMessageBox.warning(
            self, "确认重置",
            "将清空所有配置（账号凭据、指令规则、应用列表等），确定继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self.config.reset()
        QMessageBox.information(self, "完成", "已重置，重启应用后生效。")
