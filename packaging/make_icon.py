"""生成应用图标 app.ico（多尺寸，PNG 压缩，兼容 Windows Vista+）。

用法：
    python packaging/make_icon.py [输出路径]

图标造型统一由 miiotpcapi.branding 提供，桌面端与 Android 端共用同一份绘制代码。
"""
from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtGui import QGuiApplication  # noqa: E402

from miiotpcapi.branding import render_png  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]


def write_ico(images: dict[int, bytes], path: Path) -> None:
    """按 ICO 容器格式写入多尺寸图标（每个尺寸内嵌 PNG 数据）。"""
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)  # reserved, type=icon, count
    entries = b""
    payload = b""
    offset = 6 + 16 * count
    for size, data in images.items():
        dim = 0 if size >= 256 else size  # 256 在 ICO 中记为 0
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        payload += data
        offset += len(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + entries + payload)


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent / "app.ico"
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841
    images = {size: render_png(size) for size in SIZES}
    write_ico(images, out)
    print(f"已生成图标：{out}（{len(SIZES)} 个尺寸：{', '.join(map(str, SIZES))}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
