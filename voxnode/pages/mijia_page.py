"""米家设备页：列出账号下的米家设备，支持开关、属性读写与动作调用。"""
from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from miiotpcapi.config import Config, TOKEN_FILE
from miiotpcapi.secure import load_password
from miiotpcapi.xiaomi.account import SID_MIIO, MiAccount
from miiotpcapi.xiaomi.miot import POWER_IID, MiIO

from ..ui import card, page
from ..workers import run_async


def make_miio(config: Config) -> MiIO:
    """按当前配置创建米家客户端（供各页面与后台线程复用）。"""
    username = config.get("xiaomi.username", "")
    if not username:
        raise RuntimeError("未配置小米账号，请先在「语音助手」页登录")
    account = MiAccount(username, load_password(config), token_path=TOKEN_FILE)
    if not account.is_logged_in(SID_MIIO):
        account.login(SID_MIIO)
    return MiIO(account)


class MijiaPage(QFrame):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._devices: list[dict] = []
        _, lay = page("米家设备", "查看并用电脑控制账号下的米家设备（需先在「语音助手」页登录）", root=self)

        # -- 设备列表 ------------------------------------------------------
        list_card, list_lay = card("设备列表")
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("按名称或房间过滤…")
        self.search.setMinimumWidth(220)
        self.search.textChanged.connect(self._render_devices)
        btn_refresh = QPushButton("刷新设备")
        btn_refresh.setProperty("kind", "primary")
        btn_refresh.clicked.connect(self.load_devices)
        btn_on = QPushButton("打开")
        btn_on.clicked.connect(lambda: self._set_power(True))
        btn_off = QPushButton("关闭")
        btn_off.clicked.connect(lambda: self._set_power(False))
        bar.addWidget(self.search)
        bar.addStretch(1)
        bar.addWidget(btn_on)
        bar.addWidget(btn_off)
        bar.addWidget(btn_refresh)
        list_lay.addLayout(bar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["名称", "房间", "型号", "在线", "DID"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 190)
        self.table.setColumnWidth(3, 60)
        self.table.setColumnWidth(4, 150)
        list_lay.addWidget(self.table)
        lay.addWidget(list_card, 3)

        # -- 属性读写 ------------------------------------------------------
        prop_card, prop_lay = card("属性读写（MIoT：siid / piid）")
        row = QHBoxLayout()
        self.siid = QSpinBox(); self.siid.setRange(1, 99); self.siid.setValue(POWER_IID[0])
        self.piid = QSpinBox(); self.piid.setRange(1, 99); self.piid.setValue(POWER_IID[1])
        btn_read = QPushButton("读取")
        btn_read.clicked.connect(self._read_prop)
        self.prop_value = QLineEdit(); self.prop_value.setPlaceholderText("属性值")
        self.prop_value.setMinimumWidth(140)
        btn_write = QPushButton("写入")
        btn_write.setProperty("kind", "primary")
        btn_write.clicked.connect(self._write_prop)
        row.addWidget(QLabel("siid")); row.addWidget(self.siid)
        row.addWidget(QLabel("piid")); row.addWidget(self.piid)
        row.addWidget(btn_read)
        row.addWidget(self.prop_value, 1)
        row.addWidget(btn_write)
        prop_lay.addLayout(row)
        hint = QLabel(f"提示：绝大多数米家设备的「开关」为 siid={POWER_IID[0]}、piid={POWER_IID[1]}（布尔值）。")
        hint.setProperty("muted", True)
        prop_lay.addWidget(hint)
        lay.addWidget(prop_card)

        # -- 动作调用 ------------------------------------------------------
        act_card, act_lay = card("动作调用（MIoT：siid / aiid）")
        row2 = QHBoxLayout()
        self.as_siid = QSpinBox(); self.as_siid.setRange(1, 99); self.as_siid.setValue(2)
        self.as_aiid = QSpinBox(); self.as_aiid.setRange(1, 99); self.as_aiid.setValue(1)
        self.args = QLineEdit()
        self.args.setPlaceholderText('参数 JSON 数组，如 ["Hello"]，可留空')
        btn_action = QPushButton("调用动作")
        btn_action.clicked.connect(self._call_action)
        row2.addWidget(QLabel("siid")); row2.addWidget(self.as_siid)
        row2.addWidget(QLabel("aiid")); row2.addWidget(self.as_aiid)
        row2.addWidget(self.args, 1)
        row2.addWidget(btn_action)
        act_lay.addLayout(row2)
        lay.addWidget(act_card)

        self.status = QLabel("尚未加载设备，点击「刷新设备」开始。")
        self.status.setProperty("muted", True)
        lay.addWidget(self.status)

    # ----------------------------------------------------------------------
    def on_shown(self) -> None:
        if not self._devices and self.config.get("xiaomi.username", ""):
            self.load_devices()

    def load_devices(self) -> None:
        self.status.setText("正在加载米家设备…")

        def fetch():
            return make_miio(self.config).device_list_with_room()

        def on_done(devices):
            self._devices = devices or []
            self._render_devices()
            self.status.setText(f"共 {len(self._devices)} 台设备。")

        def on_fail(err):
            self.status.setText(f"加载失败：{err}")
            QMessageBox.warning(self, "加载米家设备失败", err)

        run_async(self, fetch, on_done, on_fail)

    def _render_devices(self) -> None:
        keyword = self.search.text().strip().lower()
        self.table.setRowCount(0)
        for d in self._devices:
            if keyword and keyword not in (d.get("name", "") + d.get("room", "")).lower():
                continue
            r = self.table.rowCount()
            self.table.insertRow(r)
            values = [d.get("name", ""), d.get("room", ""), d.get("model", ""),
                      "在线" if d.get("online") else "离线", d.get("did", "")]
            for c, v in enumerate(values):
                item = QTableWidgetItem(str(v))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, d.get("did", ""))
                self.table.setItem(r, c, item)

    def _selected(self) -> dict | None:
        rows = self.table.selectedIndexes()
        if not rows:
            return None
        did = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        return next((d for d in self._devices if d.get("did") == did), None)

    # ----------------------------------------------------------------------
    def _set_power(self, on: bool) -> None:
        device = self._selected()
        if not device:
            QMessageBox.information(self, "提示", "请先在列表中选择一台设备。")
            return
        did, name = device["did"], device["name"]
        self.status.setText(f"正在{'打开' if on else '关闭'} {name}…")

        def do():
            return make_miio(self.config).set_power(did, on)

        def on_done(ok):
            self.status.setText(f"{name}：{'操作成功' if ok else '该设备不支持开关控制'}")

        def on_fail(err):
            self.status.setText(f"操作失败：{err}")

        run_async(self, do, on_done, on_fail)

    def _read_prop(self) -> None:
        device = self._selected()
        if not device:
            QMessageBox.information(self, "提示", "请先在列表中选择一台设备。")
            return
        did = device["did"]
        siid, piid = self.siid.value(), self.piid.value()

        def do():
            return make_miio(self.config).get_prop(did, siid, piid)

        def on_done(value):
            self.prop_value.setText("" if value is None else str(value))
            self.status.setText(f"读取 siid={siid} piid={piid} → {value!r}")

        def on_fail(err):
            self.status.setText(f"读取失败：{err}")

        run_async(self, do, on_done, on_fail)

    def _write_prop(self) -> None:
        device = self._selected()
        if not device:
            QMessageBox.information(self, "提示", "请先在列表中选择一台设备。")
            return
        raw = self.prop_value.text().strip()
        value: object = raw
        if raw.lower() in ("true", "false"):
            value = raw.lower() == "true"
        elif raw.lower() in ("on", "off"):
            value = raw.lower() == "on"
        else:
            try:
                value = int(raw)
            except ValueError:
                try:
                    value = float(raw)
                except ValueError:
                    pass
        did = device["did"]
        siid, piid = self.siid.value(), self.piid.value()

        def do():
            return make_miio(self.config).set_prop(did, siid, piid, value)

        def on_done(code):
            self.status.setText(f"写入 siid={siid} piid={piid} = {value!r} → {'成功' if code == 0 else f'失败(code={code})'}")

        def on_fail(err):
            self.status.setText(f"写入失败：{err}")

        run_async(self, do, on_done, on_fail)

    def _call_action(self) -> None:
        device = self._selected()
        if not device:
            QMessageBox.information(self, "提示", "请先在列表中选择一台设备。")
            return
        text = self.args.text().strip()
        try:
            args = json.loads(text) if text else []
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "参数格式错误", f"参数需要是 JSON 数组：{e}")
            return
        if not isinstance(args, list):
            QMessageBox.warning(self, "参数格式错误", "参数需要是 JSON 数组，例如 [\"Hello\"]")
            return
        did = device["did"]
        siid, aiid = self.as_siid.value(), self.as_aiid.value()

        def do():
            return make_miio(self.config).action(did, siid, aiid, args)

        def on_done(code):
            self.status.setText(f"调用动作 siid={siid} aiid={aiid} → {'成功' if code == 0 else f'失败(code={code})'}")

        def on_fail(err):
            self.status.setText(f"动作调用失败：{err}")

        run_async(self, do, on_done, on_fail)
