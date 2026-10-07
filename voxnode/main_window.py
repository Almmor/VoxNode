"""主窗口：侧边栏导航 + 各功能页 + 系统托盘。"""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from miiotpcapi import APP_NAME, APP_NAME_ZH, __version__
from miiotpcapi.config import Config
from miiotpcapi.xiaomi.bridge import XiaoaiBridge

from .bridge_signals import BridgeSignals, ChannelSignals, RemoteSignals
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


def make_app_icon() -> QIcon:
    """运行时绘制应用图标（橙色圆角方块 + Mi 字样），无需资源文件。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#ff6900"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 16, 16)
    p.setPen(QColor("#ffffff"))
    f = QFont("Segoe UI", 22, QFont.Weight.Bold)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "Mi")
    p.end()
    return QIcon(pm)


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
        self.resize(1120, 720)
        self.setMinimumSize(QSize(960, 640))

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setCentralWidget(root)

        # -- 侧边栏 --------------------------------------------------------
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 16, 0, 12)
        side.setSpacing(4)

        logo = QLabel(f"  {APP_NAME}")
        logo.setProperty("h1", True)
        logo.setProperty("accent", True)
        sub = QLabel("  " + APP_NAME_ZH)
        sub.setProperty("muted", True)
        side.addWidget(logo)
        side.addWidget(sub)
        side.addSpacing(14)

        self.nav = QListWidget()
        self.nav.setObjectName("navList")
        for title, key in NAV:
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._on_nav)
        side.addWidget(self.nav, 1)

        self.status_label = QLabel("  小爱桥接：未知")
        self.status_label.setProperty("muted", True)
        side.addWidget(self.status_label)
        layout.addWidget(sidebar)

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

        # -- 桥接信号 --------------------------------------------------------
        signals.state.connect(self._on_bridge_state)
        signals.log.connect(lambda msg: None)

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
        self.tray.activated.connect(
            lambda reason: self.show_up()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick
            else None
        )
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

    def _on_nav(self, row: int) -> None:
        key = self.nav.item(row).data(Qt.ItemDataRole.UserRole)
        page = self.pages.get(key)
        if page:
            self.stack.setCurrentWidget(page)
            if hasattr(page, "on_shown"):
                page.on_shown()

    def _on_bridge_state(self, running: bool) -> None:
        text = "运行中" if running else "已停止"
        self.status_label.setText(f"  小爱桥接：{text}")
        self.status_label.setProperty("accent", running)

    def closeEvent(self, event) -> None:
        """点关闭按钮时最小化到托盘，真正退出走托盘菜单。"""
        if self._first_close:
            self._first_close = False
            self.tray.showMessage(
                APP_NAME,
                "已最小化到系统托盘，右键托盘图标可退出",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        event.ignore()
        self.hide()
