"""网络唤醒（WOL）：管理唤醒目标、发送魔术包、查看本机 WOL 信息。"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from miiotpcapi.config import Config
from miiotpcapi.core import sysinfo, wol

from ..ui import card, page


class HostEditDialog(QDialog):
    def __init__(self, parent=None, host: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("唤醒目标" if host else "添加唤醒目标")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(host["name"] if host else "")
        self.mac = QLineEdit(host.get("mac", "") if host else "")
        self.ip = QLineEdit(host.get("ip", "255.255.255.255") if host else "255.255.255.255")
        self.port = QLineEdit(str(host.get("port", 9)) if host else "9")
        self.name.setPlaceholderText("如：客厅台式机")
        self.mac.setPlaceholderText("AA:BB:CC:DD:EE:FF")
        form.addRow("名称", self.name)
        form.addRow("MAC 地址", self.mac)
        form.addRow("IP / 广播", self.ip)
        form.addRow("端口", self.port)
        lay.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(),
            "mac": self.mac.text().strip(),
            "ip": self.ip.text().strip() or "255.255.255.255",
            "port": int(self.port.text().strip() or 9),
        }


class WolPage(QFrame):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        _, lay = page("网络唤醒", "对局域网内支持 WOL 的设备发送魔术包；对小爱说「唤醒客厅台式机」", root=self)

        hosts_card, hosts_lay = card("唤醒目标")
        bar = QHBoxLayout()
        btn_add = QPushButton("添加目标")
        btn_add.setProperty("kind", "primary")
        btn_add.clicked.connect(self._add)
        btn_edit = QPushButton("编辑")
        btn_edit.clicked.connect(self._edit)
        btn_del = QPushButton("删除")
        btn_del.setProperty("kind", "danger")
        btn_del.clicked.connect(self._remove)
        btn_wake = QPushButton("唤醒选中目标")
        btn_wake.setProperty("kind", "primary")
        btn_wake.clicked.connect(self._wake_selected)
        bar.addWidget(btn_add)
        bar.addWidget(btn_edit)
        bar.addWidget(btn_del)
        bar.addStretch(1)
        bar.addWidget(btn_wake)
        hosts_lay.addLayout(bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["名称", "MAC 地址", "IP / 广播", "端口"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        hosts_lay.addWidget(self.table)
        lay.addWidget(hosts_card)

        local_card, local_lay = card("本机 WOL 信息")
        self.local_info = QLabel("读取中…")
        self.local_info.setProperty("muted", True)
        self.local_info.setWordWrap(True)
        local_lay.addWidget(self.local_info)
        armed = QLabel("")
        armed.setProperty("muted", True)
        armed.setWordWrap(True)
        self._armed_label = armed
        local_lay.addWidget(armed)
        tip = QLabel(
            "远程唤醒「这台」电脑：在 BIOS/UEFI 开启 Wake on LAN，并在设备管理器允许网卡魔术包唤醒；"
            "小爱无法直接发魔术包，推荐用「米家智能插座」控制供电 + 主板设置「来电自启」，即可对小爱说「打开插座」实现开机。"
        )
        tip.setProperty("muted", True)
        tip.setWordWrap(True)
        local_lay.addWidget(tip)
        lay.addWidget(local_card)
        lay.addStretch(1)

        self._refresh()
        self._refresh_local()

    # ----------------------------------------------------------------------
    def _refresh(self) -> None:
        hosts = self.config.get("wol", [])
        self.table.setRowCount(0)
        for h in hosts:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, k in enumerate(["name", "mac", "ip", "port"]):
                item = QTableWidgetItem(str(h.get(k, "")))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, c, item)

    def _refresh_local(self) -> None:
        parts = []
        for itf in sysinfo.interfaces():
            if itf["mac"]:
                parts.append(f"{itf['name']}：{itf['mac']}" + (f"（{itf['ipv4']}）" if itf["ipv4"] else ""))
        self.local_info.setText("本机网卡 MAC：\n" + ("\n".join(parts) if parts else "（未读取到）"))
        armed = wol.wake_armed_devices()
        self._armed_label.setText("当前允许唤醒本机的设备：\n" + ("\n".join(armed) if armed else "（无——如需远程唤醒本机，请在设备管理器中开启）"))

    def _selected(self) -> tuple[int, dict] | None:
        rows = self.table.selectedIndexes()
        if not rows:
            return None
        r = rows[0].row()
        return r, self.config.get("wol", [])[r]

    def _add(self) -> None:
        dlg = HostEditDialog(self)
        while dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                wol.normalize_mac(dlg.values()["mac"])
            except ValueError as e:
                QMessageBox.warning(self, "提示", str(e))
                continue
            hosts = self.config.get("wol", [])
            hosts.append(dlg.values())
            self.config.set("wol", hosts)
            self._refresh()
            return

    def _edit(self) -> None:
        sel = self._selected()
        if not sel:
            QMessageBox.information(self, "提示", "请先选中一个目标。")
            return
        r, host = sel
        dlg = HostEditDialog(self, host)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            try:
                wol.normalize_mac(dlg.values()["mac"])
            except ValueError as e:
                QMessageBox.warning(self, "提示", str(e))
                return
            hosts = self.config.get("wol", [])
            hosts[r] = dlg.values()
            self.config.set("wol", hosts)
            self._refresh()

    def _remove(self) -> None:
        sel = self._selected()
        if not sel:
            QMessageBox.information(self, "提示", "请先选中一个目标。")
            return
        r, host = sel
        ret = QMessageBox.question(self, "确认删除", f"删除目标「{host['name']}」？")
        if ret != QMessageBox.StandardButton.Yes:
            return
        hosts = self.config.get("wol", [])
        hosts.pop(r)
        self.config.set("wol", hosts)
        self._refresh()

    def _wake_selected(self) -> None:
        sel = self._selected()
        if not sel:
            QMessageBox.information(self, "提示", "请先选中一个目标。")
            return
        _, host = sel
        try:
            wol.send(host["mac"], host.get("ip", "255.255.255.255"), int(host.get("port", 9) or 9))
        except Exception as e:
            QMessageBox.critical(self, "唤醒失败", str(e))
            return
        QMessageBox.information(self, "已发送", f"已向「{host['name']}」发送唤醒包，等待对方开机上线。")

    def on_shown(self) -> None:
        self._refresh()
        self._refresh_local()
