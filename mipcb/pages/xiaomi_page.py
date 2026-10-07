"""小爱控制：账号登录 / 音箱选择 / 桥接启停 / 语音指令规则 / 运行日志。"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QFrame,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from miiotpcapi.config import Config, TOKEN_FILE
from miiotpcapi.secure import clear_password, load_password, save_password
from miiotpcapi.tasks import ACTIONS
from miiotpcapi.xiaomi.account import MiAccount
from miiotpcapi.xiaomi.mina import MiNA

from ..bridge_signals import BridgeSignals, OtpBridge, ask_otp_from_thread
from ..ui import card, page
from ..workers import run_async


class LoginDialog(QDialog):
    def __init__(self, parent, config: Config, username: str = ""):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("登录小米账号")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.user = QLineEdit(username)
        self.pwd = QLineEdit()
        self.pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.save = QCheckBox("记住密码（DPAPI 加密保存，仅本机可解）")
        self.save.setChecked(bool(config.get("xiaomi.save_password", True)))
        form.addRow("账号（手机/邮箱）", self.user)
        form.addRow("密码", self.pwd)
        lay.addLayout(form)
        lay.addWidget(self.save)
        self.status = QLabel("密码仅用于登录并获取 serviceToken，不会上传到任何第三方。")
        self.status.setProperty("muted", True)
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        btn = QPushButton("登录")
        btn.setProperty("kind", "primary")
        btn.clicked.connect(self._login)
        lay.addWidget(btn)

    def _login(self) -> None:
        user = self.user.text().strip()
        pwd = self.pwd.text()
        if not user or not pwd:
            self.status.setText("请输入账号和密码。")
            return
        self.status.setText("登录中，若需要验证码会弹出输入框…")
        otp_bridge = OtpBridge(self)

        def otp(method: str) -> str:
            return ask_otp_from_thread(otp_bridge, method)

        def on_done(_):
            self.config.set("xiaomi.username", user, save=False)
            if self.save.isChecked():
                save_password(self.config, pwd)
            else:
                clear_password(self.config)
            self.config.save()
            self.accept()

        def on_fail(err: str):
            self.status.setText(f"登录失败：{err}")

        def do_login():
            account = MiAccount(user, pwd, token_path=TOKEN_FILE, otp_callback=otp)
            return account.login()

        run_async(self, do_login, on_done, on_fail)


class TaskEditDialog(QDialog):
    def __init__(self, parent, rule: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("编辑指令" if rule else "添加指令")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.patterns = QLineEdit(" / ".join(rule["patterns"]) if rule else "")
        self.patterns.setPlaceholderText("如：关机 / 关闭电脑（支持正则，用 / 分隔）")
        self.action = QComboBox()
        for a in sorted(ACTIONS):
            self.action.addItem(a)
        if rule:
            self.action.setCurrentText(rule.get("action", "tts"))
        self.reply = QLineEdit(rule.get("reply", "") if rule else "")
        self.reply.setPlaceholderText("小爱播报的回复，可留空；支持 {app} 等占位")
        self.enabled = QCheckBox("启用")
        self.enabled.setChecked(rule.get("enabled", True) if rule else True)
        form.addRow("匹配词", self.patterns)
        form.addRow("动作", self.action)
        form.addRow("回复", self.reply)
        lay.addLayout(form)
        lay.addWidget(self.enabled)
        tip = QLabel("内置动作：shutdown/restart/lock/sleep/hibernate/signout/cancel_shutdown/"
                     "screenshot/report_status/open_app/close_app/wol/volume/media/tts；"
                     "open_app 等动作的参数可用命名捕获组，如 打开(?P<app>.+)")
        tip.setProperty("muted", True)
        tip.setWordWrap(True)
        lay.addWidget(tip)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def values(self) -> dict:
        patterns = [p.strip() for p in self.patterns.text().split("/") if p.strip()]
        return {
            "id": self._make_id(patterns),
            "enabled": self.enabled.isChecked(),
            "patterns": patterns,
            "action": self.action.currentText(),
            "reply": self.reply.text().strip(),
        }

    @staticmethod
    def _make_id(patterns: list[str]) -> str:
        import hashlib
        return "task-" + hashlib.md5("|".join(patterns).encode()).hexdigest()[:8]


class XiaoaiPage(QFrame):
    def __init__(self, config: Config, bridge, signals: BridgeSignals):
        super().__init__()
        self.config = config
        self.bridge = bridge
        _, lay = page("小爱控制", "登录小米账号后，对小爱音箱说话即可控制这台电脑", root=self)

        # -- 账号 ----------------------------------------------------------
        acc_card, acc_lay = card("小米账号")
        acc_row = QHBoxLayout()
        self.acc_label = QLabel("未登录")
        self.acc_label.setProperty("muted", True)
        btn_login = QPushButton("登录 / 切换账号")
        btn_login.setProperty("kind", "primary")
        btn_login.clicked.connect(self._login)
        btn_logout = QPushButton("退出登录")
        btn_logout.setProperty("kind", "ghost")
        btn_logout.clicked.connect(self._logout)
        acc_row.addWidget(self.acc_label, 1)
        acc_row.addWidget(btn_login)
        acc_row.addWidget(btn_logout)
        acc_lay.addLayout(acc_row)

        spk_row = QHBoxLayout()
        self.speaker = QComboBox()
        self.speaker.setMinimumWidth(260)
        self.speaker.currentIndexChanged.connect(self._on_speaker_changed)
        btn_spk = QPushButton("刷新音箱列表")
        btn_spk.clicked.connect(self._load_speakers)
        spk_row.addWidget(QLabel("音箱"))
        spk_row.addWidget(self.speaker, 1)
        spk_row.addWidget(btn_spk)
        acc_lay.addLayout(spk_row)
        lay.addWidget(acc_card)

        # -- 桥接 ----------------------------------------------------------
        br_card, br_lay = card("语音桥接")
        br_row = QHBoxLayout()
        self.state_label = QLabel("已停止")
        btn_start = QPushButton("启动桥接")
        btn_start.setProperty("kind", "primary")
        btn_start.clicked.connect(self._start)
        btn_stop = QPushButton("停止")
        btn_stop.clicked.connect(self._stop)
        btn_test = QPushButton("测试播报")
        btn_test.clicked.connect(self._test_tts)
        br_row.addWidget(self.state_label)
        br_row.addStretch(1)
        br_row.addWidget(btn_start)
        br_row.addWidget(btn_stop)
        br_row.addWidget(btn_test)
        br_lay.addLayout(br_row)

        opt_row = QHBoxLayout()
        self.interval = QDoubleSpinBox()
        self.interval.setRange(1.0, 30.0)
        self.interval.setSingleStep(0.5)
        self.interval.setSuffix(" 秒")
        self.interval.setValue(float(config.get("bridge.poll_interval", 2.0)))
        self.tts_reply = QCheckBox("小爱语音播报执行结果")
        self.tts_reply.setChecked(bool(config.get("bridge.tts_reply", True)))
        opt_row.addWidget(QLabel("轮询间隔"))
        opt_row.addWidget(self.interval)
        opt_row.addStretch(1)
        opt_row.addWidget(self.tts_reply)
        br_lay.addLayout(opt_row)
        lay.addWidget(br_card)

        # -- 指令规则 ------------------------------------------------------
        rule_card, rule_lay = card("语音指令规则")
        rule_bar = QHBoxLayout()
        btn_rule_add = QPushButton("添加指令")
        btn_rule_add.clicked.connect(self._rule_add)
        btn_rule_edit = QPushButton("编辑")
        btn_rule_edit.clicked.connect(self._rule_edit)
        btn_rule_del = QPushButton("删除")
        btn_rule_del.setProperty("kind", "danger")
        btn_rule_del.clicked.connect(self._rule_del)
        btn_reset = QPushButton("恢复默认指令")
        btn_reset.setProperty("kind", "ghost")
        btn_reset.clicked.connect(self._rule_reset)
        rule_bar.addWidget(btn_rule_add)
        rule_bar.addWidget(btn_rule_edit)
        rule_bar.addWidget(btn_rule_del)
        rule_bar.addStretch(1)
        rule_bar.addWidget(btn_reset)
        rule_lay.addLayout(rule_bar)

        self.rule_table = QTableWidget(0, 4)
        self.rule_table.setHorizontalHeaderLabels(["启用", "匹配词", "动作", "回复"])
        self.rule_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.rule_table.verticalHeader().setVisible(False)
        self.rule_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rule_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        rule_lay.addWidget(self.rule_table)
        lay.addWidget(rule_card, 2)

        # -- 日志 ----------------------------------------------------------
        log_card, log_lay = card("运行日志")
        self.log_list = QListWidget()
        self.log_list.setMaximumHeight(200)
        log_lay.addWidget(self.log_list)
        lay.addWidget(log_card, 1)

        signals.log.connect(self._append_log)
        signals.result.connect(self._on_result)
        signals.state.connect(self._on_state)
        self._refresh_acc()
        self._load_rules()

        if config.get("bridge.enabled", False) and config.get("setup_completed", False):
            self._start()

    # -- 账号 --------------------------------------------------------------
    def _refresh_acc(self) -> None:
        username = self.config.get("xiaomi.username", "")
        logged = bool(username) and TOKEN_FILE.is_file()
        dev_name = self.config.get("xiaomi.device.name", "")
        text = f"已登录：{username}" if logged else "未登录"
        if dev_name:
            text += f"｜音箱：{dev_name}"
        self.acc_label.setText(text)
        self.acc_label.setProperty("muted", not logged)

    def _login(self) -> None:
        dlg = LoginDialog(self, self.config, self.config.get("xiaomi.username", ""))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.bridge.account = None  # 强制重建会话
            self._refresh_acc()
            self._load_speakers()

    def _logout(self) -> None:
        ret = QMessageBox.question(self, "确认", "退出小米账号并清除本地凭据？")
        if ret != QMessageBox.StandardButton.Yes:
            return
        if TOKEN_FILE.is_file():
            TOKEN_FILE.unlink()
        clear_password(self.config)
        self.config.set("xiaomi.username", "")
        self.config.set("xiaomi.device.device_id", "")
        self.config.set("xiaomi.device.name", "")
        self._refresh_acc()

    # -- 音箱 --------------------------------------------------------------
    def _load_speakers(self) -> None:
        username = self.config.get("xiaomi.username", "")
        if not username:
            QMessageBox.information(self, "提示", "请先登录小米账号。")
            return

        def fetch():
            account = MiAccount(username, load_password(self.config), token_path=TOKEN_FILE)
            return MiNA(account).device_list()

        def on_done(devices):
            self.speaker.clear()
            current = self.config.get("xiaomi.device.device_id", "")
            for d in devices:
                if not d.get("deviceID"):
                    continue
                name = d.get("name") or d.get("hardware", "未知设备")
                self.speaker.addItem(name, d["deviceID"])
                if d["deviceID"] == current:
                    self.speaker.setCurrentIndex(self.speaker.count() - 1)

        def on_fail(err):
            QMessageBox.warning(self, "获取音箱失败", err)

        run_async(self, fetch, on_done, on_fail)

    def _on_speaker_changed(self, index: int) -> None:
        did = self.speaker.currentData()
        if did:
            self.config.set("xiaomi.device.device_id", did)
            self.config.set("xiaomi.device.name", self.speaker.currentText())

    # -- 桥接 --------------------------------------------------------------
    def _start(self) -> None:
        self.config.set("bridge.poll_interval", float(self.interval.value()), save=False)
        self.config.set("bridge.tts_reply", self.tts_reply.isChecked(), save=False)
        self.config.set("bridge.enabled", True)
        if not self.config.get("xiaomi.username", ""):
            QMessageBox.information(self, "提示", "请先登录小米账号，再启动桥接。")
            return
        self.bridge.start()

    def _stop(self) -> None:
        self.config.set("bridge.enabled", False)
        self.bridge.stop()

    def _test_tts(self) -> None:
        def on_fail(err):
            QMessageBox.warning(self, "测试失败", err)
        run_async(self, self.bridge.test_tts, lambda _: None, on_fail)

    def _on_state(self, running: bool) -> None:
        self.state_label.setText("运行中" if running else "已停止")
        self.state_label.setProperty("accent", running)
        self._refresh_acc()

    def _on_result(self, query: str, reply: str, ok: bool, detail: str) -> None:
        mark = "✓" if ok else "✗"
        self._append_log(f"[{mark}] “{query}” → {reply or '（无回复）'}" + (f"（{detail}）" if detail else ""))

    def _append_log(self, msg: str) -> None:
        from datetime import datetime
        self.log_list.insertItem(0, f"{datetime.now().strftime('%H:%M:%S')}  {msg}")
        while self.log_list.count() > 500:
            self.log_list.takeItem(self.log_list.count() - 1)

    # -- 指令规则 ------------------------------------------------------------
    def _load_rules(self) -> None:
        rules = self.config.get("tasks", [])
        self.rule_table.setRowCount(0)
        for r in rules:
            row = self.rule_table.rowCount()
            self.rule_table.insertRow(row)
            enabled = QTableWidgetItem("启用" if r.get("enabled", True) else "停用")
            enabled.setFlags((enabled.flags() & ~Qt.ItemFlag.ItemIsEditable) | Qt.ItemFlag.ItemIsUserCheckable)
            enabled.setCheckState(Qt.CheckState.Checked if r.get("enabled", True) else Qt.CheckState.Unchecked)
            self.rule_table.setItem(row, 0, enabled)
            for c, val in enumerate([" / ".join(r.get("patterns", [])), r.get("action", ""), r.get("reply", "")]):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.rule_table.setItem(row, c + 1, item)

    def _selected_rule(self) -> tuple[int, dict] | None:
        rows = self.rule_table.selectedIndexes()
        if not rows:
            return None
        r = rows[0].row()
        return r, self.config.get("tasks", [])[r]

    def _rule_add(self) -> None:
        dlg = TaskEditDialog(self)
        while dlg.exec() == QDialog.DialogCode.Accepted:
            v = dlg.values()
            if not v["patterns"]:
                QMessageBox.warning(self, "提示", "匹配词不能为空。")
                continue
            rules = self.config.get("tasks", [])
            rules.append(v)
            self.config.set("tasks", rules)
            self._load_rules()
            return

    def _rule_edit(self) -> None:
        sel = self._selected_rule()
        if not sel:
            QMessageBox.information(self, "提示", "请先选中一条指令。")
            return
        r, rule = sel
        dlg = TaskEditDialog(self, rule)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            v = dlg.values()
            if not v["patterns"]:
                QMessageBox.warning(self, "提示", "匹配词不能为空。")
                return
            rules = self.config.get("tasks", [])
            rules[r] = {**rule, **v}
            self.config.set("tasks", rules)
            self._load_rules()

    def _rule_del(self) -> None:
        sel = self._selected_rule()
        if not sel:
            QMessageBox.information(self, "提示", "请先选中一条指令。")
            return
        r, rule = sel
        ret = QMessageBox.question(self, "确认删除", f"删除指令「{rule['patterns'][0]}…」？")
        if ret != QMessageBox.StandardButton.Yes:
            return
        rules = self.config.get("tasks", [])
        rules.pop(r)
        self.config.set("tasks", rules)
        self._load_rules()

    def _rule_reset(self) -> None:
        ret = QMessageBox.question(self, "确认", "恢复为默认指令集？现有自定义指令将被覆盖。")
        if ret != QMessageBox.StandardButton.Yes:
            return
        from miiotpcapi.config import DEFAULT_TASKS
        self.config.set("tasks", DEFAULT_TASKS)
        self._load_rules()

    def on_shown(self) -> None:
        self._refresh_acc()
