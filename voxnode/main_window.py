"""主窗口：顶部自定义导航栏 + 各功能页 + 系统托盘。"""
from __future__ import annotations

from PyQt6.QtCore import QSize, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QMainWindow, QMenu, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from miiotpcapi import APP_NAME, APP_NAME_ZH, branding, __version__
from miiotpcapi.config import Config
from miiotpcapi.xiaomi.bridge import XiaoaiBridge

from . import theme
from .bridge_signals import BridgeSignals, ChannelSignals, RemoteSignals
from .navbar import TopNavBar
from .pages.apps_page import AppsPage
from .pages.assistant_page import AssistantPage
from .pages.dashboard_page import DashboardPage
from .pages.mijia_channel_page import MijiaChannelPage
from .pages.mijia_page import MijiaPage
from .pages.power_page import PowerPage
from .pages.processes_page import ProcessesPage
from .pages.remote_page import RemotePage
from .pages.screenshot_page import ScreenshotPage
from .pages.settings_page import SettingsPage
from .pages.wol_page import WolPage


def make_app_icon(accent: str | None = None) -> QIcon:
    """应用图标：复用品牌绘制逻辑（圆角方块 + 显示器），随强调色变化。"""
    color = accent or theme.current_palette()["accent"]
    pm = QPixmap()
    pm.loadFromData(branding.render_png(128, background=color), "PNG")
    return QIcon(pm)


# 导航项：(标题, key)。key 同时就是 voxnode/assets/icons/<key>.svg 的文件名。
NAV = [
    ("仪表盘", "dashboard"),
    ("电源控制", "power"),
    ("屏幕截取", "screenshot"),
    ("进程管理", "processes"),
    ("应用任务", "apps"),
    ("网络唤醒", "wol"),
    ("米家设备", "mijia"),
    ("米家遥控", "mijia_channel"),
    ("遥控台", "remote"),
    ("语音助手", "assistant"),
    ("设置", "settings"),
]


class MainWindow(QMainWindow):
    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self, config: Config, bridge: XiaoaiBridge, signals: BridgeSignals,
                 channel=None, channel_signals: ChannelSignals | None = None,
                 remote=None, remote_signals: RemoteSignals | None = None,
                 start_minimized: bool = False):
        super().__init__()
        self.config = config
        self.bridge = bridge
        self.signals = signals
        self.channel = channel
        self.channel_signals = channel_signals or ChannelSignals(self)
        self.remote = remote
        self.remote_signals = remote_signals or RemoteSignals(self)
        self._first_close = True

        self.setWindowTitle(f"{APP_NAME} — {APP_NAME_ZH} v{__version__}")
        self.setWindowIcon(make_app_icon())
        self.resize(1180, 760)
        self.setMinimumSize(QSize(900, 620))

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(root)

        # -- 顶部自定义导航栏 ------------------------------------------------
        self.nav = TopNavBar(NAV)
        self.nav.set_labels_enabled(bool(config.get("ui.nav_labels", True)))
        self.nav.currentChanged.connect(self._on_nav)
        layout.addWidget(self.nav)

        # -- 页面区 ----------------------------------------------------------
        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {
            "dashboard": DashboardPage(config),
            "power": PowerPage(config),
            "screenshot": ScreenshotPage(config),
            "processes": ProcessesPage(config),
            "apps": AppsPage(config),
            "wol": WolPage(config),
            "mijia": MijiaPage(config),
            "mijia_channel": MijiaChannelPage(config, self.channel, self.channel_signals),
            "remote": RemotePage(config, self.remote, self.remote_signals),
            "assistant": AssistantPage(config, bridge, signals),
            "settings": SettingsPage(config),
        }
        for _, key in NAV:
            self.stack.addWidget(self.pages[key])
        layout.addWidget(self.stack, 1)
        self.nav.setCurrentRow(0)   # 触发 _on_nav(0)，让首页 on_shown 也跑一次

        # -- 桥接信号 --------------------------------------------------------
        signals.state.connect(self._on_bridge_state)
        signals.log.connect(lambda msg: None)

        # 换主题时导航栏图标要重新染色，窗口图标也要跟着换
        theme.theme_bus.changed.connect(self._on_theme_changed)

        # -- 托盘 ------------------------------------------------------------
        self.tray = QSystemTrayIcon(make_app_icon(), self)
        self.tray.setToolTip(f"{APP_NAME} — {APP_NAME_ZH}")
        menu = QMenu()
        act_show = QAction("显示主界面", self)
        act_show.triggered.connect(self.show_up)
        act_start = QAction("启动小爱桥接", self)
        act_start.triggered.connect(self.start_requested.emit)
        act_stop = QAction("停止小爱桥接", self)
        act_stop.triggered.connect(self.stop_requested.emit)
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_show)
        menu.addSeparator()
        menu.addAction(act_start)
        menu.addAction(act_stop)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

        if start_minimized:
            self.hide()
        else:
            self.show()

    # ----------------------------------------------------------------------
    def show_up(self) -> None:
        self.showNormal()
        self.activateWindow()

    def quit_app(self) -> None:
        self.tray.hide()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()

    # ---------------------------------------------------------------- 导航
    def _on_nav(self, row: int) -> None:
        key = self.nav.rowKey(row)
        page = self.pages.get(key)
        if page:
            self.stack.setCurrentWidget(page)
            if hasattr(page, "on_shown"):
                page.on_shown()

    # ---------------------------------------------------------------- 主题
    def _on_theme_changed(self, _palette: dict) -> None:
        self.nav.refresh_theme()
        icon = make_app_icon()
        self.setWindowIcon(icon)
        self.tray.setIcon(icon)
        if hasattr(self.pages.get("settings"), "sync_theme_controls"):
            self.pages["settings"].sync_theme_controls()

    # ---------------------------------------------------------------- 通知
    def notify(self, title: str, message: str, msec: int = 3500) -> None:
        """桌面通知；在设置里关掉通知后静默跳过。"""
        if not bool(self.config.get("ui.notifications", True)):
            return
        self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, msec)

    # ---------------------------------------------------------------- 状态
    def _on_bridge_state(self, running: bool) -> None:
        self.nav.status.set_state(running)

    # ---------------------------------------------------------------- 托盘
    def _on_tray_activated(self, reason) -> None:
        if reason != QSystemTrayIcon.ActivationReason.DoubleClick:
            return
        if self.config.get("ui.tray_double_click", "show") == "toggle_bridge":
            if self.bridge and getattr(self.bridge, "running", False):
                self.stop_requested.emit()
                self.notify(APP_NAME, "已停止小爱桥接")
            else:
                self.start_requested.emit()
                self.notify(APP_NAME, "正在启动小爱桥接")
        else:
            self.show_up()

    def closeEvent(self, event) -> None:  # noqa: N802
        """按设置决定：最小化到托盘，还是直接退出。"""
        if self.config.get("ui.close_action", "tray") == "quit":
            self.quit_app()
            return
        if self._first_close:
            self._first_close = False
            self.notify(APP_NAME, "已最小化到系统托盘，右键托盘图标可退出", 3000)
        event.ignore()
        self.hide()
