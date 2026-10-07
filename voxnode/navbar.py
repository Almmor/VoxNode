"""顶部自定义导航栏。

替代原来的左侧 QListWidget：
  - 每个入口是自绘的 `NavButton`（图标 + 文字 + 悬停/选中态 + 强调色指示条）
  - 图标来自 `voxnode/assets/icons/*.svg`（手写 SVG），运行时按状态染色
  - 左侧是品牌标识（复用 branding.render_png，随强调色变化），右侧是桥接状态胶囊
  - 窗口变窄时自动收起文字标签，只留图标（悬停有 tooltip），不会挤压或裁切

对外保留旧 QListWidget 用到的 `count()` / `setCurrentRow()` / `currentRow()`，
因此主窗口与自检代码的调用方式不用改。
"""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractButton, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from miiotpcapi import branding

from . import icons, theme

ICON_PX = 21          # 图标基准尺寸（逻辑像素，会随缩放放大）
LABEL_PX = 11         # 标签基准字号
BAR_H = 62            # 导航栏基准高度
MIN_ITEM_W = 60
ICON_ONLY_W = 46


class NavButton(QAbstractButton):
    """自绘导航项：上图标下文字，带悬停底色、选中底色与底部强调色指示条。"""

    def __init__(self, title: str, icon_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.title = title
        self.icon_name = icon_name
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setToolTip(title)

        self._palette = theme.current_palette()
        self._scale = theme.current_scale()
        self._show_label = True
        self._pix_off = QPixmap()
        self._pix_hover = QPixmap()
        self._pix_on = QPixmap()
        self._font = QFont()
        self._icon_px = ICON_PX
        self.refresh_theme()

    # ---------------------------------------------------------------- 主题
    def refresh_theme(self) -> None:
        self._palette = theme.current_palette()
        self._scale = theme.current_scale()
        dpr = max(2.0, float(self.devicePixelRatioF() or 1.0))

        self._icon_px = int(round(ICON_PX * self._scale))
        self._font = QFont(self.font())
        self._font.setPixelSize(max(9, int(round(LABEL_PX * self._scale))))
        self._font.setWeight(QFont.Weight.DemiBold)

        c = self._palette
        self._pix_off = icons.svg_pixmap(self.icon_name, self._icon_px, c["muted"], dpr)
        self._pix_hover = icons.svg_pixmap(self.icon_name, self._icon_px, c["text"], dpr)
        self._pix_on = icons.svg_pixmap(self.icon_name, self._icon_px, c["accent"], dpr)
        self._apply_size()
        self.update()

    def set_show_label(self, on: bool) -> None:
        if on == self._show_label:
            return
        self._show_label = on
        self._apply_size()
        self.update()

    def shows_label(self) -> bool:
        return self._show_label

    def _label_width(self) -> int:
        return QFontMetrics(self._font).horizontalAdvance(self.title)

    def preferred_width(self, show_label: bool) -> int:
        s = self._scale
        if not show_label:
            return int(round(ICON_ONLY_W * s))
        return max(int(round(MIN_ITEM_W * s)),
                   self._label_width() + int(round(22 * s)))

    def _apply_size(self) -> None:
        s = self._scale
        h = int(round(56 * s)) if self._show_label else int(round(ICON_ONLY_W * s))
        self.setFixedSize(self.preferred_width(self._show_label), h)

    # ---------------------------------------------------------------- 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c = self._palette
        selected = self.isChecked()
        hovered = self.underMouse()

        radius = 10.0 * self._scale
        body = QRectF(self.rect()).adjusted(2, 4, -2, -4)
        if selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c["selection"]))
            p.drawRoundedRect(body, radius, radius)
        elif hovered:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c["card"]))
            p.drawRoundedRect(body, radius, radius)

        pm = self._pix_on if selected else (self._pix_hover if hovered else self._pix_off)
        iw = self._icon_px
        ix = (self.width() - iw) / 2.0
        iy = (self.height() - iw) / 2.0
        if self._show_label:
            iy -= 8.0 * self._scale
        p.drawPixmap(QPointF(ix, iy), pm)

        if self._show_label:
            p.setFont(self._font)
            if selected:
                p.setPen(QColor(c["accent"]))
            elif hovered:
                p.setPen(QColor(c["text"]))
            else:
                p.setPen(QColor(c["muted"]))
            top = iy + iw + 2.0 * self._scale
            rect = QRectF(0, top, self.width(), self.height() - top - 1)
            text = QFontMetrics(self._font).elidedText(
                self.title, Qt.TextElideMode.ElideRight, max(10, self.width() - 8))
            p.drawText(rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, text)

        if selected:
            bar_w = min(24.0 * self._scale, self.width() * 0.5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c["accent"]))
            p.drawRoundedRect(
                QRectF((self.width() - bar_w) / 2.0, self.height() - 3.0, bar_w, 3.0), 1.5, 1.5)
        p.end()

    def enterEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)


class StatusChip(QFrame):
    """右上角的桥接状态胶囊：一个圆点 + 一行字。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("navStatus")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(11, 5, 13, 5)
        lay.setSpacing(7)

        self.dot = QLabel("●")
        self.dot.setStyleSheet("font-size: 11px;")
        self.text = QLabel("小爱桥接：未知")
        self.text.setObjectName("navStatusText")
        lay.addWidget(self.dot)
        lay.addWidget(self.text)

        self._running: bool | None = None
        self.set_state(None)

    def set_state(self, running: bool | None) -> None:
        self._running = running
        c = theme.current_palette()
        if running is True:
            color, word = c["ok"], "运行中"
        elif running is False:
            color, word = c["muted"], "已停止"
        else:
            color, word = c["muted"], "未知"
        self.dot.setStyleSheet(f"font-size: 11px; color: {color};")
        self.text.setText(f"小爱桥接：{word}")
        self.setToolTip("小爱音箱语音桥接的运行状态")


class TopNavBar(QWidget):
    """顶部导航栏：品牌 + 导航项 + 状态胶囊。"""

    currentChanged = pyqtSignal(int)

    def __init__(self, entries: list[tuple[str, str]], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("topNav")
        self._entries = list(entries)
        self._row = -1
        # 用户在设置里是否希望显示文字；空间不够时仍会自动收起
        self._labels_pref = True
        self._showing_labels = True

        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 0, 16, 0)
        outer.setSpacing(12)

        # -- 品牌 --------------------------------------------------------
        self._brand = QWidget()
        brand_lay = QHBoxLayout(self._brand)
        brand_lay.setContentsMargins(0, 0, 0, 0)
        brand_lay.setSpacing(10)
        self._logo = QLabel()
        name_col = QVBoxLayout()
        name_col.setContentsMargins(0, 0, 0, 0)
        name_col.setSpacing(0)
        self._brand_name = QLabel("VoxNode")
        self._brand_name.setObjectName("brandName")
        self._brand_sub = QLabel("声枢 · PC CONTROL")
        self._brand_sub.setObjectName("brandSub")
        name_col.addWidget(self._brand_name)
        name_col.addWidget(self._brand_sub)
        brand_lay.addWidget(self._logo)
        brand_lay.addLayout(name_col)
        outer.addWidget(self._brand)

        divider = QFrame()
        divider.setObjectName("navDivider")
        divider.setFixedWidth(1)
        self._divider = divider
        outer.addWidget(divider)

        # -- 导航项 ------------------------------------------------------
        outer.addStretch(1)
        nav_holder = QWidget()
        nav_lay = QHBoxLayout(nav_holder)
        nav_lay.setContentsMargins(0, 0, 0, 0)
        nav_lay.setSpacing(2)
        self._nav_holder = nav_holder
        self.buttons: list[NavButton] = []
        for title, key in self._entries:
            btn = NavButton(title, key, nav_holder)
            btn.clicked.connect(lambda _=False, b=btn: self.setCurrentRow(self.buttons.index(b)))
            nav_lay.addWidget(btn)
            self.buttons.append(btn)
        outer.addWidget(nav_holder)
        outer.addStretch(1)

        # -- 状态 --------------------------------------------------------
        self.status = StatusChip()
        outer.addWidget(self.status)

        # -- 页头副标题（占位，保持两侧对齐） ----------------------------
        self.refresh_theme()
        self._sync_heights()

    # ---------------------------------------------------------------- 兼容旧 API
    def count(self) -> int:
        return len(self.buttons)

    def currentRow(self) -> int:  # noqa: N802
        return self._row

    def setCurrentRow(self, row: int) -> None:  # noqa: N802
        if not 0 <= row < len(self.buttons):
            return
        if row == self._row:
            return
        self._row = row
        for i, b in enumerate(self.buttons):
            b.setChecked(i == row)
        self.currentChanged.emit(row)

    def rowKey(self, row: int) -> str:
        return self._entries[row][1] if 0 <= row < len(self._entries) else ""

    def rowTitle(self, row: int) -> str:
        return self._entries[row][0] if 0 <= row < len(self._entries) else ""

    # ---------------------------------------------------------------- 主题
    def refresh_theme(self, _palette: dict | None = None) -> None:
        c = theme.current_palette()
        s = theme.current_scale()
        self.setFixedHeight(int(round(BAR_H * s)))

        dpr = max(2.0, float(self.devicePixelRatioF() or 1.0))
        logo_px = int(round(30 * s))
        pm = QPixmap()
        pm.loadFromData(branding.render_png(logo_px * 2, background=c["accent"]), "PNG")
        if not pm.isNull():
            pm.setDevicePixelRatio(dpr)
        self._logo.setPixmap(pm)
        self._logo.setFixedSize(QSize(logo_px, logo_px))

        self._brand_name.setText("VoxNode")
        self._brand_name.setStyleSheet(f"color: {c['text']};")
        self._brand_sub.setStyleSheet(f"color: {c['muted']};")

        for b in self.buttons:
            b.refresh_theme()
        self.status.set_state(self.status._running)
        self._update_compact(force=True)

    def _sync_heights(self) -> None:
        self._brand.setFixedHeight(self.height())

    # ---------------------------------------------------------------- 自适应
    def set_labels_enabled(self, enabled: bool) -> None:
        """设置里的「导航栏显示文字标签」。关闭后即使窗口很宽也只显示图标。"""
        self._labels_pref = bool(enabled)
        self._update_compact(force=True)

    def labels_enabled(self) -> bool:
        return self._labels_pref

    def _update_compact(self, force: bool = False) -> None:
        """空间不够时自动收起文字，避免导航项被挤压或裁切。"""
        need = (self._brand.sizeHint().width() + 1
                + sum(b.preferred_width(True) + 2 for b in self.buttons)
                + self.status.sizeHint().width()
                + 8 * 2 + 12 * 4)
        show = self._labels_pref and need <= self.width()
        if show == self._showing_labels and not force:
            return
        self._showing_labels = show
        for b in self.buttons:
            b.set_show_label(show)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_heights()
        self._update_compact()
