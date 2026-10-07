"""遥控台页：启用内置网页服务，用手机浏览器远程控制这台电脑。"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QSpinBox, QVBoxLayout,
)

from miiotpcapi.config import Config
from miiotpcapi.remote import RemoteServer

from ..bridge_signals import RemoteSignals
from ..ui import card, page


class RemotePage(QFrame):
    def __init__(self, config: Config, server: RemoteServer, signals: RemoteSignals):
        super().__init__()
        self.config = config
        self.server = server
        self.signals = signals
        _, lay = page(
            "遥控台",
            "用手机浏览器远程控制这台电脑；也可作为米家场景之外的完整遥控界面",
            root=self,
        )

        # -- 开关与端口 ----------------------------------------------------
        ctl_card, ctl_lay = card("服务")
        row = QHBoxLayout()
        self.chk_enable = QCheckBox("启用网页遥控台")
        self.chk_enable.setChecked(bool(config.get("remote.enabled", False)))
        self.chk_enable.stateChanged.connect(self._toggle)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(int(config.get("remote.port", 8765)))
        self.port.valueChanged.connect(self._on_port_changed)
        self.state_label = QLabel("已停止")
        row.addWidget(self.chk_enable)
        row.addStretch(1)
        row.addWidget(QLabel("端口"))
        row.addWidget(self.port)
        row.addWidget(self.state_label)
        ctl_lay.addLayout(row)

        warn = QLabel(
            "安全提示：所有请求都必须携带访问令牌，动作仅限白名单（电源 / 截屏 / 状态 / 音量 / "
            "媒体 / 已配置应用 / 唤醒目标）。请仅在内网使用；需要在外网访问时，"
            "建议通过 VPN（如 Tailscale、ZeroTier）接入，不要把端口直接映射到公网。"
        )
        warn.setProperty("muted", True)
        warn.setWordWrap(True)
        ctl_lay.addWidget(warn)
        lay.addWidget(ctl_card)

        # -- 访问地址 ------------------------------------------------------
        url_card, url_lay = card("访问地址（手机与电脑需在同一局域网）")
        self.url_list = QListWidget()
        self.url_list.setMaximumHeight(110)
        url_lay.addWidget(self.url_list)

        btn_row = QHBoxLayout()
        btn_copy = QPushButton("复制首个地址")
        btn_copy.setProperty("kind", "primary")
        btn_copy.clicked.connect(self._copy_first)
        btn_refresh = QPushButton("刷新地址")
        btn_refresh.clicked.connect(self._refresh_urls)
        btn_reset = QPushButton("重置访问令牌")
        btn_reset.setProperty("kind", "danger")
        btn_reset.clicked.connect(self._reset_token)
        btn_row.addWidget(btn_copy)
        btn_row.addWidget(btn_refresh)
        btn_row.addStretch(1)
        btn_row.addWidget(btn_reset)
        url_lay.addLayout(btn_row)

        self.token_label = QLabel("")
        self.token_label.setProperty("muted", True)
        self.token_label.setTextInteractionFlags(
            self.token_label.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse)
        url_lay.addWidget(self.token_label)
        lay.addWidget(url_card)

        tip = QLabel(
            "在手机上打开上面任一地址即可看到遥控界面：实时查看 CPU / 内存 / 磁盘，"
            "一键完成关机、重启、锁屏、截屏、查看屏幕、音量与播放控制、打开应用、唤醒其他电脑。"
        )
        tip.setProperty("muted", True)
        tip.setWordWrap(True)
        lay.addWidget(tip)

        # -- 日志 ----------------------------------------------------------
        log_card, log_lay = card("访问日志")
        self.log_list = QListWidget()
        self.log_list.setMaximumHeight(150)
        log_lay.addWidget(self.log_list)
        lay.addWidget(log_card, 1)

        signals.log.connect(self._append_log)
        signals.state.connect(self._on_state)

        self._refresh_urls()
        self._on_state(self.server.running)
        if self.config.get("remote.enabled", False) and not self.server.running:
            self._start()

    # ----------------------------------------------------------------------
    def _append_log(self, msg: str) -> None:
        from datetime import datetime
        self.log_list.insertItem(0, f"{datetime.now().strftime('%H:%M:%S')}  {msg}")
        while self.log_list.count() > 300:
            self.log_list.takeItem(self.log_list.count() - 1)

    def _set_state_text(self, running: bool) -> None:
        self.state_label.setText("运行中" if running else "已停止")
        self.state_label.setProperty("accent", running)

    def _on_state(self, running: bool) -> None:
        self._set_state_text(running)

    def _toggle(self, state: int) -> None:
        if state:
            self._start()
        else:
            self.config.set("remote.enabled", False)
            self.server.stop()
            self._set_state_text(False)

    def _start(self) -> None:
        self.config.set("remote.port", int(self.port.value()), save=False)
        self.config.set("remote.enabled", True)
        if self.server.start():
            self._set_state_text(True)
            self._refresh_urls()
        else:
            self.chk_enable.blockSignals(True)
            self.chk_enable.setChecked(False)
            self.chk_enable.blockSignals(False)
            self._set_state_text(False)
            QMessageBox.warning(self, "启动失败",
                                f"端口 {self.port.value()} 无法监听，请换一个端口后重试。")

    def _on_port_changed(self, value: int) -> None:
        self.config.set("remote.port", int(value))
        if self.server.running:
            self.server.stop()
            self._start()
        self._refresh_urls()

    def _refresh_urls(self) -> None:
        urls = self.server.urls()
        self.url_list.clear()
        for url in urls:
            self.url_list.addItem(QListWidgetItem(url))
        token = self.server.token
        self.token_label.setText(f"访问令牌：{token[:6]}…{token[-4:]}（已含在地址中）")

    def _copy_first(self) -> None:
        urls = self.server.urls()
        if not urls:
            return
        QApplication.clipboard().setText(urls[0])
        QMessageBox.information(self, "已复制", "访问地址已复制到剪贴板，发到手机上打开即可。")

    def _reset_token(self) -> None:
        ret = QMessageBox.question(
            self, "确认", "重置后旧链接会立即失效，需要重新复制新地址，确定继续？")
        if ret != QMessageBox.StandardButton.Yes:
            return
        self.server.reset_token()
        if self.server.running:
            self.server.stop()
            self._start()
        self._refresh_urls()

    def on_shown(self) -> None:
        self.chk_enable.setChecked(bool(self.config.get("remote.enabled", False)))
        self._set_state_text(self.server.running)
        self._refresh_urls()
