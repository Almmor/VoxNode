"""应用入口：首次运行走引导式部署向导，之后直接进入主界面。"""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from miiotpcapi import APP_NAME
from miiotpcapi.config import Config
from miiotpcapi.tasks import TaskExecutor
from miiotpcapi.xiaomi.bridge import XiaoaiBridge
from miiotpcapi.xiaomi.channel import MijiaChannel

from .bridge_signals import BridgeSignals, ChannelSignals, OtpBridge, ask_otp
from .main_window import MainWindow, make_app_icon
from .pages.mijia_page import make_miio
from .theme import apply_theme
from .wizard import SetupWizard


def _set_dpi_aware() -> None:
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def _selftest() -> int:
    """打包后的自检：离屏构建全部界面，结果写入文件并返回退出码。

    用于验证 PyInstaller 产物是否完整（依赖、Qt 插件、资源均可用）。
    """
    import os
    import tempfile
    import traceback
    from pathlib import Path

    report = Path(tempfile.gettempdir()) / "voxnode_selftest.txt"
    lines: list[str] = []
    ok = True
    try:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"  # 必须在 QApplication 之前
        from PyQt6.QtWidgets import QApplication

        app = QApplication.instance() or QApplication([])
        apply_theme(app)
        lines.append(f"frozen={getattr(sys, 'frozen', False)}")
        lines.append(f"executable={sys.executable}")

        # 核心库
        from miiotpcapi.core import monitor, screenshot, sysinfo, wol
        lines.append(f"hostname={sysinfo.hostname()}")
        lines.append(f"cpu_cores={sysinfo.summary()['cpu_cores']}")
        lines.append(f"mem_percent={monitor.memory()['percent']}")
        _ = screenshot.list_monitors()
        lines.append("screenshot.monitors=ok")
        wol.normalize_mac("AA:BB:CC:DD:EE:FF")
        lines.append("wol=ok")

        # 指令引擎
        from miiotpcapi.config import Config, DEFAULT_TASKS
        from miiotpcapi.tasks import match
        m = match("关机", DEFAULT_TASKS)
        lines.append(f"match={m.rule['action'] if m else 'FAIL'}")

        # 米家：签名算法自检（不联网）
        from miiotpcapi.xiaomi.miot import sign_data, sign_nonce
        import base64 as _b64
        ssecurity = _b64.b64encode(b"0123456789abcdef").decode()
        nonce = _b64.b64encode(b"abcdefgh" + (0).to_bytes(4, "big")).decode()
        assert len(sign_nonce(ssecurity, nonce)) > 0
        signed = sign_data("/home/device_list", '{"a": 1}', ssecurity)
        assert {"data", "nonce", "signature"} == set(signed)
        lines.append("miot_sign=ok")

        # 米家：指令通道取值匹配
        from miiotpcapi.xiaomi.channel import value_matches
        assert value_matches(True, "1") and value_matches(0, "off") and value_matches(30, "30")
        assert not value_matches(2, "1")
        lines.append("channel_match=ok")

        # 扫码登录模块可导入
        from miiotpcapi.xiaomi.qrlogin import XiaomiQrLogin  # noqa: F401
        lines.append("qrlogin=ok")

        # 界面：主窗口各页 + 向导 5 页
        tmp_cfg = Path(tempfile.gettempdir()) / "voxnode_selftest_cfg.json"
        cfg = Config(path=tmp_cfg)
        from miiotpcapi.tasks import TaskExecutor
        from miiotpcapi.xiaomi.bridge import XiaoaiBridge
        from miiotpcapi.xiaomi.channel import MijiaChannel

        from .bridge_signals import BridgeSignals, ChannelSignals
        from .main_window import MainWindow
        from .wizard import SetupWizard

        signals = BridgeSignals()
        chan_signals = ChannelSignals()
        bridge = XiaoaiBridge(cfg)
        channel = MijiaChannel(cfg, lambda: TaskExecutor(), on_log=lambda m: None)
        win = MainWindow(cfg, bridge, signals, channel=channel,
                         channel_signals=chan_signals, start_minimized=True)
        for i in range(win.nav.count()):
            win.nav.setCurrentRow(i)
            app.processEvents()
        lines.append(f"main_window_pages={win.stack.count()}")
        wiz = SetupWizard(cfg)
        ids = wiz.pageIds()
        for pid in ids:
            wiz.setCurrentId(pid)
            app.processEvents()
        lines.append(f"wizard_pages={len(ids)}")
        win.tray.hide()
        win.hide()
        if tmp_cfg.exists():
            tmp_cfg.unlink()
        lines.append("RESULT=PASS")
    except Exception:
        ok = False
        lines.append("RESULT=FAIL")
        lines.append(traceback.format_exc())

    text = "\n".join(lines)
    try:
        report.write_text(text, "utf-8")
    except Exception:
        pass
    print(text)
    return 0 if ok else 1


def run(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if "--selftest" in argv:
        return _selftest()
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

    # 信号中继（工作线程 → 主线程）
    signals = BridgeSignals()
    channel_signals = ChannelSignals()
    otp_bridge = OtpBridge(None)

    def on_otp(method: str) -> str:
        return ask_otp(otp_bridge, method)

    bridge = XiaoaiBridge(
        config,
        on_query=lambda q: signals.query.emit(q),
        on_result=lambda q, r, ok, d: signals.result.emit(q, r, ok, d),
        on_log=lambda m: signals.log.emit(m),
        on_state=lambda r: signals.state.emit(r),
        on_otp=on_otp,
    )

    def executor_factory() -> TaskExecutor:
        data = config.data()
        return TaskExecutor(
            screenshot_dir=data.get("screenshot_dir", ""),
            apps_list=data.get("apps", []),
            wol_hosts=data.get("wol", []),
            logger=lambda m: channel_signals.log.emit(m),
            miot_factory=lambda: make_miio(config),
        )

    channel = MijiaChannel(
        config, executor_factory,
        on_log=lambda m: channel_signals.log.emit(m),
        on_state=lambda r: channel_signals.state.emit(r),
        on_trigger=lambda v, r, ok: channel_signals.trigger.emit(v, r, ok),
    )

    # 首次部署时先不显示主窗口，避免向导后面闪现
    start_minimized = bool(config.get("start_minimized", False)) or first_run
    window = MainWindow(config, bridge, signals, channel=channel,
                        channel_signals=channel_signals, start_minimized=start_minimized)
    otp_bridge.parent_widget = window
    otp_bridge.setParent(window)

    def _start_bridge() -> None:
        if config.get("xiaomi.username", ""):
            bridge.start()
        else:
            QMessageBox.information(window, "提示", "请先在「语音助手」页登录小米账号。")

    def _start_autos() -> None:
        if not config.get("xiaomi.username", ""):
            return
        if config.get("bridge.enabled", False):
            bridge.start()
        if config.get("mijia_channel.enabled", False):
            channel.start()

    window.start_requested.connect(_start_bridge)
    window.stop_requested.connect(bridge.stop)
    app.aboutToQuit.connect(bridge.stop)
    app.aboutToQuit.connect(channel.stop)

    if need_setup:
        wizard = SetupWizard(config)
        wizard.setWindowIcon(make_app_icon())
        accepted = wizard.exec() == SetupWizard.DialogCode.Accepted
        if not accepted and not config.get("setup_completed", False):
            window.tray.hide()
            return 0  # 用户中途取消且尚未完成部署，直接退出
        if not config.get("start_minimized", False):
            window.show_up()
        _start_autos()
    else:
        _start_autos()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())
