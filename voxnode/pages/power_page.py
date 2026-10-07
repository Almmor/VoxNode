"""电源控制：关机 / 重启 / 锁屏 / 睡眠 / 休眠 / 注销 / 定时关机 / 取消。

危险动作（关机 / 重启 / 休眠 / 注销 / 睡眠）受「设置 → 电源与安全」约束：
  - 关闭「二次确认」后不再弹确认框
  - 打开「禁止危险操作」后按钮直接置灰，点了也会被拦下
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSpinBox, QTimeEdit,
)

from miiotpcapi.config import Config
from miiotpcapi.core import power

from ..ui import card, confirm_dangerous, dangerous_blocked, page

ACTION_NAMES = {
    "shutdown": "关机", "restart": "重启", "sleep": "睡眠",
    "hibernate": "休眠", "signout": "注销", "lock": "锁屏",
}


class PowerPage(QFrame):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        # 受安全策略约束的按钮（锁屏与取消关机不在其中）
        self._guarded: list[QPushButton] = []

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
            if action in ACTION_NAMES and action != "lock":
                self._guarded.append(b)
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
        self.delay.valueChanged.connect(
            lambda v: self.config.set("power.default_delay", int(v)))
        row.addWidget(QLabel("延迟"))
        row.addWidget(self.delay)
        btn_shutdown = QPushButton("延迟关机")
        btn_shutdown.setProperty("kind", "primary")
        btn_shutdown.clicked.connect(lambda: self._exec("shutdown", "关机", self.delay.value()))
        btn_restart = QPushButton("延迟重启")
        btn_restart.clicked.connect(lambda: self._exec("restart", "重启", self.delay.value()))
        self._guarded += [btn_shutdown, btn_restart]
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
        self._guarded.append(btn_sched)
        row2.addWidget(self.time)
        row2.addWidget(btn_sched)
        row2.addWidget(btn_cancel)
        row2.addStretch(1)
        sched_lay.addLayout(row2)
        lay.addWidget(sched_card)

        self.tip = QLabel("")
        self.tip.setProperty("muted", True)
        self.tip.setWordWrap(True)
        lay.addWidget(self.tip)
        lay.addStretch(1)

        self._apply_safety()

    # ----------------------------------------------------------------------
    def _apply_safety(self) -> None:
        """按安全设置同步按钮可用状态与提示文案。"""
        blocked = bool(self.config.get("safety.block_dangerous", False))
        confirm = bool(self.config.get("safety.confirm_dangerous", True))
        for b in self._guarded:
            b.setEnabled(not blocked)

        if blocked:
            self.tip.setText(
                "危险操作已被禁止（设置 → 电源与安全）。锁屏与「取消已设定的关机」仍然可用。")
            self.tip.setProperty("accent", True)
        else:
            note = "执行前会二次确认" if confirm else "已关闭二次确认，点了就直接执行"
            self.tip.setText(
                f"提示：语音「关机」默认 {int(self.config.get('power.default_delay', 60))} 秒延迟，"
                f"期间说「取消关机」即可撤销；{note}。")
            self.tip.setProperty("accent", False)
        self.tip.style().unpolish(self.tip)
        self.tip.style().polish(self.tip)

    def _exec(self, action: str, name: str, delay: int) -> None:
        if dangerous_blocked(self, self.config):
            return
        extra = f"，{delay} 秒后执行" if delay and action in ("shutdown", "restart") else ""
        if not confirm_dangerous(self, ACTION_NAMES.get(action, name), self.config, extra):
            return
        try:
            power.execute(action, delay)
        except Exception as e:
            QMessageBox.critical(self, "执行失败", str(e))
            return
        if action in ("shutdown", "restart") and delay:
            QMessageBox.information(self, "已设定",
                                    f"{name}将在 {delay} 秒后执行，可点击「取消已设定的关机」撤销。")

    def _schedule(self) -> None:
        if dangerous_blocked(self, self.config):
            return
        hhmm = self.time.time().toString("HH:mm")
        if not confirm_dangerous(self, "定时关机", self.config, f"，{hhmm} 执行"):
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

    def on_shown(self) -> None:
        """从设置页改完延时或安全策略后，切回本页要能看到最新状态。"""
        value = int(self.config.get("power.default_delay", 60))
        if self.delay.value() != value:
            self.delay.blockSignals(True)
            self.delay.setValue(value)
            self.delay.blockSignals(False)
        self._apply_safety()
