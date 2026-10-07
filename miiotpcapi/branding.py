"""品牌图标渲染：VoxNode 的图标在桌面端与移动端共用同一份绘制逻辑。

只用 Qt 的离屏绘制（QImage + QPainter），不需要显示器，也不需要额外依赖。
注意：本模块依赖 PyQt6，仅在被调用时才导入，因此核心库在无 GUI 环境仍可使用。
"""
from __future__ import annotations

from PyQt6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen

ACCENT = "#ff6900"
WHITE = "#ffffff"

# Android 启动图标各密度所需尺寸
ANDROID_DENSITIES = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}


def render_png(size: int, background: str = ACCENT, foreground: str = WHITE,
               rounded: bool = True) -> bytes:
    """绘制图标并返回 PNG 字节。

    造型：方块 + 白色显示器（屏幕外框 / 支架 / 底座），按比例绘制，
    因此 16px 到 512px 都清晰。

    rounded=True 时绘制圆角方块（Windows / PWA 用）；
    rounded=False 时铺满整块正方形（Android 启动图标用，交给系统蒙版裁形）。
    """
    from PyQt6.QtGui import QImage

    s = float(size)
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # 背景方块
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(background))
    if rounded:
        radius = s * 0.22
        p.drawRoundedRect(QRectF(0, 0, s, s), radius, radius)
    else:
        p.drawRect(QRectF(0, 0, s, s))

    # 显示器在非圆角（Android）下略微缩小，给系统蒙版留出安全边距
    k = 1.0 if rounded else 0.84
    ox = (s - s * k) / 2

    # 显示器外框
    stroke = max(1.0, s * 0.075 * k)
    pen = QPen(QColor(foreground))
    pen.setWidthF(stroke)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    screen = QRectF(ox + s * k * 0.20, ox + s * k * 0.24, s * k * 0.60, s * k * 0.40)
    frame_radius = s * k * 0.06
    p.drawRoundedRect(screen, frame_radius, frame_radius)

    # 支架与底座
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(foreground))
    stand_w = s * k * 0.11
    p.drawRect(QRectF(ox + s * k / 2 - stand_w / 2, ox + s * k * 0.64, stand_w, s * k * 0.12))
    base_w, base_h = s * k * 0.34, s * k * 0.07
    p.drawRoundedRect(
        QRectF(ox + s * k / 2 - base_w / 2, ox + s * k * 0.74, base_w, base_h),
        base_h / 2, base_h / 2,
    )
    p.end()

    # QBuffer 不持有 QByteArray 所有权，必须保留引用，否则会因悬空指针崩溃
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    if not img.save(buf, "PNG"):
        raise RuntimeError(f"PNG 编码失败（size={size}）")
    buf.close()
    return bytes(ba)
