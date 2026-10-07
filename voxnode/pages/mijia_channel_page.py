"""米家遥控页：把米家设备属性当作指令通道，用米家 App 控制这台电脑。

小米不开放个人把自定义设备加入米家 App，因此这里的做法是：
  用一台已有米家设备当「遥控器」，在米家 App 里建手动场景去改它的属性，
  本机轮询到属性变化后执行对应动作。米家 App 里的场景按钮就是遥控界面。
"""
from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from miiotpcapi.config import Config
from miiotpcapi.tasks import ACTIONS

from ..bridge_signals import ChannelSignals
from ..ui import card, page
from ..workers import run_async
from .mijia_page import make_miio

SUGGESTED = [
    "shutdown", "restart", "lock", "sleep", "hibernate", "signout",
    "cancel_shutdown", "screenshot", "report_status", "wol", "volume", "media",
]

ACTION_LABEL = {
    "shutdown": "关机", "restart": "重启", "lock": "锁屏", "sleep": "睡眠",
    "hibernate": "休眠", "signout": "注销", "cancel_shutdown": "取消关机",
    "screenshot": "截屏", "report_status": "语音播报状态", "wol": "唤醒其他设备",
    "volume": "音量", "media": "播放控制", "open_app": "打开应用", "miot_power": "控制米家设备",
}


# ---------------------------------------------------------------- 编辑对话框
class MappingDialog(QDialog):
    def __init__(self, parent=None, mapping: dict | None = None,
                 default_value: str = "", prop_count: int = 1):
        super().__init__(parent)
        self.setWindowTitle("编辑映射" if mapping else "添加映射")
        self.setMinimumWidth(470)
        self.prop_count = max(1, prop_count)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.value = QLineEdit(str(mapping.get("value", default_value)) if mapping else default_value)
        hint = "，" if self.prop_count == 1 else "（多个属性用逗号分隔，如 1,0）"
        self.value.setPlaceholderText(f"属性取值{hint}")
        self.action = QComboBox()
        self.action.addItems(sorted(ACTIONS))
        if mapping:
            self.action.setCurrentText(mapping.get("action", "shutdown"))
        self.params = QLineEdit(
            json.dumps(mapping.get("params", {}), ensure_ascii=False) if mapping else "{}")
        self.params.setPlaceholderText('动作参数 JSON，如 {"delay": 60}')
        self.reply = QLineEdit(mapping.get("reply", "") if mapping else "")
        self.reply.setPlaceholderText("触发后的说明文字（可留空）")
        form.addRow("属性取值", self.value)
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
        raw = self.value.text().strip()
        if not raw:
            QMessageBox.warning(self, "提示", "属性值不能为空。")
            return
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) != self.prop_count:
            QMessageBox.warning(
                self, "提示",
                f"已绑定 {self.prop_count} 个属性，取值需要 {self.prop_count} 段（用逗号分隔）。")
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
            "value": ",".join(p.strip() for p in self.value.text().split(",")),
            "action": self.action.currentText(),
            "params": json.loads(self.params.text().strip() or "{}"),
            "reply": self.reply.text().strip(),
        }


# ---------------------------------------------------------------- 场景指引
class GuideDialog(QDialog):
    """告诉用户在米家 App 里怎么建"手动场景"当遥控按钮。"""

    def __init__(self, parent, text: str):
        super().__init__(parent)
        self.setWindowTitle("在米家 App 里创建遥控按钮")
        self.setMinimumSize(640, 520)
        lay = QVBoxLayout(self)
        view = QTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        lay.addWidget(view)
        row = QHBoxLayout()
        btn_copy = QPushButton("复制全文")
        btn_copy.setProperty("kind", "primary")
        btn_copy.clicked.connect(lambda: (QGuiApplication.clipboard().setText(text),
                                          btn_copy.setText("已复制")))
        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        row.addWidget(btn_copy)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)


# ---------------------------------------------------------------- 页面
class MijiaChannelPage(QFrame):
    def __init__(self, config: Config, channel, signals: ChannelSignals):
        super().__init__()
        self.config = config
        self.channel = channel
        _, lay = page(
            "米家遥控",
            "用一台已有米家设备当遥控器：在米家 App 建手动场景改它的属性，"
            "本机轮询到变化就执行动作。米家 App 里的场景按钮就是遥控界面",
            root=self,
        )

        # -- 1. 绑定设备 ----------------------------------------------------
        bind_card, bind_lay = card("1. 绑定设备")
        row = QHBoxLayout()
        self.device = QComboBox()
        self.device.setMinimumWidth(240)
        btn_load = QPushButton("加载米家设备")
        btn_load.clicked.connect(self.load_devices)
        row.addWidget(QLabel("设备"))
        row.addWidget(self.device, 1)
        row.addWidget(btn_load)
        bind_lay.addLayout(row)
        hint = QLabel(
            "建议选「多键开关」或「可单独分孔的插排」这类能独立控制多路的设备，"
            "每多一路就能多表达一倍指令；也可用可调灯，亮度 1~100 相当于 100 档。"
        )
        hint.setProperty("muted", True)
        hint.setWordWrap(True)
        bind_lay.addWidget(hint)
        lay.addWidget(bind_card)

        # -- 2. 属性 --------------------------------------------------------
        prop_card, prop_lay = card("2. 作为指令载体的属性（可加多个做组合编码）")
        bar = QHBoxLayout()
        btn_add_prop = QPushButton("添加属性")
        btn_add_prop.setProperty("kind", "primary")
        btn_add_prop.clicked.connect(self._add_prop)
        btn_edit_prop = QPushButton("编辑")
        btn_edit_prop.clicked.connect(self._edit_prop)
        btn_del_prop = QPushButton("删除")
        btn_del_prop.setProperty("kind", "danger")
        btn_del_prop.clicked.connect(self._del_prop)
        self.interval = QDoubleSpinBox()
        self.interval.setRange(1.0, 60.0)
        self.interval.setSingleStep(0.5)
        self.interval.setSuffix(" 秒")
        self.interval.setValue(float((config.get("mijia_channel", {}) or {}).get("poll_interval", 3.0)))
        btn_read = QPushButton("读取当前值")
        btn_read.clicked.connect(self._read_value)
        bar.addWidget(btn_add_prop)
        bar.addWidget(btn_edit_prop)
        bar.addWidget(btn_del_prop)
        bar.addStretch(1)
        bar.addWidget(QLabel("轮询"))
        bar.addWidget(self.interval)
        bar.addWidget(btn_read)
        prop_lay.addLayout(bar)

        self.prop_table = QTableWidget(0, 3)
        self.prop_table.setHorizontalHeaderLabels(["siid", "piid", "名称"])
        self.prop_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.prop_table.verticalHeader().setVisible(False)
        self.prop_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.prop_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.prop_table.setMaximumHeight(130)
        prop_lay.addWidget(self.prop_table)

        self.current_value = QLabel("当前值：—")
        self.current_value.setProperty("accent", True)
        prop_lay.addWidget(self.current_value)
        lay.addWidget(prop_card)

        # -- 3. 映射 --------------------------------------------------------
        map_card, map_lay = card("3. 属性取值 → 电脑动作")
        bar2 = QHBoxLayout()
        btn_add = QPushButton("添加映射")
        btn_add.setProperty("kind", "primary")
        btn_add.clicked.connect(self._add_mapping)
        btn_edit = QPushButton("编辑")
        btn_edit.clicked.connect(self._edit_mapping)
        btn_del = QPushButton("删除")
        btn_del.setProperty("kind", "danger")
        btn_del.clicked.connect(self._del_mapping)
        btn_guide = QPushButton("米家 App 场景创建指引")
        btn_guide.clicked.connect(self._show_guide)
        bar2.addWidget(btn_add)
        bar2.addWidget(btn_edit)
        bar2.addWidget(btn_del)
        bar2.addStretch(1)
        bar2.addWidget(btn_guide)
        map_lay.addLayout(bar2)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["属性取值", "执行动作", "动作参数", "说明", "米家里怎么设"])
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        map_lay.addWidget(self.table)
        lay.addWidget(map_card, 2)

        # -- 4. 运行 --------------------------------------------------------
        run_card, run_lay = card("4. 启动")
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
            "关于开机：电脑关机后本程序无法运行，因此「从关机状态唤醒」需要硬件配合 —— "
            "用米家智能插座控制主机供电并在主板 BIOS 开启「断电恢复后自动开机」，或使用米家开机卡。"
            "本页负责电脑已开机时的各类操作。"
        )
        note.setProperty("muted", True)
        note.setWordWrap(True)
        run_lay.addWidget(note)

        self.log_list = QListWidget()
        self.log_list.setMaximumHeight(140)
        run_lay.addWidget(self.log_list)
        lay.addWidget(run_card, 1)

        signals.log.connect(self._append_log)
        signals.state.connect(self._on_state)
        signals.trigger.connect(self._on_trigger)

        self._load_from_config()
        if config.get("mijia_channel.enabled", False) and config.get("setup_completed", False):
            self._start()

    # -- 配置读写 ----------------------------------------------------------
    def _channel_cfg(self) -> dict:
        return dict(self.config.get("mijia_channel", {}) or {})

    def _props(self) -> list[dict]:
        from miiotpcapi.xiaomi.channel import normalize_props
        return normalize_props(self._channel_cfg())

    def _load_from_config(self) -> None:
        cfg = self._channel_cfg()
        device = cfg.get("device") or {}
        self.device.clear()
        if device.get("name"):
            self.device.addItem(device["name"], device.get("did", ""))
        self.interval.setValue(float(cfg.get("poll_interval", 3.0)))
        self._load_props()
        self._load_mappings()

    def _load_props(self) -> None:
        props = self._props()
        self.prop_table.setRowCount(0)
        for p in props:
            r = self.prop_table.rowCount()
            self.prop_table.insertRow(r)
            for c, v in enumerate([str(p.get("siid", "")), str(p.get("piid", "")),
                                   p.get("label", "")]):
                item = QTableWidgetItem(v)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.prop_table.setItem(r, c, item)

    def _load_mappings(self) -> None:
        self.table.setRowCount(0)
        for m in self._channel_cfg().get("mappings", []) or []:
            r = self.table.rowCount()
            self.table.insertRow(r)
            values = [str(m.get("value", "")), m.get("action", ""),
                      json.dumps(m.get("params", {}), ensure_ascii=False),
                      m.get("reply", ""),
                      ACTION_LABEL.get(m.get("action", ""), m.get("action", ""))]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, c, item)

    def _save(self, notify: bool = False) -> bool:
        cfg = self._channel_cfg()
        cfg["device"] = {"did": self.device.currentData() or "",
                         "name": self.device.currentText()}
        cfg["poll_interval"] = float(self.interval.value())
        self.config.set("mijia_channel", cfg)
        if notify:
            self._append_log("配置已保存")
            QMessageBox.information(self, "已保存", "米家遥控配置已保存。")
        return True

    # -- 设备 --------------------------------------------------------------
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

    # -- 属性 --------------------------------------------------------------
    def _selected_prop(self) -> tuple[int, dict] | None:
        rows = self.prop_table.selectedIndexes()
        if not rows:
            return None
        r = rows[0].row()
        props = self._props()
        if r >= len(props):
            return None
        return r, props[r]

    def _add_prop(self) -> None:
        props = self._props()
        default = {"siid": 2 + len(props), "piid": 1, "label": f"按键{len(props) + 1}"}
        form = _PropDialog(self, default)
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        cfg = self._channel_cfg()
        items = list(cfg.get("props") or props)
        items.append(form.values())
        cfg["props"] = items
        self.config.set("mijia_channel", cfg)
        self._load_props()

    def _edit_prop(self) -> None:
        sel = self._selected_prop()
        if not sel:
            QMessageBox.information(self, "提示", "请先选中一个属性。")
            return
        r, prop = sel
        form = _PropDialog(self, prop)
        if form.exec() != QDialog.DialogCode.Accepted:
            return
        cfg = self._channel_cfg()
        items = list(cfg.get("props") or self._props())
        items[r] = form.values()
        cfg["props"] = items
        self.config.set("mijia_channel", cfg)
        self._load_props()

    def _del_prop(self) -> None:
        sel = self._selected_prop()
        if not sel:
            QMessageBox.information(self, "提示", "请先选中一个属性。")
            return
        r, _ = sel
        cfg = self._channel_cfg()
        items = list(cfg.get("props") or self._props())
        items.pop(r)
        cfg["props"] = items
        self.config.set("mijia_channel", cfg)
        self._load_props()

    def _read_value(self) -> None:
        did = self.device.currentData()
        props = self._props()
        if not did:
            QMessageBox.information(self, "提示", "请先加载并选择一台米家设备。")
            return
        if not props:
            QMessageBox.information(self, "提示", "请先添加至少一个属性。")
            return
        pairs = [(int(p["siid"]), int(p["piid"])) for p in props]

        def do():
            return make_miio(self.config).get_props(did, pairs)

        def on_done(values):
            text = ",".join("—" if v is None else str(v) for v in values)
            self.current_value.setText(f"当前值：{text}")
            self._append_log(f"读取 {pairs} → {text}")

        def on_fail(err):
            self._append_log(f"读取失败：{err}")

        run_async(self, do, on_done, on_fail)

    # -- 映射 --------------------------------------------------------------
    def _selected_mapping(self) -> tuple[int, dict] | None:
        rows = self.table.selectedIndexes()
        if not rows:
            return None
        r = rows[0].row()
        mappings = self._channel_cfg().get("mappings", [])
        if r >= len(mappings):
            return None
        return r, mappings[r]

    def _add_mapping(self) -> None:
        default = self.current_value.text().replace("当前值：", "").strip()
        if default in ("—", ""):
            default = ""
        dlg = MappingDialog(self, default_value=default, prop_count=len(self._props()) or 1)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cfg = self._channel_cfg()
            mappings = list(cfg.get("mappings") or [])
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
        dlg = MappingDialog(self, mapping, prop_count=len(self._props()) or 1)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cfg = self._channel_cfg()
            mappings = list(cfg.get("mappings") or [])
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
        cfg = self._channel_cfg()
        mappings = list(cfg.get("mappings") or [])
        mappings.pop(r)
        cfg["mappings"] = mappings
        self.config.set("mijia_channel", cfg)
        self._load_mappings()

    # -- 场景指引 ----------------------------------------------------------
    def _guide_text(self) -> str:
        cfg = self._channel_cfg()
        device = (cfg.get("device") or {}).get("name") or "（未选择设备）"
        props = self._props()
        mappings = cfg.get("mappings") or []
        labels = [p.get("label") or f"siid{p.get('siid')}-piid{p.get('piid')}" for p in props]

        lines = [
            "在米家 App 里为每条指令建一个「手动场景」，场景按钮就是遥控台。",
            "",
            f"绑定设备：{device}",
            f"指令载体：{'、'.join(labels) if labels else '（尚未添加属性）'}",
            "",
            "── 操作步骤 ──────────────────────────────",
            "1. 打开米家 App →「智能」→ 右上角 + → 选择「手动控制」（手动执行）",
            "2. 名称填写下表的「场景名」，例如「电脑-关机」",
            "3. 添加动作 → 选择设备「" + device + "」→ 把属性设为下表的值",
            "4. 保存后回到「智能」列表，长按该场景 →「添加到桌面」或「发送到桌面」",
            "5. 对每条指令重复 1~4 步，之后在手机桌面或米家 App 首页点按钮即可",
            "",
            "提示：也可以在场景里做「先复位再设置」，或把多个场景放进一个小爱训练计划里用语音触发。",
            "",
            "── 需要创建的场景 ────────────────────────",
        ]
        if not mappings:
            lines.append("（还没有配置映射，请先在「3. 属性取值 → 电脑动作」里添加）")
        for i, m in enumerate(mappings, 1):
            action = m.get("action", "")
            name = ACTION_LABEL.get(action, action)
            reply = m.get("reply") or ""
            lines.append("")
            lines.append(f"{i}. 场景名：电脑-{name}")
            lines.append(f"   动作：把「{device}」的 { ' / '.join(labels) } 设为：{m.get('value', '')}")
            if reply:
                lines.append(f"   说明：{reply}")

        lines += [
            "",
            "── 关于能表达多少条指令 ──────────────────",
            "· 单孔插座：2 种（开 / 关）",
            "· 多键开关 / 可分孔插排：2 的 N 次方（N = 可独立控制的路数）",
            "· 可调亮度灯：1~100 共 100 档（注意灯会亮，建议用色温或隐藏灯带）",
            "· 两条指令若用同一个属性的同一个值，会无法区分，请错开取值",
            "",
            "── 关于远程开机 ──────────────────────────",
            "电脑关机后本程序无法运行，所以「从关机状态唤醒」需要硬件配合：",
            "用米家智能插座控制主机供电，并在主板 BIOS 打开「断电恢复后自动开机」；",
            "或者使用米家开机卡。这样对小爱说「打开插座」就等于远程开机。",
        ]
        return "\n".join(lines)

    def _show_guide(self) -> None:
        self._save()
        GuideDialog(self, self._guide_text()).exec()

    # -- 运行 --------------------------------------------------------------
    def _start(self) -> None:
        if not self.device.currentData():
            QMessageBox.information(self, "提示", "请先加载并选择一台米家设备。")
            return
        if not self._props():
            QMessageBox.information(self, "提示", "请先添加至少一个属性。")
            return
        if not (self._channel_cfg().get("mappings")):
            QMessageBox.information(self, "提示", "请至少添加一条「属性取值 → 动作」映射。")
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


# ---------------------------------------------------------------- 属性编辑
class _PropDialog(QDialog):
    def __init__(self, parent=None, prop: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("编辑属性" if prop else "添加属性")
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.siid = QSpinBox(); self.siid.setRange(1, 99)
        self.piid = QSpinBox(); self.piid.setRange(1, 99)
        self.label = QLineEdit()
        self.label.setPlaceholderText("如 按键1 / 亮度")
        if prop:
            self.siid.setValue(int(prop.get("siid", 2)))
            self.piid.setValue(int(prop.get("piid", 1)))
            self.label.setText(prop.get("label", ""))
        form.addRow("siid", self.siid)
        form.addRow("piid", self.piid)
        form.addRow("名称", self.label)
        lay.addLayout(form)
        tip = QLabel("常见约定：开关类设备 siid=2、piid=1；多键开关的按键依次是 siid=2、3、4…")
        tip.setProperty("muted", True)
        tip.setWordWrap(True)
        lay.addWidget(tip)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def values(self) -> dict:
        return {
            "siid": int(self.siid.value()),
            "piid": int(self.piid.value()),
            "label": self.label.text().strip() or f"siid{self.siid.value()}-piid{self.piid.value()}",
        }
