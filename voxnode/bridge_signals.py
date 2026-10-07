"""桥接信号与跨线程 OTP 验证码输入桥。"""
from __future__ import annotations

import threading
from typing import Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication, QInputDialog, QWidget


class BridgeSignals(QObject):
    """XiaoaiBridge 工作线程 → GUI 主线程的信号中继。"""

    query = pyqtSignal(str)
    result = pyqtSignal(str, str, bool, str)
    log = pyqtSignal(str)
    state = pyqtSignal(bool)


class ChannelSignals(QObject):
    """米家指令通道工作线程 → GUI 主线程的信号中继。"""

    log = pyqtSignal(str)
    state = pyqtSignal(bool)
    trigger = pyqtSignal(str, str, bool)   # 属性值, 说明, 是否成功


class OtpBridge(QObject):
    """跨线程请求用户输入验证码。

    背景：PyQt6 的 QMetaObject.invokeMethod 即使使用 BlockingQueuedConnection
    也**不会**返回槽函数的返回值（实测恒为 None），因此旧实现拿不到验证码，
    导致登录时报「未提供验证码」。

    现改为双向配合：
      工作线程 --信号(队列)--> 主线程弹窗输入 --threading.Event--> 工作线程取回结果
    """

    _request = pyqtSignal(str)

    def __init__(self, parent: Optional[QWidget] = None, timeout: float = 300.0):
        super().__init__(parent)
        self.parent_widget = parent
        self._timeout = timeout
        self._event = threading.Event()
        self._result = ""
        # 接收者在主线程创建，跨线程 emit 会自动排队到主线程执行
        self._request.connect(self._on_request)

    # ------------------------------------------------------------------
    def ask(self, method: str) -> str:
        """可在任意线程调用；阻塞等待用户输入，超时或取消返回空串。"""
        app = QApplication.instance()
        if app is not None and QThread.currentThread() is app.thread():
            # 已经处于主线程：直接弹窗，避免自我阻塞
            return self._show_dialog(method)
        self._event.clear()
        self._result = ""
        self._request.emit(method)
        if not self._event.wait(self._timeout):
            return ""
        return self._result

    # ------------------------------------------------------------------
    @pyqtSlot(str)
    def _on_request(self, method: str) -> None:
        """在主线程中执行，弹出输入框。"""
        try:
            self._result = self._show_dialog(method)
        finally:
            self._event.set()

    def _show_dialog(self, method: str) -> str:
        label = {"Phone": "短信", "Email": "邮箱"}.get(method, method)
        parent = self.parent_widget
        code, ok = QInputDialog.getText(
            parent, "小米账号安全验证",
            f"已向你的{label}发送验证码，请在 5 分钟内输入：\n（取消则放弃本次登录）",
        )
        return code.strip() if ok else ""


def ask_otp(bridge: OtpBridge, method: str) -> str:
    """请求验证码（可在任意线程调用）。"""
    return bridge.ask(method)


# 兼容旧调用名
def ask_otp_from_thread(bridge: OtpBridge, method: str) -> str:
    return bridge.ask(method)
