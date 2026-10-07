"""应用入口：首次运行走引导式部署向导，之后直接进入主界面。"""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from miiotpcapi import APP_NAME
from miiotpcapi.config import Config
from miiotpcapi.xiaomi.bridge import XiaoaiBridge

from .bridge_signals import BridgeSignals, OtpBridge, ask_otp_from_thread
from .main_window import MainWindow, make_app_icon
from .theme import apply_theme
from .wizard import SetupWizard


def _set_dpi_aware() -> None:
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def run(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    force_wizard = "--setup" in argv
    first_run = False

    _set_dpi_aware()
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setWindowIcon(make_app_icon())
    app.setQuitOnLastWindowClosed(False)  # 关闭主窗口时驻留系统托盘
    apply_theme(app)

    config = Config()
    need_setup = force_wizard or not config.get("setup_completed", False)
    first_run = need_setup

    # 桥接信号中继（工作线程 → 主线程）
    signals = BridgeSignals()
    otp_bridge = OtpBridge(None)

    def on_otp(method: str) -> str:
        return ask_otp_from_thread(otp_bridge, method)

    bridge = XiaoaiBridge(
        config,
        on_query=lambda q: signals.query.emit(q),
        on_result=lambda q, r, ok, d: signals.result.emit(q, r, ok, d),
        on_log=lambda m: signals.log.emit(m),
        on_state=lambda r: signals.state.emit(r),
        on_otp=on_otp,
    )

    # 首次部署时先不显示主窗口，避免向导后面闪现
    start_minimized = bool(config.get("start_minimized", False)) or first_run
    window = MainWindow(config, bridge, signals, start_minimized=start_minimized)
    otp_bridge.parent_widget = window
    otp_bridge.setParent(window)

    def _start_bridge() -> None:
        if config.get("xiaomi.username", ""):
            bridge.start()
        else:
            QMessageBox.information(window, "提示", "请先在「小爱控制」页登录小米账号。")

    window.start_requested.connect(_start_bridge)
    window.stop_requested.connect(bridge.stop)
    app.aboutToQuit.connect(bridge.stop)

    if need_setup:
        wizard = SetupWizard(config)
        wizard.setWindowIcon(make_app_icon())
        accepted = wizard.exec() == SetupWizard.DialogCode.Accepted
        if not accepted and not config.get("setup_completed", False):
            window.tray.hide()
            return 0  # 用户中途取消且尚未完成部署，直接退出
        if not config.get("start_minimized", False):
            window.show_up()
        if config.get("bridge.enabled", False) and config.get("xiaomi.username", ""):
            bridge.start()
    else:
        if config.get("bridge.enabled", False) and config.get("xiaomi.username", ""):
            bridge.start()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
