"""模块入口：python -m mipcb [--setup] [--minimized]"""
from __future__ import annotations

from .app import run

if __name__ == "__main__":
    raise SystemExit(run())
