"""首次引导式部署向导。

流程：欢迎与环境自检 → 登录小米账号（扫码 / 密码）→ 选择音箱 →
语音指令预览 → 完成设置（开机自启 / 最小化启动 / 立即启动）。
"""
from __future__ import annotations

import platform
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWizard, QWizardPage,
)

from miiotpcapi import APP_NAME, APP_NAME_ZH, __version__
from miiotpcapi.config import Config, DEFAULT_TASKS, TOKEN_FILE
from miiotpcapi.core import autostart
from miiotpcapi.secure import load_password
from miiotpcapi.xiaomi.account import MiAccount
from miiotpcapi.xiaomi.mina import MiNA

from .login import LoginDialog
from .ui import card
from .workers import run_async


class WelcomePage(QWizardPage):
    def __init__(self):
        super().__init__()
        self.setTitle(f"欢迎使用 {APP_NAME} — {APP_NAME_ZH}")
        lay = QVBoxLayout(self)
        intro = QLabel(
            "这是一款把你的电脑接入小米生态的开源工具：\n\n"
            "· 对小爱音箱说「关机」「截屏」「打开浏览器」即可控制电脑\n"
            "· 本地图形界面：电源控制、截屏、进程管理、系统监控、WOL 唤醒\n\n"
            "接下来会引导你完成部署，全程约 2 分钟。"
        )
        intro.setWordWrap(True)
        lay.addWidget(intro)
        check_card, check_lay = card("环境自检")
        self.result_table = QTableWidget(0, 2)
        self.result_table.setHorizontalHeaderLabels(["检查项", "结果"])
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.setMaximumHeight(180)
        check_lay.addWidget(self.result_table)
        lay.addWidget(check_card)
        lay.addStretch(1)
        self._run_checks()

    def _run_checks(self) -> None:
        checks: list[tuple[str, str, bool]] = []

        v = sys.version_info
        ok = v >= (3, 10)
        checks.append(("Python 版本", f"{v.major}.{v.minor}.{v.micro}" + ("" if ok else "（需要 3.10+）"), ok))

        try:
            import PyQt6  # noqa: F401
            checks.append(("图形界面框架 PyQt6", "已安装", True))
        except ImportError:
            checks.append(("图形界面框架 PyQt6", "缺失（pip install PyQt6）", False))

        try:
            import psutil  # noqa: F401
            checks.append(("系统监控 psutil", "已安装", True))
        except ImportError:
            checks.append(("系统监控 psutil", "缺失（pip install psutil）", False))

        try:
            import mss  # noqa: F401
            checks.append(("截图 mss", "已安装", True))
        except ImportError:
            checks.append(("截图 mss", "缺失（pip install mss）", False))

        is_win = platform.system() == "Windows"
        checks.append(("操作系统", f"{platform.system()} {platform.release()}" + ("" if is_win else "（仅支持 Windows）"), is_win))

        self.result_table.setRowCount(0)
        all_ok = True
        for name, result, ok in checks:
            r = self.result_table.rowCount()
            self.result_table.insertRow(r)
            item = QTableWidgetItem(f"{name}：{result}")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setForeground(QColor("#46c46c" if ok else "#e5484d"))
            self.result_table.setItem(r, 0, item)
            status = QTableWidgetItem("通过" if ok else "未通过")
            status.setFlags(status.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status.setForeground(QColor("#46c46c" if ok else "#e5484d"))
            self.result_table.setItem(r, 1, status)
            all_ok = all_ok and ok
        self.setProperty("checks_ok", all_ok)


class AccountPage(QWizardPage):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.setTitle("第 1 步 · 登录小米账号")
        self.setSubTitle("用于绑定你的音箱与米家设备；推荐扫码登录，无需在本地保存密码。")
        lay = QVBoxLayout(self)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        row = QHBoxLayout()
        self.btn_login = QPushButton("登录小米账号…")
        self.btn_login.setProperty("kind", "primary")
        self.btn_login.clicked.connect(self._open_login)
        self.btn_skip = QPushButton("跳过（稍后在「语音助手」页配置）")
        self.btn_skip.clicked.connect(self._skip)
        row.addWidget(self.btn_login)
        row.addStretch(1)
        row.addWidget(self.btn_skip)
        lay.addLayout(row)

        tip = QLabel(
            "扫码登录：打开米家 App → 我的 → 右上角「扫一扫」扫描二维码即可，"
            "不会在本机保存密码。\n也可以切换到「账号密码」输入小米账号登录。"
        )
        tip.setProperty("muted", True)
        tip.setWordWrap(True)
        lay.addWidget(tip)
        lay.addStretch(1)
        self._refresh()

    def isComplete(self) -> bool:
        return self._logged_in() or self.property("skipped") is True

    def _logged_in(self) -> bool:
        return bool(self.config.get("xiaomi.username", "")) and TOKEN_FILE.is_file()

    def _refresh(self) -> None:
        if self._logged_in():
            kind = "扫码" if self.config.get("xiaomi.login_type") == "qr" else "账号密码"
            self.status.setText(f"已登录（{kind}）：{self.config.get('xiaomi.username', '')}")
        else:
            self.status.setText("尚未登录。点击下方按钮打开登录窗口。")
        self.completeChanged.emit()

    def _skip(self) -> None:
        self.setProperty("skipped", True)
        self.completeChanged.emit()

    def _open_login(self) -> None:
        dlg = LoginDialog(self, self.config, self.config.get("xiaomi.username", ""))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.setProperty("skipped", False)
            self._refresh()


class SpeakerPage(QWizardPage):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.setTitle("第 2 步 · 选择音箱")
        self.setSubTitle("音箱收到的语音指令会从这台设备轮询获取。")
        lay = QVBoxLayout(self)
        self.combo = QComboBox()
        self.combo.setMinimumHeight(36)
        lay.addWidget(self.combo)
        self.btn_refresh = QPushButton("刷新音箱列表")
        self.btn_refresh.clicked.connect(self._load)
        lay.addWidget(self.btn_refresh)
        self.status = QLabel("（未登录时此页可跳过）")
        self.status.setProperty("muted", True)
        lay.addWidget(self.status)
        lay.addStretch(1)

    def initializePage(self) -> None:
        if self.config.get("xiaomi.username", ""):
            self.status.setText("加载中…")
            self._load()

    def _load(self) -> None:
        username = self.config.get("xiaomi.username", "")
        if not username:
            self.status.setText("尚未登录账号，请跳过此页。")
            return

        def fetch():
            account = MiAccount(username, load_password(self.config), token_path=TOKEN_FILE)
            return MiNA(account).device_list()

        def on_done(devices):
            self.combo.clear()
            current = self.config.get("xiaomi.device.device_id", "")
            found = False
            for d in devices:
                if not d.get("deviceID"):
                    continue
                name = d.get("name") or d.get("hardware", "未知设备")
                self.combo.addItem(f"{name}（{d.get('hardware', '')}）", d["deviceID"])
                if d["deviceID"] == current:
                    self.combo.setCurrentIndex(self.combo.count() - 1)
                    found = True
            if self.combo.count():
                self.status.setText(f"找到 {self.combo.count()} 台设备，已自动选中" + ("已配置的设备。" if found else "第一台。"))
            else:
                self.status.setText("账号下没有小爱音箱设备。")

        def on_fail(err):
            self.status.setText(f"获取失败：{err}")

        run_async(self, fetch, on_done, on_fail)

    def validatePage(self) -> bool:
        did = self.combo.currentData()
        if did:
            self.config.set("xiaomi.device.device_id", did)
            self.config.set("xiaomi.device.name", self.combo.currentText())
        return True


class CommandsPage(QWizardPage):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.setTitle("第 3 步 · 语音指令一览")
        self.setSubTitle("部署完成后，对音箱说出下面的指令即可控制电脑；稍后可在「语音助手」页自定义。")
        lay = QVBoxLayout(self)
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["对小爱说", "电脑执行"])
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        action_names = {
            "shutdown": "延迟 60 秒关机（可说“取消关机”撤销）", "restart": "延迟 60 秒重启",
            "lock": "锁定电脑", "sleep": "电脑睡眠", "cancel_shutdown": "取消关机 / 重启任务",
            "screenshot": "截图并保存", "report_status": "播报电脑状态",
            "open_app": "打开已配置的应用", "close_app": "关闭应用", "wol": "唤醒局域网内其他电脑",
            "miot_power": "打开 / 关闭指定的米家设备",
        }
        for rule in DEFAULT_TASKS:
            r = table.rowCount()
            table.insertRow(r)
            pats = " / ".join(rule["patterns"])
            a = action_names.get(rule["action"], rule["action"])
            for c, v in enumerate([pats, a]):
                item = QTableWidgetItem(v)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(r, c, item)
        lay.addWidget(table)


class FinishPage(QWizardPage):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.setTitle("第 4 步 · 完成部署")
        self.setSubTitle("按需勾选，点「完成」保存设置。")
        lay = QVBoxLayout(self)
        self.chk_autostart = QCheckBox("开机自动启动 VoxNode")
        lay.addWidget(self.chk_autostart)
        self.chk_minimized = QCheckBox("启动时最小化到系统托盘")
        lay.addWidget(self.chk_minimized)
        self.chk_start_bridge = QCheckBox("完成部署后立即启动小爱桥接（推荐）")
        self.chk_start_bridge.setChecked(True)
        lay.addWidget(self.chk_start_bridge)
        lay.addStretch(1)
        done = QLabel("部署完成后，试着对小爱说一句「电脑状态」吧！")
        done.setProperty("accent", True)
        lay.addWidget(done)

    def validatePage(self) -> bool:
        self.config.set("start_minimized", self.chk_minimized.isChecked(), save=False)
        self.config.set("bridge.enabled", self.chk_start_bridge.isChecked(), save=False)
        self.config.set("setup_completed", True)
        if self.chk_autostart.isChecked():
            try:
                autostart.enable()
            except Exception as e:
                QMessageBox.warning(self, "自启动设置失败", str(e))
        return True


class SetupWizard(QWizard):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.setWindowTitle(f"{APP_NAME} 首次部署向导")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.IndependentPages, False)
        self.setMinimumSize(720, 560)
        self.addPage(WelcomePage())
        self.addPage(AccountPage(config))
        self.addPage(SpeakerPage(config))
        self.addPage(CommandsPage(config))
        self.addPage(FinishPage(config))

    @property
    def should_start_bridge(self) -> bool:
        return bool(self.config.get("bridge.enabled", False))
