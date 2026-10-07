"""VoxNode 启动引导（双击运行，无控制台窗口）。

用法：
  双击本文件，或执行：pythonw run_app.pyw [--setup] [--minimized]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# 确保源码目录在 sys.path 中，便于未安装时直接运行
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from voxnode.app import run  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run())
