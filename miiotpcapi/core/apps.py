"""应用管理：别名注册表，支持启动 / 关闭，供“小爱，打开浏览器”等指令使用。"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import monitor


def launch(path: str, args: str = "") -> None:
    """启动应用。支持 exe / 快捷方式 / 文件 / URL。"""
    if not path:
        raise ValueError("应用路径为空")
    if path.startswith(("http://", "https://", "mailto:")):
        os.startfile(path)  # noqa: S606 - 用户配置的 URL
        return
    p = Path(path)
    if not p.exists() and not Path(path).is_file():
        raise FileNotFoundError(f"找不到应用: {path}")
    if args:
        subprocess.Popen([path, *args.split()], close_fds=True)
    else:
        os.startfile(str(p))  # noqa: S606 - 用户配置的本地路径


def find_app(apps: list[dict], name: str) -> dict | None:
    key = name.strip().lower().rstrip(".exe")
    for a in apps:
        if key == a["name"].strip().lower() or key == Path(a.get("path", "")).stem.lower():
            return a
    return None


def open_by_name(name: str, apps: list[dict]) -> dict:
    app = find_app(apps, name)
    if not app:
        known = "、".join(a["name"] for a in apps) or "（暂无）"
        raise KeyError(f"未配置名为「{name}」的应用，已配置：{known}")
    launch(app["path"], app.get("args", ""))
    return app


def close_by_name(name: str, apps: list[dict]) -> int:
    """按别名关闭进程，返回结束的进程数。"""
    app = find_app(apps, name)
    pattern = app["path"] if app else name
    if not pattern:
        return 0
    exe = Path(pattern).name if "\\" in pattern or "/" in pattern else pattern
    return monitor.kill_by_name(exe)
