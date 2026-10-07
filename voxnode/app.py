"""应用入口：首次运行走引导式部署向导，之后直接进入主界面。"""
from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication, QMessageBox

from miiotpcapi import APP_NAME
from miiotpcapi.config import Config
from miiotpcapi.core import screenshot as screenshot_core
from miiotpcapi.remote import RemoteServer
from miiotpcapi.tasks import TaskExecutor, executor_from_config
from miiotpcapi.xiaomi.bridge import XiaoaiBridge
from miiotpcapi.xiaomi.channel import MijiaChannel

from .bridge_signals import BridgeSignals, ChannelSignals, OtpBridge, RemoteSignals, ask_otp
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

        # 遥控台：真实起服务并验证鉴权
        import json as _json
        import urllib.error
        import urllib.request

        from miiotpcapi.remote import RemoteServer
        from miiotpcapi.tasks import TaskExecutor as _TE
        remote_cfg = Config(path=Path(tempfile.gettempdir()) / "voxnode_selftest_remote.json")
        remote_cfg.set("remote.port", 0, save=False)      # 端口交给系统分配，避免被占用
        rsrv = RemoteServer(remote_cfg, lambda: _TE())
        assert rsrv.start(), "遥控台启动失败"
        try:
            base = f"http://127.0.0.1:{rsrv.port}"
            with urllib.request.urlopen(f"{base}/api/status?t={rsrv.token}", timeout=5) as r:
                payload = _json.loads(r.read())
            assert payload.get("ok"), payload
            code = 0
            try:
                urllib.request.urlopen(f"{base}/api/status", timeout=5)
            except urllib.error.HTTPError as e:
                code = e.code
            assert code == 401, f"无令牌应返回 401，实际 {code}"
            with urllib.request.urlopen(f"{base}/?t={rsrv.token}", timeout=5) as r:
                page = r.read().decode("utf-8")
            assert "VoxNode" in page and "__TOKEN__" not in page
            # 手机 App 靠这两组数据建立本地唤醒设备
            with urllib.request.urlopen(f"{base}/api/config?t={rsrv.token}", timeout=5) as r:
                cfg_payload = _json.loads(r.read())
            assert "wol_targets" in cfg_payload and "macs" in cfg_payload, cfg_payload.keys()
            lines.append(
                f"remote=ok(host={payload.get('hostname')}, auth=401, page=ok, "
                f"nics={len(cfg_payload['macs'])})"
            )
        finally:
            rsrv.stop()

        # 界面：主窗口各页 + 向导 5 页
        tmp_cfg = Path(tempfile.gettempdir()) / "voxnode_selftest_cfg.json"
        cfg = Config(path=tmp_cfg)
        from miiotpcapi.tasks import TaskExecutor
        from miiotpcapi.xiaomi.bridge import XiaoaiBridge
        from miiotpcapi.xiaomi.channel import MijiaChannel

        from .bridge_signals import ChannelSignals, RemoteSignals
        from .bridge_signals import BridgeSignals as _BS
        from .main_window import MainWindow
        from .wizard import SetupWizard

        signals = _BS()
        chan_signals = ChannelSignals()
        remote_signals = RemoteSignals()
        bridge = XiaoaiBridge(cfg)
        channel = MijiaChannel(cfg, lambda: TaskExecutor(), on_log=lambda m: None)
        remote = RemoteServer(cfg, lambda: TaskExecutor(), on_log=lambda m: None)
        win = MainWindow(cfg, bridge, signals, channel=channel,
                         channel_signals=chan_signals,
                         remote=remote, remote_signals=remote_signals,
                         start_minimized=True)
        for i in range(win.nav.count()):
            win.nav.setCurrentRow(i)
            app.processEvents()
        lines.append(f"main_window_pages={win.stack.count()}")

        # 顶部自定义导航栏：入口数 = 页面数 = 自制 SVG 图标数，且图标真的渲染出内容
        from . import icons as _icons
        from . import theme as _theme
        from .main_window import NAV as _NAV

        assert win.nav.count() == len(_NAV) == win.stack.count(), (
            win.nav.count(), len(_NAV), win.stack.count())
        missing_svg = [k for _, k in _NAV if not _icons.icon_path(k).is_file()]
        assert not missing_svg, f"缺少自制 SVG 图标：{missing_svg}"
        blank = [b.icon_name for b in win.nav.buttons if b._pix_off.isNull()]
        assert not blank, f"这些导航图标渲染为空：{blank}"
        lines.append(f"top_nav=ok(items={win.nav.count()}, svg={len(_icons.ICON_NAMES)})")

        # 换强调色：调色板、QSS 与导航栏图标都要跟着变，切回来也要能还原
        for accent in ("violet", "blue", "green", "magenta", "orange"):
            _theme.set_theme(accent=accent)
            app.processEvents()
            assert _theme.current_palette()["accent"] == _theme.ACCENTS[accent][0]
            assert _theme.ACCENTS[accent][0] in app.styleSheet()
        assert _theme.current_accent() == "orange"
        _theme.set_theme(scale=1.25)
        app.processEvents()
        _theme.set_theme(scale=1.0)
        app.processEvents()
        lines.append("theme_switch=ok")

        # 设置页：新增的设置分组控件都在
        settings = win.pages["settings"]
        for attr in ("_swatches", "cmb_scale", "chk_nav_labels", "chk_autostart",
                     "chk_minimized", "cmb_close", "cmb_tray", "chk_notify",
                     "spn_delay", "chk_confirm", "chk_block", "cmb_format", "spn_clean"):
            assert hasattr(settings, attr), f"设置页缺少控件 {attr}"
        lines.append("settings_page=ok(groups=5)")

        # 导航栏文字开关要真的作用到按钮上
        win.nav.set_labels_enabled(False)
        app.processEvents()
        assert all(not b.shows_label() for b in win.nav.buttons), "关闭文字后仍有按钮显示标签"
        win.nav.set_labels_enabled(True)
        app.processEvents()
        lines.append("nav_label_toggle=ok")

        wiz = SetupWizard(cfg)
        ids = wiz.pageIds()
        for pid in ids:
            wiz.setCurrentId(pid)
            app.processEvents()
        lines.append(f"wizard_pages={len(ids)}")
        win.tray.hide()
        win.hide()
        remote.stop()
        for leftover in (tmp_cfg, remote_cfg.path):
            if leftover.exists():
                leftover.unlink()
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
    app.setQuitOnLastWindowClosed(False)  # 关闭主窗口时驻留系统托盘

    config = Config()
    # 主题从配置读：强调色与界面缩放在「设置 → 外观」里改过就要延续
    apply_theme(app, str(config.get("ui.accent", "orange")),
                float(config.get("ui.scale", 1.0)))
    app.setWindowIcon(make_app_icon())

    # 启动时按设置清理过期截图（0 = 不清理）
    try:
        screenshot_core.cleanup(config.get("screenshot_dir", ""),
                                config.get("screenshot.auto_clean_days", 0))
    except Exception:
        pass

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
        # 截图格式与危险操作策略统一从配置读，三个入口（语音 / 米家 / 遥控台）一致
        return executor_from_config(
            config,
            logger=lambda m: channel_signals.log.emit(m),
            miot_factory=lambda: make_miio(config),
        )

    channel = MijiaChannel(
        config, executor_factory,
        on_log=lambda m: channel_signals.log.emit(m),
        on_state=lambda r: channel_signals.state.emit(r),
        on_trigger=lambda v, r, ok: channel_signals.trigger.emit(v, r, ok),
    )

    remote_signals = RemoteSignals()
    remote = RemoteServer(
        config, executor_factory,
        on_log=lambda m: remote_signals.log.emit(m),
    )

    # 首次部署时先不显示主窗口，避免向导后面闪现
    start_minimized = bool(config.get("start_minimized", False)) or first_run
    window = MainWindow(config, bridge, signals, channel=channel,
                        channel_signals=channel_signals,
                        remote=remote, remote_signals=remote_signals,
                        start_minimized=start_minimized)
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
    app.aboutToQuit.connect(remote.stop)

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
