"""进程管理：搜索、刷新、结束进程。"""
from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QHeaderView, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from miiotpcapi.config import Config
from miiotpcapi.core import monitor

from ..ui import card, page


def _fmt_mb(n: float) -> str:
    return f"{n / 1024 ** 2:.0f} MB"


class ProcessesPage(QFrame):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        _, lay = page("进程管理", "按内存占用排序；部分系统进程需管理员权限才能结束", root=self)

        table_card, table_lay = card()
        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索进程名或用户…")
        self.search.setMinimumWidth(260)
        self.search.textChanged.connect(self._refresh)
        self.auto_refresh = QCheckBox("每 5 秒自动刷新")
        self.auto_refresh.setChecked(True)
        self.auto_refresh.stateChanged.connect(self._toggle_timer)
        btn_refresh = QPushButton("立即刷新")
        btn_refresh.clicked.connect(self._refresh)
        btn_kill = QPushButton("结束选中进程")
        btn_kill.setProperty("kind", "danger")
        btn_kill.clicked.connect(self._kill_selected)
        bar.addWidget(self.search)
        bar.addStretch(1)
        bar.addWidget(self.auto_refresh)
        bar.addWidget(btn_refresh)
        bar.addWidget(btn_kill)
        table_lay.addLayout(bar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["PID", "进程名", "用户", "内存", "CPU %"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 80)
        table_lay.addWidget(self.table)
        lay.addWidget(table_card, 1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(5000)
        self._refresh()

    def _toggle_timer(self, state: int) -> None:
        if state:
            self._timer.start(5000)
        else:
            self._timer.stop()

    def _refresh(self) -> None:
        keyword = self.search.text().strip()
        self.table.setRowCount(0)
        for p in monitor.processes(keyword)[:300]:
            r = self.table.rowCount()
            self.table.insertRow(r)
            values = [str(p["pid"]), p["name"], p["username"], _fmt_mb(p["mem"]), f"{p['cpu']:.0f}"]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, p["pid"])
                self.table.setItem(r, c, item)

    def _kill_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要结束的进程。")
            return
        info = []
        for r in rows:
            name = self.table.item(r, 1).text()
            pid = self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)
            info.append((pid, name))
        names = "、".join(n for _, n in info)
        ret = QMessageBox.warning(
            self, "确认结束进程",
            f"确定要结束 {len(info)} 个进程（{names}）吗？\n强行结束可能导致未保存的数据丢失。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        failed = []
        for pid, name in info:
            try:
                monitor.kill(pid)
            except Exception as e:
                failed.append(f"{name}: {e}")
        self._refresh()
        if failed:
            QMessageBox.warning(self, "部分失败", "\n".join(failed))

    def on_shown(self) -> None:
        self._refresh()
