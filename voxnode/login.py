"""登录对话框：支持小米账号「扫码登录」与「账号密码登录」。"""
from __future__ import annotations

import threading
import time
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from miiotpcapi.config import Config, TOKEN_FILE
from miiotpcapi.secure import clear_password, save_password
from miiotpcapi.xiaomi import qrlogin as qr
from miiotpcapi.xiaomi.account import SID_MIIO, SID_MINA, MiAccount
from miiotpcapi.xiaomi.qrlogin import XiaomiQrLogin

from .bridge_signals import OtpBridge, ask_otp
from .workers import run_async


class QrLoginWorker(QThread):
    """后台完成「申请二维码 → 轮询 → 拿到 passToken」全过程。"""

    qr_ready = pyqtSignal(bytes)
    status = pyqtSignal(str)
    confirmed = pyqtSignal(str, str)   # pass_token, user_id
    failed = pyqtSignal(str)

    def __init__(self, sid: str, parent=None):
        super().__init__(parent)
        self.sid = sid
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:  # noqa: C901
        while not self._stop.is_set():
            try:
                session = XiaomiQrLogin(sid=self.sid)
                session.start()
                image = session.fetch_qr_image()
            except Exception as e:
                self.failed.emit(f"{e}")
                return
            self.qr_ready.emit(image)
            self.status.emit("请打开米家 App → 我的 → 右上角扫一扫")

            deadline = time.time() + session.expires_in
            while not self._stop.is_set() and time.time() < deadline:
                state = session.poll()
                if state == qr.CONFIRMED:
                    self.confirmed.emit(session.pass_token, session.user_id)
                    return
                if state == qr.SCANNED:
                    self.status.emit("已扫描，请在手机上确认登录")
                elif state == qr.EXPIRED:
                    break
                elif state == qr.FAILED:
                    self.failed.emit(session.error or "扫码登录失败")
                    return
            if self._stop.is_set():
                return
            self.status.emit("二维码已过期，正在自动刷新…")


class LoginDialog(QDialog):
    """登录小米账号。默认「扫码登录」，也可切换到账号密码。"""

    def __init__(self, parent, config: Config, username: str = ""):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("登录小米账号")
        self.setMinimumWidth(460)

        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_qr_tab(), "扫码登录")
        self.tabs.addTab(self._build_password_tab(username), "账号密码")
        lay.addWidget(self.tabs)

        tip = QLabel("扫码登录更安全，无需在本地保存密码；两种方式都需要在米家 App 里绑定过账号。")
        tip.setProperty("muted", True)
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self._worker: Optional[QrLoginWorker] = None
        self._parent = parent
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._start_qr()

    # -- 扫码页 --------------------------------------------------------
    def _build_qr_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        self.qr_label = QLabel("正在获取二维码…")
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setMinimumHeight(280)
        self.qr_label.setStyleSheet("border: 1px dashed #2e333d; border-radius: 10px;")
        lay.addWidget(self.qr_label)

        self.qr_status = QLabel("")
        self.qr_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_status.setWordWrap(True)
        lay.addWidget(self.qr_status)

        row = QHBoxLayout()
        self.btn_refresh_qr = QPushButton("刷新二维码")
        self.btn_refresh_qr.clicked.connect(self._start_qr)
        row.addStretch(1)
        row.addWidget(self.btn_refresh_qr)
        row.addStretch(1)
        lay.addLayout(row)
        return page

    def _start_qr(self) -> None:
        self._stop_qr()
        self.qr_label.setText("正在获取二维码…")
        self.qr_label.setPixmap(QPixmap())
        self.qr_status.setText("")
        worker = QrLoginWorker("mijia", self)
        worker.qr_ready.connect(self._on_qr_ready)
        worker.status.connect(self.qr_status.setText)
        worker.confirmed.connect(self._on_qr_confirmed)
        worker.failed.connect(self._on_qr_failed)
        self._worker = worker
        worker.start()

    def _stop_qr(self) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(1500)
            self._worker = None

    def _on_qr_ready(self, data: bytes) -> None:
        pix = QPixmap()
        if pix.loadFromData(data):
            self.qr_label.setPixmap(pix.scaled(
                260, 260, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
        else:
            self.qr_label.setText("二维码加载失败，请点击刷新")

    def _on_qr_failed(self, message: str) -> None:
        self.qr_status.setText(f"扫码登录失败：{message}")
        self.qr_label.setText("点击「刷新二维码」重试")

    def _on_qr_confirmed(self, pass_token: str, user_id: str) -> None:
        self.qr_status.setText("登录成功，正在获取访问令牌…")
        self._stop_qr()

        def exchange():
            account = MiAccount(user_id, "", token_path=TOKEN_FILE)
            account.token["userId"] = user_id
            # 用同一次扫码的 passToken 换取各业务 sid 的令牌
            account.login_with_pass_token(SID_MINA, pass_token, user_id)
            account.login_with_pass_token(SID_MIIO, pass_token, user_id)
            return user_id

        def on_done(uid):
            self.config.set("xiaomi.username", str(uid), save=False)
            self.config.set("xiaomi.login_type", "qr", save=False)
            clear_password(self.config)  # 扫码登录不保存密码
            self.config.save()
            self.accept()

        def on_fail(err: str):
            self.qr_status.setText(f"换取令牌失败：{err}")

        run_async(self, exchange, on_done, on_fail)

    # -- 密码页 --------------------------------------------------------
    def _build_password_tab(self, username: str) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        form = QFormLayout()
        self.user = QLineEdit(username)
        self.user.setPlaceholderText("手机号 / 邮箱 / 小米 ID")
        self.pwd = QLineEdit()
        self.pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.pwd.setPlaceholderText("小米账号密码")
        form.addRow("账号", self.user)
        form.addRow("密码", self.pwd)
        lay.addLayout(form)

        self.save_chk = QCheckBox("记住密码（DPAPI 加密保存，仅本机可解）")
        self.save_chk.setChecked(bool(self.config.get("xiaomi.save_password", True)))
        lay.addWidget(self.save_chk)

        self.pwd_status = QLabel("密码仅用于登录并换取 serviceToken，不会上传到任何第三方。")
        self.pwd_status.setProperty("muted", True)
        self.pwd_status.setWordWrap(True)
        lay.addWidget(self.pwd_status)

        self.btn_login = QPushButton("登录")
        self.btn_login.setProperty("kind", "primary")
        self.btn_login.clicked.connect(self._login_password)
        lay.addWidget(self.btn_login)
        lay.addStretch(1)
        return page

    def _login_password(self) -> None:
        user = self.user.text().strip()
        pwd = self.pwd.text()
        if not user or not pwd:
            self.pwd_status.setText("请输入账号和密码。")
            return
        self.pwd_status.setText("登录中，若触发安全验证会弹出验证码输入框…")
        otp_bridge = OtpBridge(self)

        def otp(method: str) -> str:
            return ask_otp(otp_bridge, method)

        def do_login():
            account = MiAccount(user, pwd, token_path=TOKEN_FILE, otp_callback=otp)
            account.login(SID_MINA)
            account.login(SID_MIIO)   # 同时拿到米家设备的令牌
            return True

        def on_done(_):
            self.config.set("xiaomi.username", user, save=False)
            self.config.set("xiaomi.login_type", "password", save=False)
            if self.save_chk.isChecked():
                save_password(self.config, pwd)
            else:
                clear_password(self.config)
            self.config.save()
            self.accept()

        def on_fail(err: str):
            self.pwd_status.setText(f"登录失败：{err}")

        run_async(self, do_login, on_done, on_fail)

    # -- 生命周期 ------------------------------------------------------
    def _on_tab_changed(self, index: int) -> None:
        if index == 0:
            if self._worker is None:
                self._start_qr()
        else:
            self._stop_qr()

    def closeEvent(self, event) -> None:
        self._stop_qr()
        super().closeEvent(event)

    def reject(self) -> None:
        self._stop_qr()
        super().reject()
