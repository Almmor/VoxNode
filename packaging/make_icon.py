"""生成应用图标 app.ico（多尺寸，PNG 压缩，兼容 Windows Vista+）。

用法：
    python packaging/make_icon.py [输出路径]

设计：科技橙圆角方块 + 白色显示器图形，在小尺寸下依然清晰可辨。
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPen

SIZES = [16, 24, 32, 48, 64, 128, 256]
ORANGE = "#ff6900"
WHITE = "#ffffff"


def render(size: int) -> bytes:
    """按给定边长绘制图标，返回 PNG 字节。"""
    s = float(size)
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)

    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # 背景：橙色圆角方块
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(ORANGE))
    radius = s * 0.22
    p.drawRoundedRect(QRectF(0, 0, s, s), radius, radius)

    # 显示器外框（白色描边）
    stroke = max(1.0, s * 0.075)
    pen = QPen(QColor(WHITE))
    pen.setWidthF(stroke)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    screen = QRectF(s * 0.20, s * 0.24, s * 0.60, s * 0.40)
    frame_radius = s * 0.06
    p.drawRoundedRect(screen, frame_radius, frame_radius)

    # 支架与底座（实心白）
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(WHITE))
    stand_w = s * 0.11
    p.drawRect(QRectF(s / 2 - stand_w / 2, s * 0.64, stand_w, s * 0.12))
    base_w, base_h = s * 0.34, s * 0.07
    p.drawRoundedRect(
        QRectF(s / 2 - base_w / 2, s * 0.74, base_w, base_h),
        base_h / 2, base_h / 2,
    )
    p.end()

    # 注意：QBuffer 不持有 QByteArray 所有权，必须保留引用，否则会因悬空指针崩溃
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    if not img.save(buf, "PNG"):
        raise RuntimeError(f"PNG 编码失败（size={size}）")
    buf.close()
    return bytes(ba)


def write_ico(images: dict[int, bytes], path: Path) -> None:
    """按 ICO 容器格式写入多尺寸图标（每个尺寸内嵌 PNG 数据）。"""
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)  # reserved, type=icon, count
    entries = b""
    payload = b""
    offset = 6 + 16 * count
    for size, data in images.items():
        dim = 0 if size >= 256 else size  # 256 在 ICO 中记为 0
        entries += struct.pack(
            "<BBBBHHII",
            dim, dim, 0, 0, 1, 32, len(data), offset,
        )
        payload += data
        offset += len(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entries + payload)


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent / "app.ico"
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    images = {size: render(size) for size in SIZES}
    write_ico(images, out)
    print(f"已生成图标：{out}（{len(SIZES)} 个尺寸：{', '.join(map(str, SIZES))}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
