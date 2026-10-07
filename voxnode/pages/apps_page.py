"""应用任务：别名注册表，供快捷启动与小爱「打开 XX」指令使用。"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from miiotpcapi.config import Config
from miiotpcapi.core import apps

from ..ui import card, page


class AppEditDialog(QDialog):
    def __init__(self, parent=None, app: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("应用" if app else "添加应用")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(app["name"] if app else "")
        self.path = QLineEdit(app.get("path", "") if app else "")
        self.args = QLineEdit(app.get("args", "") if app else "")
        self.name.setPlaceholderText("如：微信")
        self.path.setPlaceholderText("exe / 快捷方式 / 文件 / URL")
        form.addRow("名称", self.name)
        form.addRow("路径", self.path)
        form.addRow("参数", self.args)
        lay.addLayout(form)
        row = QHBoxLayout()
        btn_browse = QPushButton("浏览…")
        btn_browse.clicked.connect(self._browse)
        row.addStretch(1)
        row.addWidget(btn_browse)
        lay.addLayout(row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择程序", "", "程序 (*.exe *.lnk *.bat);;所有文件 (*)")
        if path:
            self.path.setText(path)

    def values(self) -> dict:
        return {"name": self.name.text().strip(), "path": self.path.text().strip(),
                "args": self.args.text().strip()}


class AppsPage(QFrame):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        _, lay = page("应用任务", "对小爱说「打开记事本」「关闭浏览器」，名称取自下表", root=self)

        table_card, table_lay = card()
        bar = QHBoxLayout()
        bar.setSpacing(10)
        btn_add = QPushButton("添加应用")
        btn_add.setProperty("kind", "primary")
        btn_add.clicked.connect(self._add)
        btn_edit = QPushButton("编辑")
        btn_edit.clicked.connect(self._edit)
        btn_del = QPushButton("删除")
        btn_del.setProperty("kind", "danger")
        btn_del.clicked.connect(self._remove)
        btn_run = QPushButton("试运行")
        btn_run.clicked.connect(self._run)
        bar.addWidget(btn_add)
        bar.addWidget(btn_edit)
        bar.addWidget(btn_del)
        bar.addStretch(1)
        bar.addWidget(btn_run)
        table_lay.addLayout(bar)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["名称", "路径", "参数"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table_lay.addWidget(self.table)
        lay.addWidget(table_card, 1)

        tip = QLabel("提示：路径支持 exe、快捷方式、普通文件和 http(s) 链接；「参数」以空格分隔传给程序。")
        tip.setProperty("muted", True)
        lay.addWidget(tip)
        self._refresh()

    def _refresh(self) -> None:
        apps_list = self.config.get("apps", [])
        self.table.setRowCount(0)
        for a in apps_list:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, k in enumerate(["name", "path", "args"]):
                item = QTableWidgetItem(a.get(k, ""))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(r, c, item)

    def _selected(self) -> tuple[int, dict] | None:
        rows = self.table.selectedIndexes()
        if not rows:
            return None
        r = rows[0].row()
        return r, self.config.get("apps", [])[r]

    def _add(self) -> None:
        dlg = AppEditDialog(self)
        while dlg.exec() == QDialog.DialogCode.Accepted:
            v = dlg.values()
            if not v["name"] or not v["path"]:
                QMessageBox.warning(self, "提示", "名称和路径不能为空。")
                continue
            apps_list = self.config.get("apps", [])
            apps_list.append(v)
            self.config.set("apps", apps_list)
            self._refresh()
            return

    def _edit(self) -> None:
        sel = self._selected()
        if not sel:
            QMessageBox.information(self, "提示", "请先选中一个应用。")
            return
        r, app = sel
        dlg = AppEditDialog(self, app)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            apps_list = self.config.get("apps", [])
            apps_list[r] = {**app, **dlg.values()}
            self.config.set("apps", apps_list)
            self._refresh()

    def _remove(self) -> None:
        sel = self._selected()
        if not sel:
            QMessageBox.information(self, "提示", "请先选中一个应用。")
            return
        r, app = sel
        ret = QMessageBox.question(self, "确认删除", f"删除应用「{app['name']}」？")
        if ret != QMessageBox.StandardButton.Yes:
            return
        apps_list = self.config.get("apps", [])
        apps_list.pop(r)
        self.config.set("apps", apps_list)
        self._refresh()

    def _run(self) -> None:
        sel = self._selected()
        if not sel:
            QMessageBox.information(self, "提示", "请先选中一个应用。")
            return
        _, app = sel
        try:
            apps.launch(app["path"], app.get("args", ""))
        except Exception as e:
            QMessageBox.critical(self, "启动失败", str(e))

    def on_shown(self) -> None:
        self._refresh()
