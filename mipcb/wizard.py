"""首次引导式部署向导。

流程：欢迎与环境自检 → 小米账号登录 → 选择小爱音箱 → 语音指令预览 →
完成设置（开机自启 / 最小化启动 / 立即启动桥接）。
"""
from __future__ import annotations

import platform
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWizard, QWizardPage,
)

from miiotpcapi import APP_NAME, APP_NAME_ZH, __version__
from miiotpcapi.config import Config, DEFAULT_TASKS, TOKEN_FILE
from miiotpcapi.core import autostart
from miiotpcapi.secure import clear_password, load_password, save_password
from miiotpcapi.xiaomi.account import MiAccount
from miiotpcapi.xiaomi.mina import MiNA

from .bridge_signals import OtpBridge, ask_otp_from_thread
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
        self.setSubTitle("用于绑定你的小爱音箱；密码经 DPAPI 加密后只保存在本机。")
        lay = QVBoxLayout(self)
        self.user = QLineEdit(config.get("xiaomi.username", ""))
        self.user.setPlaceholderText("手机号或邮箱")
        self.pwd = QLineEdit()
        self.pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd.setPlaceholderText("小米账号密码")
        self.save_chk = QCheckBox("记住密码（推荐，重启后无需重复登录）")
        self.save_chk.setChecked(True)

        fields = QHBoxLayout()
        col1 = QVBoxLayout()
        col1.addWidget(QLabel("账号"))
        col1.addWidget(self.user)
        col2 = QVBoxLayout()
        col2.addWidget(QLabel("密码"))
        col2.addWidget(self.pwd)
        fields.addLayout(col1, 1)
        fields.addLayout(col2, 1)
        lay.addLayout(fields)
        lay.addWidget(self.save_chk)

        row = QHBoxLayout()
        self.btn_login = QPushButton("登录")
        self.btn_login.setProperty("kind", "primary")
        self.btn_login.clicked.connect(self._login)
        self.btn_skip = QPushButton("跳过（稍后在「小爱控制」页配置）")
        self.btn_skip.clicked.connect(lambda: self.setProperty("skipped", True))
        row.addWidget(self.btn_login)
        row.addStretch(1)
        row.addWidget(self.btn_skip)
        lay.addLayout(row)

        self.status = QLabel("登录后才能选择音箱。也可以跳过，稍后再配置。")
        self.status.setProperty("muted", True)
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        lay.addStretch(1)
        self._logged_in = False

    def isComplete(self) -> bool:
        return self._logged_in or self.property("skipped") is True

    def _login(self) -> None:
        user = self.user.text().strip()
        pwd = self.pwd.text()
        if not user or not pwd:
            self.status.setText("请填写账号和密码。")
            return
        self.btn_login.setEnabled(False)
        self.status.setText("登录中，若触发安全验证会弹出验证码输入框…")
        otp_bridge = OtpBridge(self)

        def otp(method: str) -> str:
            return ask_otp_from_thread(otp_bridge, method)

        def do_login():
            account = MiAccount(user, pwd, token_path=TOKEN_FILE, otp_callback=otp)
            ok = account.login()
            if ok and self.save_chk.isChecked():
                save_password(self.config, pwd)
            elif ok:
                clear_password(self.config)
            return ok

        def on_done(ok):
            self.btn_login.setEnabled(True)
            if ok:
                self.config.set("xiaomi.username", user, save=False)
                self.config.save()
                self._logged_in = True
                self.status.setText("登录成功！")
                self.completeChanged.emit()
            else:
                self.status.setText("登录失败，请检查账号密码。")

        def on_fail(err):
            self.btn_login.setEnabled(True)
            self.status.setText(f"登录失败：{err}")

        run_async(self, do_login, on_done, on_fail)


class SpeakerPage(QWizardPage):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.setTitle("第 2 步 · 选择小爱音箱")
        self.setSubTitle("小爱收到的语音指令会从这台音箱轮询获取。")
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
        self.setSubTitle("部署完成后，对小爱说出下面的指令即可控制电脑；稍后可在「小爱控制」页自定义。")
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
            "open_app": "打开已配置的应用", "close_app": "关闭应用", "wol": "网络唤醒指定主机",
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
        self.chk_autostart = QCheckBox("开机自动启动 MiPC Bridge")
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
