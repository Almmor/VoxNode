"""生成 Android 启动图标（各密度 mipmap PNG）。

用法：
    python android/tools/make_android_icons.py

图标造型与桌面端共用 miiotpcapi.branding，只是这里铺满正方形，
交给 Android 启动器的蒙版裁形。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PyQt6.QtGui import QGuiApplication  # noqa: E402

from miiotpcapi.branding import ANDROID_DENSITIES, render_png  # noqa: E402

RES = ROOT / "android" / "app" / "src" / "main" / "res"


def main() -> int:
    QGuiApplication.instance() or QGuiApplication([])
    written = []
    for density, size in ANDROID_DENSITIES.items():
        data = render_png(size, rounded=False)
        target = RES / f"mipmap-{density}" / "ic_launcher.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(f"mipmap-{density}/ic_launcher.png ({size}px, {len(data)}B)")

    # 顺带导出一张 512 供商店/文档使用
    store = ROOT / "android" / "icon-512.png"
    store.write_bytes(render_png(512, rounded=False))
    written.append(f"icon-512.png (512px)")

    for item in written:
        print("已生成", item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
