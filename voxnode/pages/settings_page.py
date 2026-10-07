"""设置：外观、启动与托盘、电源与安全、截图、配置数据。

每一项都真正接线生效，不做「只是存起来」的假开关：
  - 外观   → theme.set_theme() 立即换肤，导航栏图标重新染色
  - 托盘   → MainWindow 的 closeEvent / 托盘双击事件读配置
  - 安全   → ui.confirm_dangerous() 与 TaskExecutor.block_dangerous 共同把关
  - 截图   → 格式进入 core.screenshot.capture，自动清理按天数删旧图
  - 数据   → 配置导出 / 导入（导入前自动备份）
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from miiotpcapi.config import APP_DIR, CONFIG_FILE, Config
from miiotpcapi.core import autostart, screenshot

from .. import theme
from ..ui import card, hline, section

FORMAT_LABELS = [("png", "PNG（无损，体积较大）"), ("jpeg", "JPEG（有损，体积较小）")]
CLOSE_LABELS = [("tray", "最小化到系统托盘（推荐）"), ("quit", "直接退出程序")]
TRAY_LABELS = [("show", "显示 / 恢复主界面"), ("toggle_bridge", "启停小爱桥接")]


class SettingsPage(QFrame):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("settingsScroll")
        body = QWidget()
        body.setObjectName("settingsBody")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        title = QLabel("设置")
        title.setProperty("h1", True)
        lay.addWidget(title)
        sub = QLabel("所有改动即时保存并生效")
        sub.setProperty("muted", True)
        lay.addWidget(sub)

        self._build_appearance(lay)
        self._build_startup(lay)
        self._build_safety(lay)
        self._build_screenshot(lay)
        self._build_data(lay)

        about = QLabel("VoxNode © 2026 · 基于 miiotpcapi · MIT 开源")
        about.setProperty("muted", True)
        lay.addWidget(about)
        lay.addStretch(1)

    # ================================================================ 外观
    def _build_appearance(self, lay: QVBoxLayout) -> None:
        lay.addWidget(section("外观"))
        card_, body = card("配色与缩放")

        # -- 强调色 ------------------------------------------------------
        body.addWidget(QLabel("强调色"))
        row = QHBoxLayout()
        row.setSpacing(10)
        self._swatches = QButtonGroup(self)
        self._swatches.setExclusive(True)
        current = str(self.config.get("ui.accent", theme.DEFAULT_ACCENT))
        for key, (color, _, _) in theme.ACCENTS.items():
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setProperty("swatch", True)
            btn.setToolTip(theme.ACCENT_LABELS.get(key, key))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton{background:%s;border:2px solid transparent;border-radius:9px;"
                "min-width:38px;min-height:38px;max-width:38px;max-height:38px;padding:0;}"
                "QPushButton:checked{border-color:#e8eaed;}" % color
            )
            btn.setChecked(key == current)
            btn.clicked.connect(lambda _=False, k=key: self._set_accent(k))
            self._swatches.addButton(btn)
            row.addWidget(btn)
        self.accent_label = QLabel(theme.ACCENT_LABELS.get(current, current))
        self.accent_label.setProperty("muted", True)
        row.addSpacing(6)
        row.addWidget(self.accent_label)
        row.addStretch(1)
        body.addLayout(row)

        # -- 界面缩放 ----------------------------------------------------
        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(10)
        zoom_row.addWidget(QLabel("界面缩放"))
        self.cmb_scale = QComboBox()
        for step in theme.SCALE_STEPS:
            self.cmb_scale.addItem(theme.SCALE_LABELS.get(step, f"{int(step * 100)}%"), step)
        self._select_combo(self.cmb_scale, float(self.config.get("ui.scale", 1.0)))
        self.cmb_scale.currentIndexChanged.connect(
            lambda _: self._set_scale(float(self.cmb_scale.currentData())))
        self.cmb_scale.setMinimumWidth(160)
        zoom_row.addWidget(self.cmb_scale)
        zoom_row.addStretch(1)
        body.addLayout(zoom_row)

        # -- 导航栏文字 --------------------------------------------------
        self.chk_nav_labels = QCheckBox("导航栏显示文字标签（关闭后只留图标，鼠标悬停显示名称）")
        self.chk_nav_labels.setChecked(bool(self.config.get("ui.nav_labels", True)))
        self.chk_nav_labels.stateChanged.connect(self._set_nav_labels)
        body.addWidget(self.chk_nav_labels)

        tip = QLabel("提示：窗口变窄时导航栏会自动收起文字，避免按钮被挤压。")
        tip.setProperty("muted", True)
        body.addWidget(tip)
        lay.addWidget(card_)

    # ================================================================ 启动与托盘
    def _build_startup(self, lay: QVBoxLayout) -> None:
        lay.addWidget(section("启动与托盘"))
        card_, body = card("开机与最小化")

        self.chk_autostart = QCheckBox("开机自动启动（写入当前用户注册表 Run 键）")
        self.chk_autostart.setChecked(autostart.is_enabled())
        self.chk_autostart.stateChanged.connect(self._toggle_autostart)
        body.addWidget(self.chk_autostart)

        self.chk_minimized = QCheckBox("启动时最小化到系统托盘")
        self.chk_minimized.setChecked(bool(self.config.get("start_minimized", False)))
        self.chk_minimized.stateChanged.connect(
            lambda _: self.config.set("start_minimized", self.chk_minimized.isChecked()))
        body.addWidget(self.chk_minimized)

        body.addWidget(hline())

        close_row = QHBoxLayout()
        close_row.setSpacing(10)
        close_row.addWidget(QLabel("点右上角关闭按钮时"))
        self.cmb_close = QComboBox()
        for value, label in CLOSE_LABELS:
            self.cmb_close.addItem(label, value)
        self._select_combo(self.cmb_close, str(self.config.get("ui.close_action", "tray")))
        self.cmb_close.currentIndexChanged.connect(
            lambda _: self.config.set("ui.close_action", self.cmb_close.currentData()))
        self.cmb_close.setMinimumWidth(220)
        close_row.addWidget(self.cmb_close)
        close_row.addStretch(1)
        body.addLayout(close_row)

        tray_row = QHBoxLayout()
        tray_row.setSpacing(10)
        tray_row.addWidget(QLabel("双击托盘图标时"))
        self.cmb_tray = QComboBox()
        for value, label in TRAY_LABELS:
            self.cmb_tray.addItem(label, value)
        self._select_combo(self.cmb_tray, str(self.config.get("ui.tray_double_click", "show")))
        self.cmb_tray.currentIndexChanged.connect(
            lambda _: self.config.set("ui.tray_double_click", self.cmb_tray.currentData()))
        self.cmb_tray.setMinimumWidth(220)
        tray_row.addWidget(self.cmb_tray)
        tray_row.addStretch(1)
        body.addLayout(tray_row)

        self.chk_notify = QCheckBox("操作结果弹出桌面通知")
        self.chk_notify.setChecked(bool(self.config.get("ui.notifications", True)))
        self.chk_notify.stateChanged.connect(
            lambda _: self.config.set("ui.notifications", self.chk_notify.isChecked()))
        body.addWidget(self.chk_notify)

        lay.addWidget(card_)

    # ================================================================ 电源与安全
    def _build_safety(self, lay: QVBoxLayout) -> None:
        lay.addWidget(section("电源与安全"))
        card_, body = card("危险操作策略")

        delay_row = QHBoxLayout()
        delay_row.setSpacing(10)
        delay_row.addWidget(QLabel("默认关机 / 重启延时"))
        self.spn_delay = QSpinBox()
        self.spn_delay.setRange(0, 3600)
        self.spn_delay.setSuffix(" 秒")
        self.spn_delay.setValue(int(self.config.get("power.default_delay", 60)))
        self.spn_delay.setMinimumWidth(120)
        self.spn_delay.valueChanged.connect(self._set_default_delay)
        delay_row.addWidget(self.spn_delay)
        delay_row.addStretch(1)
        body.addLayout(delay_row)

        hint = QLabel("这个延时同时用于语音「关机 / 重启」指令，改完立即生效。")
        hint.setProperty("muted", True)
        body.addWidget(hint)

        body.addWidget(hline())

        self.chk_confirm = QCheckBox("危险操作（关机 / 重启 / 休眠 / 注销 / 睡眠）执行前二次确认")
        self.chk_confirm.setChecked(bool(self.config.get("safety.confirm_dangerous", True)))
        self.chk_confirm.stateChanged.connect(self._set_confirm)
        body.addWidget(self.chk_confirm)

        self.chk_block = QCheckBox("禁止一切危险操作（语音、米家、遥控台、手机 App 都会被拦下）")
        self.chk_block.setChecked(bool(self.config.get("safety.block_dangerous", False)))
        self.chk_block.stateChanged.connect(self._set_block)
        body.addWidget(self.chk_block)

        warn = QLabel("开启「禁止危险操作」后，仍可正常截屏、查状态、放音乐、开关机箱灯之外的日常操作。")
        warn.setProperty("muted", True)
        warn.setWordWrap(True)
        body.addWidget(warn)
        lay.addWidget(card_)

    # ================================================================ 截图
    def _build_screenshot(self, lay: QVBoxLayout) -> None:
        lay.addWidget(section("截图"))
        card_, body = card("保存与清理")

        row = QHBoxLayout()
        self.dir_label = QLabel(self.config.get("screenshot_dir", ""))
        self.dir_label.setProperty("muted", True)
        btn_dir = QPushButton("更改目录…")
        btn_dir.clicked.connect(self._choose_dir)
        btn_open = QPushButton("打开目录")
        btn_open.clicked.connect(self._open_dir)
        row.addWidget(self.dir_label, 1)
        row.addWidget(btn_dir)
        row.addWidget(btn_open)
        body.addLayout(row)

        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(10)
        fmt_row.addWidget(QLabel("图片格式"))
        self.cmb_format = QComboBox()
        for value, label in FORMAT_LABELS:
            self.cmb_format.addItem(label, value)
        self._select_combo(self.cmb_format, str(self.config.get("screenshot.format", "png")))
        self.cmb_format.currentIndexChanged.connect(
            lambda _: self.config.set("screenshot.format", self.cmb_format.currentData()))
        self.cmb_format.setMinimumWidth(220)
        fmt_row.addWidget(self.cmb_format)
        fmt_row.addStretch(1)
        body.addLayout(fmt_row)

        clean_row = QHBoxLayout()
        clean_row.setSpacing(10)
        clean_row.addWidget(QLabel("自动清理"))
        self.spn_clean = QSpinBox()
        self.spn_clean.setRange(0, 3650)
        self.spn_clean.setSuffix(" 天前的截图")
        self.spn_clean.setSpecialValueText("不自动清理")
        self.spn_clean.setValue(int(self.config.get("screenshot.auto_clean_days", 0)))
        self.spn_clean.setMinimumWidth(180)
        self.spn_clean.valueChanged.connect(
            lambda v: self.config.set("screenshot.auto_clean_days", int(v)))
        btn_clean = QPushButton("立即清理一次")
        btn_clean.clicked.connect(self._clean_now)
        clean_row.addWidget(self.spn_clean)
        clean_row.addWidget(btn_clean)
        clean_row.addStretch(1)
        body.addLayout(clean_row)

        lay.addWidget(card_)

    # ================================================================ 数据
    def _build_data(self, lay: QVBoxLayout) -> None:
        lay.addWidget(section("配置与数据"))
        card_, body = card("配置文件")

        path_label = QLabel(f"配置文件：{CONFIG_FILE}")
        path_label.setProperty("muted", True)
        path_label.setWordWrap(True)
        body.addWidget(path_label)

        btn_cfg_dir = QPushButton("打开配置文件夹")
        btn_cfg_dir.clicked.connect(self._open_cfg_dir)
        btn_export = QPushButton("导出配置…")
        btn_export.clicked.connect(self._export)
        btn_import = QPushButton("导入配置…")
        btn_import.clicked.connect(self._import)
        btn_reset = QPushButton("重置全部配置")
        btn_reset.setProperty("kind", "danger")
        btn_reset.clicked.connect(self._reset)

        row = QHBoxLayout()
        row.addWidget(btn_cfg_dir)
        row.addWidget(btn_export)
        row.addWidget(btn_import)
        row.addStretch(1)
        row.addWidget(btn_reset)
        body.addLayout(row)

        note = QLabel("导入配置前会自动备份一份到 config.json.bak；导入后界面会按新配置重新载入。")
        note.setProperty("muted", True)
        note.setWordWrap(True)
        body.addWidget(note)
        lay.addWidget(card_)

    # ================================================================ 工具
    @staticmethod
    def _select_combo(combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        if idx < 0:
            idx = 0
        combo.blockSignals(True)
        combo.setCurrentIndex(idx)
        combo.blockSignals(False)

    # ================================================================ 外观动作
    def _set_accent(self, key: str) -> None:
        self.config.set("ui.accent", key)
        self.accent_label.setText(theme.ACCENT_LABELS.get(key, key))
        theme.set_theme(accent=key)

    def _set_scale(self, scale: float) -> None:
        self.config.set("ui.scale", float(scale))
        theme.set_theme(scale=float(scale))

    def _set_nav_labels(self, state: int) -> None:
        on = bool(state)
        self.config.set("ui.nav_labels", on)
        win = self.window()
        nav = getattr(win, "nav", None)
        if nav is not None and hasattr(nav, "set_labels_enabled"):
            nav.set_labels_enabled(on)

    def sync_theme_controls(self) -> None:
        """主题被外部改动后（如导入配置）同步这里控件的显示。"""
        current = theme.current_accent()
        buttons = self._swatches.buttons()
        keys = list(theme.ACCENTS.keys())
        for i, btn in enumerate(buttons):
            if i < len(keys):
                btn.setChecked(keys[i] == current)
        self.accent_label.setText(theme.ACCENT_LABELS.get(current, current))
        self._select_combo(self.cmb_scale, theme.current_scale())

    # ================================================================ 启动动作
    def _toggle_autostart(self, state: int) -> None:
        try:
            if state:
                autostart.enable()
            else:
                autostart.disable()
            self.config.set("autostart", bool(state))
        except Exception as e:
            QMessageBox.critical(self, "操作失败", str(e))
            self.chk_autostart.setCheckState(Qt.CheckState.Unchecked)

    # ================================================================ 安全动作
    def _set_default_delay(self, value: int) -> None:
        self.config.set("power.default_delay", int(value))
        # 语音指令里的延迟也要跟着变，否则两边说法不一致
        tasks = self.config.get("tasks", [])
        touched = False
        for t in tasks:
            if t.get("action") in ("shutdown", "restart") and isinstance(t.get("params"), dict):
                t["params"]["delay"] = int(value)
                touched = True
        if touched:
            self.config.set("tasks", tasks)

    def _set_confirm(self, state: int) -> None:
        self.config.set("safety.confirm_dangerous", bool(state))

    def _set_block(self, state: int) -> None:
        on = bool(state)
        if on:
            ret = QMessageBox.warning(
                self, "确认开启",
                "开启后，关机 / 重启 / 休眠 / 注销 / 睡眠将在所有入口失效。\n确定要禁止吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                self.chk_block.setCheckState(Qt.CheckState.Unchecked)
                return
        self.config.set("safety.block_dangerous", on)

    # ================================================================ 截图动作
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

    def _clean_now(self) -> None:
        days = int(self.spn_clean.value())
        if days <= 0:
            QMessageBox.information(self, "提示", "当前是「不自动清理」，请先设置天数。")
            return
        n = screenshot.cleanup(self.config.get("screenshot_dir", ""), days)
        QMessageBox.information(self, "完成", f"已清理 {n} 个超过 {days} 天的截图。")

    # ================================================================ 数据动作
    def _open_cfg_dir(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(APP_DIR))  # noqa: S606

    def _export(self) -> None:
        self.config.save()
        target, _ = QFileDialog.getSaveFileName(
            self, "导出配置", str(Path.home() / "voxnode-config.json"), "JSON (*.json)")
        if not target:
            return
        try:
            shutil.copyfile(CONFIG_FILE, target)
        except OSError as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return
        QMessageBox.information(self, "完成", f"已导出到：\n{target}")

    def _import(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self, "导入配置", str(Path.home()), "JSON (*.json)")
        if not source:
            return
        try:
            raw = json.loads(Path(source).read_text("utf-8"))
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"不是合法的 JSON：{e}")
            return
        if not isinstance(raw, dict):
            QMessageBox.critical(self, "导入失败", "配置文件的顶层必须是对象")
            return
        ret = QMessageBox.question(
            self, "确认导入",
            "导入会覆盖当前全部配置（账号凭据、指令规则、外观等）。\n"
            "原配置会备份为 config.json.bak，确定继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        try:
            if CONFIG_FILE.exists():
                shutil.copyfile(CONFIG_FILE, CONFIG_FILE.with_suffix(".json.bak"))
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(
                json.dumps(raw, ensure_ascii=False, indent=2), "utf-8")
        except OSError as e:
            QMessageBox.critical(self, "导入失败", str(e))
            return
        self.config.load()
        self.reload_from_config()
        QMessageBox.information(self, "完成", "配置已导入并重新载入。建议重启程序以确保全部生效。")

    def reload_from_config(self) -> None:
        """把配置里的值重新灌回各控件（导入配置后调用）。"""
        self.sync_theme_controls()
        self.chk_nav_labels.setChecked(bool(self.config.get("ui.nav_labels", True)))
        self.chk_minimized.setChecked(bool(self.config.get("start_minimized", False)))
        self.chk_notify.setChecked(bool(self.config.get("ui.notifications", True)))
        self.chk_confirm.setChecked(bool(self.config.get("safety.confirm_dangerous", True)))
        self.chk_block.setChecked(bool(self.config.get("safety.block_dangerous", False)))
        self.spn_delay.setValue(int(self.config.get("power.default_delay", 60)))
        self.spn_clean.setValue(int(self.config.get("screenshot.auto_clean_days", 0)))
        self.dir_label.setText(self.config.get("screenshot_dir", ""))
        self._select_combo(self.cmb_close, str(self.config.get("ui.close_action", "tray")))
        self._select_combo(self.cmb_tray, str(self.config.get("ui.tray_double_click", "show")))
        self._select_combo(self.cmb_format, str(self.config.get("screenshot.format", "png")))
        theme.set_theme(accent=str(self.config.get("ui.accent", theme.DEFAULT_ACCENT)),
                        scale=float(self.config.get("ui.scale", 1.0)))

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
        self.reload_from_config()
        QMessageBox.information(self, "完成", "已重置，重启应用后生效。")
