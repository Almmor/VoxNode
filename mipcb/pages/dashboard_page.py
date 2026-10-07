"""仪表盘：CPU / 内存 / 磁盘实时状态 + 系统信息。"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHeaderView, QLabel, QProgressBar, QTableWidget, QTableWidgetItem,
)

from miiotpcapi.config import Config
from miiotpcapi.core import monitor, sysinfo

from ..ui import card, kv_row, page


def _fmt_gb(n: float) -> str:
    return f"{n / 1024 ** 3:.1f} GB"


class GaugeCard:
    """一个大指标卡片（标题 + 大数字 + 进度条）。"""

    def __init__(self, title: str):
        self.frame, lay = card(title)
        self.value = QLabel("--")
        self.value.setProperty("h1", True)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        lay.addWidget(self.value)
        lay.addWidget(self.bar)

    def update(self, percent: float, text: str) -> None:
        self.value.setText(text)
        self.bar.setValue(int(percent))


class DashboardPage(QFrame):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        lay = self._build()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(2000)
        self.refresh()

    def _build(self) -> None:
        _, lay = page("仪表盘", "本机实时状态一览", root=self)

        self.cpu = GaugeCard("处理器 CPU")
        self.mem = GaugeCard("内存")
        self.disk = GaugeCard("系统盘 C:")
        self.up = GaugeCard("运行时长")

        grid = QGridLayout()
        grid.setSpacing(14)
        for i, g in enumerate([self.cpu, self.mem, self.disk, self.up]):
            grid.addWidget(g.frame, 0, i)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        lay.addLayout(grid)

        info_card, info_lay = card("系统信息")
        self._info_labels: dict[str, QLabel] = {}
        gl = QGridLayout()
        gl.setSpacing(8)
        names = {
            "hostname": "主机名", "os": "操作系统", "cpu_model": "处理器",
            "cpu_cores": "逻辑核心", "mem_total_gb": "内存容量", "boot_time": "开机时间",
        }
        for row, key in enumerate(names):
            k, v = kv_row(names[key])
            self._info_labels[key] = v
            gl.addWidget(k, row, 0)
            gl.addWidget(v, row, 1)
        gl.setColumnStretch(1, 1)
        info_lay.addLayout(gl)
        lay.addWidget(info_card, 1)

        net_card, net_lay = card("网络接口（用于 WOL 配置）")
        self.net_table = QTableWidget(0, 3)
        self.net_table.setHorizontalHeaderLabels(["名称", "IPv4", "MAC"])
        self.net_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.net_table.verticalHeader().setVisible(False)
        self.net_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        net_lay.addWidget(self.net_table)
        lay.addWidget(net_card, 1)

    def refresh(self) -> None:
        s = sysinfo.summary()
        self.cpu.update(s["cpu_percent"], f"{s['cpu_percent']:.0f}%")
        self.mem.update(s["mem_percent"], f"{s['mem_percent']:.0f}%（{_fmt_gb(s['mem_used_gb'])} / {s['mem_total_gb']} GB）")
        try:
            d = monitor.disk_usage("C:\\")
            self.disk.update(d["percent"], f"{d['percent']:.0f}%（{_fmt_gb(d['used'])} / {_fmt_gb(d['total'])}）")
        except Exception:
            self.disk.update(0, "不可用")
        self.up.update(0, s["uptime"])

        self._info_labels["hostname"].setText(s["hostname"])
        self._info_labels["os"].setText(s["os"])
        self._info_labels["cpu_model"].setText(s["cpu_model"])
        self._info_labels["cpu_cores"].setText(f"{s['cpu_cores']} 核心")
        self._info_labels["mem_total_gb"].setText(f"{s['mem_total_gb']} GB")
        self._info_labels["boot_time"].setText(s["boot_time"])

        ifaces = sysinfo.interfaces()
        self.net_table.setRowCount(0)
        for itf in ifaces:
            r = self.net_table.rowCount()
            self.net_table.insertRow(r)
            for c, v in enumerate([itf["name"], itf["ipv4"], itf["mac"]]):
                item = QTableWidgetItem(v)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.net_table.setItem(r, c, item)

    def on_shown(self) -> None:
        self.refresh()
