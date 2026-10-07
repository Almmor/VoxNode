"""桥接信号与跨线程 OTP 验证码输入桥。"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QMetaObject, Qt, Q_ARG, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QInputDialog


class BridgeSignals(QObject):
    """XiaoaiBridge 工作线程 → GUI 主线程的信号中继。"""

    query = pyqtSignal(str)
    result = pyqtSignal(str, str, bool, str)
    log = pyqtSignal(str)
    state = pyqtSignal(bool)


class OtpBridge(QObject):
    """持有对话框引用；其 ask_code 槽必须在主线程执行。

    工作线程通过 invokeMethod(BlockingQueuedConnection) 调用它，
    阻塞等待用户在主线程输入验证码后返回结果。
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.parent_widget = parent

    @pyqtSlot(str, result=str)
    def ask_code(self, method: str) -> str:
        code, ok = QInputDialog.getText(
            self.parent_widget, "小米账号安全验证",
            f"已向你的{method}发送验证码，请输入：")
        return code if ok else ""


def ask_otp_from_thread(otp_bridge: OtpBridge, method: str) -> str:
    """任意线程可调用：弹验证码输入框（主线程渲染），返回用户输入。"""
    ret = QMetaObject.invokeMethod(
        otp_bridge, "ask_code", Qt.ConnectionType.BlockingQueuedConnection,
        Q_ARG(str, method),
    )
    return str(ret) if ret else ""
