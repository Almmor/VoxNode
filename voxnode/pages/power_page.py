"""电源控制：关机 / 重启 / 锁屏 / 睡眠 / 休眠 / 注销 / 定时关机 / 取消。"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSpinBox, QTimeEdit,
)

from miiotpcapi.config import Config
from miiotpcapi.core import power

from ..ui import card, page


class PowerPage(QFrame):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        _, lay = page("电源控制", "对小爱说「关机」「重启电脑」也能触发同样的操作", root=self)

        quick_card, quick_lay = card("快捷操作")
        grid = QGridLayout()
        grid.setSpacing(12)
        buttons: list[tuple[str, str, str, str]] = [
            ("锁屏", "立即锁定电脑", "lock", ""),
            ("睡眠", "进入低功耗待机", "sleep", ""),
            ("休眠", "内存写入磁盘后断电", "hibernate", ""),
            ("注销", "退出当前用户会话", "signout", ""),
        ]
        for i, (title, desc, action, kind) in enumerate(buttons):
            b = QPushButton(f"{title}\n{desc}")
            b.setMinimumHeight(72)
            if kind:
                b.setProperty("kind", kind)
            b.clicked.connect(lambda _, a=action, t=title: self._exec(a, t, 0))
            grid.addWidget(b, i // 4, i % 4)
        for c in range(4):
            grid.setColumnStretch(c, 1)
        quick_lay.addLayout(grid)
        lay.addWidget(quick_card)

        delay_card, delay_lay = card("延迟关机 / 重启")
        row = QHBoxLayout()
        row.setSpacing(10)
        self.delay = QSpinBox()
        self.delay.setRange(0, 3600)
        self.delay.setValue(int(config.get("power.default_delay", 60)))
        self.delay.setSuffix(" 秒")
        self.delay.setMinimumWidth(120)
        row.addWidget(QLabel("延迟"))
        row.addWidget(self.delay)
        btn_shutdown = QPushButton("延迟关机")
        btn_shutdown.setProperty("kind", "primary")
        btn_shutdown.clicked.connect(lambda: self._exec("shutdown", "关机", self.delay.value()))
        btn_restart = QPushButton("延迟重启")
        btn_restart.clicked.connect(lambda: self._exec("restart", "重启", self.delay.value()))
        row.addWidget(btn_shutdown)
        row.addWidget(btn_restart)
        row.addStretch(1)
        delay_lay.addLayout(row)
        lay.addWidget(delay_card)

        sched_card, sched_lay = card("定时关机（今日 HH:MM）")
        row2 = QHBoxLayout()
        row2.setSpacing(10)
        self.time = QTimeEdit()
        self.time.setDisplayFormat("HH:mm")
        self.time.setMinimumWidth(120)
        btn_sched = QPushButton("设定定时关机")
        btn_sched.setProperty("kind", "primary")
        btn_sched.clicked.connect(self._schedule)
        btn_cancel = QPushButton("取消已设定的关机")
        btn_cancel.setProperty("kind", "danger")
        btn_cancel.clicked.connect(self._cancel)
        row2.addWidget(self.time)
        row2.addWidget(btn_sched)
        row2.addWidget(btn_cancel)
        row2.addStretch(1)
        sched_lay.addLayout(row2)
        lay.addWidget(sched_card)

        tip = QLabel("提示：小爱语音「关机」默认 60 秒延迟，期间说「取消关机」即可撤销；延迟秒数可在「设置」中修改。")
        tip.setProperty("muted", True)
        lay.addWidget(tip)
        lay.addStretch(1)

    # ----------------------------------------------------------------------
    def _confirm(self, action: str, delay: int) -> bool:
        names = {"shutdown": "关机", "restart": "重启", "sleep": "睡眠",
                 "hibernate": "休眠", "signout": "注销", "lock": "锁屏"}
        name = names.get(action, action)
        delay_text = f"，{delay} 秒后执行" if delay and action in ("shutdown", "restart") else ""
        ret = QMessageBox.warning(
            self, "确认操作",
            f"确定要「{name}」{delay_text}吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return ret == QMessageBox.StandardButton.Yes

    def _exec(self, action: str, name: str, delay: int) -> None:
        if not self._confirm(action, delay):
            return
        try:
            power.execute(action, delay)
        except Exception as e:
            QMessageBox.critical(self, "执行失败", str(e))
            return
        if action in ("shutdown", "restart") and delay:
            QMessageBox.information(self, "已设定", f"{name}将在 {delay} 秒后执行，可点击「取消已设定的关机」撤销。")
        elif action in ("lock",):
            pass  # 锁屏后看不到提示

    def _schedule(self) -> None:
        hhmm = self.time.time().toString("HH:mm")
        if not self._confirm("shutdown", 0):
            return
        try:
            power.schedule_at(hhmm)
        except Exception as e:
            QMessageBox.critical(self, "执行失败", str(e))
            return
        QMessageBox.information(self, "已设定", f"已设定 {hhmm} 定时关机。")

    def _cancel(self) -> None:
        power.cancel()
        QMessageBox.information(self, "完成", "已取消所有待执行的关机 / 重启任务。")
