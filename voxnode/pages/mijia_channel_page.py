"""米家遥控页：把米家设备属性当作指令通道，用米家 App 控制这台电脑。"""
from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from miiotpcapi.config import Config
from miiotpcapi.tasks import ACTIONS

from ..bridge_signals import ChannelSignals
from ..ui import card, page
from ..workers import run_async
from .mijia_page import make_miio

# 适合作为「指令载体」的动作（不含高风险与需要额外配置的项）
SUGGESTED = [
    "shutdown", "restart", "lock", "sleep", "hibernate", "signout",
    "cancel_shutdown", "screenshot", "report_status", "wol", "volume", "media",
]


class MappingDialog(QDialog):
    def __init__(self, parent=None, mapping: dict | None = None, default_value: str = ""):
        super().__init__(parent)
        self.setWindowTitle("编辑映射" if mapping else "添加映射")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.value = QLineEdit(str(mapping.get("value", default_value)) if mapping else default_value)
        self.value.setPlaceholderText("属性取值，如 1 / 0 / on / 30")
        self.action = QComboBox()
        self.action.addItems(sorted(ACTIONS))
        if mapping:
            self.action.setCurrentText(mapping.get("action", "shutdown"))
        self.params = QLineEdit(json.dumps(mapping.get("params", {}), ensure_ascii=False) if mapping else "{}")
        self.params.setPlaceholderText('动作参数 JSON，如 {"delay": 60}')
        self.reply = QLineEdit(mapping.get("reply", "") if mapping else "")
        self.reply.setPlaceholderText("触发后的说明文字（可留空）")
        form.addRow("属性值", self.value)
        form.addRow("执行动作", self.action)
        form.addRow("动作参数", self.params)
        form.addRow("说明", self.reply)
        lay.addLayout(form)

        tip = QLabel("常用动作：" + "、".join(SUGGESTED))
        tip.setProperty("muted", True)
        tip.setWordWrap(True)
        lay.addWidget(tip)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _accept(self) -> None:
        if not self.value.text().strip():
            QMessageBox.warning(self, "提示", "属性值不能为空。")
            return
        try:
            params = json.loads(self.params.text().strip() or "{}")
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "参数格式错误", f"动作参数需要是 JSON 对象：{e}")
            return
        if not isinstance(params, dict):
            QMessageBox.warning(self, "参数格式错误", '动作参数需要是 JSON 对象，例如 {"delay": 60}')
            return
        self.accept()

    def values(self) -> dict:
        return {
            "value": self.value.text().strip(),
            "action": self.action.currentText(),
            "params": json.loads(self.params.text().strip() or "{}"),
            "reply": self.reply.text().strip(),
        }


class MijiaChannelPage(QFrame):
    def __init__(self, config: Config, channel, signals: ChannelSignals):
        super().__init__()
        self.config = config
        self.channel = channel
        _, lay = page(
            "米家遥控",
            "小米未开放个人虚拟设备，这里用米家设备的某个属性作为指令通道："
            "在米家 App 里做场景改这个属性，本机轮询到变化就执行动作",
            root=self,
        )

        # -- 绑定 ----------------------------------------------------------
        bind_card, bind_lay = card("1. 绑定米家设备与属性")
        row = QHBoxLayout()
        self.device = QComboBox()
        self.device.setMinimumWidth(240)
        btn_load = QPushButton("加载设备")
        btn_load.clicked.connect(self.load_devices)
        row.addWidget(QLabel("设备"))
        row.addWidget(self.device, 1)
        row.addWidget(btn_load)
        bind_lay.addLayout(row)

        row2 = QHBoxLayout()
        self.siid = QSpinBox(); self.siid.setRange(1, 99)
        self.piid = QSpinBox(); self.piid.setRange(1, 99)
        self.label = QLineEdit(); self.label.setPlaceholderText("属性名称，如 开关 / 亮度")
        self.interval = QDoubleSpinBox()
        self.interval.setRange(1.0, 60.0); self.interval.setSingleStep(0.5); self.interval.setSuffix(" 秒")
        btn_read = QPushButton("读取当前值")
        btn_read.clicked.connect(self._read_value)
        row2.addWidget(QLabel("siid")); row2.addWidget(self.siid)
        row2.addWidget(QLabel("piid")); row2.addWidget(self.piid)
        row2.addWidget(self.label, 1)
        row2.addWidget(QLabel("轮询")); row2.addWidget(self.interval)
        row2.addWidget(btn_read)
        bind_lay.addLayout(row2)

        self.current_value = QLabel("当前值：—")
        self.current_value.setProperty("accent", True)
        bind_lay.addWidget(self.current_value)
        lay.addWidget(bind_card)

        # -- 映射 ----------------------------------------------------------
        map_card, map_lay = card("2. 属性取值 → 电脑动作")
        bar = QHBoxLayout()
        btn_add = QPushButton("添加映射")
        btn_add.setProperty("kind", "primary")
        btn_add.clicked.connect(self._add_mapping)
        btn_edit = QPushButton("编辑")
        btn_edit.clicked.connect(self._edit_mapping)
        btn_del = QPushButton("删除")
        btn_del.setProperty("kind", "danger")
        btn_del.clicked.connect(self._del_mapping)
        bar.addWidget(btn_add)
        bar.addWidget(btn_edit)
        bar.addWidget(btn_del)
        bar.addStretch(1)
        map_lay.addLayout(bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["属性值", "执行动作", "动作参数", "说明"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        map_lay.addWidget(self.table)
        lay.addWidget(map_card, 2)

        # -- 运行 ----------------------------------------------------------
        run_card, run_lay = card("3. 启动遥控")
        run_row = QHBoxLayout()
        self.state_label = QLabel("已停止")
        btn_save = QPushButton("保存配置")
        btn_save.clicked.connect(lambda: self._save(notify=True))
        btn_start = QPushButton("保存并启动")
        btn_start.setProperty("kind", "primary")
        btn_start.clicked.connect(self._start)
        btn_stop = QPushButton("停止")
        btn_stop.clicked.connect(self._stop)
        run_row.addWidget(self.state_label)
        run_row.addStretch(1)
        run_row.addWidget(btn_save)
        run_row.addWidget(btn_start)
        run_row.addWidget(btn_stop)
        run_lay.addLayout(run_row)

        note = QLabel(
            "开机说明：电脑关机后本程序无法运行，因此「远程开机」需要硬件配合 —— "
            "用米家智能插座控制主机供电，并在主板 BIOS 开启「断电恢复后自动开机」；"
            "或使用米家开机卡。本页负责电脑已开机时的各类操作。"
        )
        note.setProperty("muted", True)
        note.setWordWrap(True)
        run_lay.addWidget(note)

        self.log_list = QListWidget()
        self.log_list.setMaximumHeight(150)
        run_lay.addWidget(self.log_list)
        lay.addWidget(run_card, 1)

        signals.log.connect(self._append_log)
        signals.state.connect(self._on_state)
        signals.trigger.connect(self._on_trigger)

        self._load_from_config()
        if config.get("mijia_channel.enabled", False) and config.get("setup_completed", False):
            self._start()

    # ----------------------------------------------------------------------
    def _load_from_config(self) -> None:
        cfg = self.config.get("mijia_channel", {}) or {}
        device = cfg.get("device") or {}
        prop = cfg.get("prop") or {}
        if device.get("name"):
            self.device.addItem(device["name"], device.get("did", ""))
        self.siid.setValue(int(prop.get("siid", 2)))
        self.piid.setValue(int(prop.get("piid", 1)))
        self.label.setText(prop.get("label", "开关"))
        self.interval.setValue(float(cfg.get("poll_interval", 3.0)))
        self._load_mappings()

    def _load_mappings(self) -> None:
        cfg = self.config.get("mijia_channel", {}) or {}
        self.table.setRowCount(0)
        for m in cfg.get("mappings", []) or []:
            r = self.table.rowCount()
            self.table.insertRow(r)
            values = [str(m.get("value", "")), m.get("action", ""),
                      json.dumps(m.get("params", {}), ensure_ascii=False),
                      m.get("reply", "")]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, c, item)

    def _save(self, notify: bool = False) -> bool:
        cfg = dict(self.config.get("mijia_channel", {}) or {})
        did = self.device.currentData() or ""
        cfg["device"] = {"did": did, "name": self.device.currentText()}
        cfg["prop"] = {"siid": self.siid.value(), "piid": self.piid.value(),
                       "label": self.label.text().strip() or f"{self.siid.value()}-{self.piid.value()}"}
        cfg["poll_interval"] = float(self.interval.value())
        self.config.set("mijia_channel", cfg)
        if notify:
            self._append_log("配置已保存")
            QMessageBox.information(self, "已保存", "米家遥控配置已保存。")
        return True

    # ----------------------------------------------------------------------
    def load_devices(self) -> None:
        self._append_log("正在加载米家设备…")

        def fetch():
            return make_miio(self.config).device_list_with_room()

        def on_done(devices):
            current = self.device.currentData()
            self.device.clear()
            for d in devices or []:
                label = d.get("name", d.get("did", ""))
                if d.get("room"):
                    label = f"{label}（{d['room']}）"
                self.device.addItem(label, d.get("did", ""))
                if d.get("did") == current:
                    self.device.setCurrentIndex(self.device.count() - 1)
            self._append_log(f"已加载 {self.device.count()} 台设备，请选择一台")

        def on_fail(err):
            self._append_log(f"加载失败：{err}")
            QMessageBox.warning(self, "加载米家设备失败", err)

        run_async(self, fetch, on_done, on_fail)

    def _read_value(self) -> None:
        did = self.device.currentData()
        if not did:
            QMessageBox.information(self, "提示", "请先加载并选择一台米家设备。")
            return
        siid, piid = self.siid.value(), self.piid.value()

        def do():
            return make_miio(self.config).get_prop(did, siid, piid)

        def on_done(value):
            self.current_value.setText(f"当前值：{value!r}")
            self._append_log(f"读取 siid={siid} piid={piid} → {value!r}")

        def on_fail(err):
            self._append_log(f"读取失败：{err}")

        run_async(self, do, on_done, on_fail)

    # ----------------------------------------------------------------------
    def _selected_mapping(self) -> tuple[int, dict] | None:
        rows = self.table.selectedIndexes()
        if not rows:
            return None
        r = rows[0].row()
        mappings = (self.config.get("mijia_channel", {}) or {}).get("mappings", [])
        if r >= len(mappings):
            return None
        return r, mappings[r]

    def _add_mapping(self) -> None:
        default = self.current_value.text().replace("当前值：", "").strip()
        if default in ("—", ""):
            default = ""
        dlg = MappingDialog(self, default_value=default)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cfg = dict(self.config.get("mijia_channel", {}) or {})
            mappings = list(cfg.get("mappings", []) or [])
            mappings.append(dlg.values())
            cfg["mappings"] = mappings
            self.config.set("mijia_channel", cfg)
            self._load_mappings()

    def _edit_mapping(self) -> None:
        sel = self._selected_mapping()
        if not sel:
            QMessageBox.information(self, "提示", "请先选中一条映射。")
            return
        r, mapping = sel
        dlg = MappingDialog(self, mapping)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cfg = dict(self.config.get("mijia_channel", {}) or {})
            mappings = list(cfg.get("mappings", []) or [])
            mappings[r] = dlg.values()
            cfg["mappings"] = mappings
            self.config.set("mijia_channel", cfg)
            self._load_mappings()

    def _del_mapping(self) -> None:
        sel = self._selected_mapping()
        if not sel:
            QMessageBox.information(self, "提示", "请先选中一条映射。")
            return
        r, _ = sel
        cfg = dict(self.config.get("mijia_channel", {}) or {})
        mappings = list(cfg.get("mappings", []) or [])
        mappings.pop(r)
        cfg["mappings"] = mappings
        self.config.set("mijia_channel", cfg)
        self._load_mappings()

    # ----------------------------------------------------------------------
    def _start(self) -> None:
        if not self.device.currentData():
            QMessageBox.information(self, "提示", "请先加载并选择一台米家设备。")
            return
        if not ((self.config.get("mijia_channel", {}) or {}).get("mappings")):
            QMessageBox.information(self, "提示", "请至少添加一条「属性值 → 动作」映射。")
            return
        self._save()
        self.config.set("mijia_channel.enabled", True)
        self.channel.start()

    def _stop(self) -> None:
        self.config.set("mijia_channel.enabled", False)
        self.channel.stop()

    def _on_state(self, running: bool) -> None:
        self.state_label.setText("运行中" if running else "已停止")
        self.state_label.setProperty("accent", running)

    def _on_trigger(self, value: str, reply: str, ok: bool) -> None:
        self._append_log(f"[{'✓' if ok else '✗'}] 属性值 {value} → {reply or '（无说明）'}")

    def _append_log(self, msg: str) -> None:
        from datetime import datetime
        self.log_list.insertItem(0, f"{datetime.now().strftime('%H:%M:%S')}  {msg}")
        while self.log_list.count() > 300:
            self.log_list.takeItem(self.log_list.count() - 1)

    def on_shown(self) -> None:
        self._load_from_config()
