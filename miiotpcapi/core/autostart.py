"""开机自启动：通过 HKCU 注册表 Run 键实现，无需管理员权限。"""
from __future__ import annotations

import sys
from pathlib import Path

import winreg

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "MiPCBridge"


def _command() -> str:
    """生成自启动命令：pythonw run_app.pyw --minimized（保证在源码目录可用）。"""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw) if pythonw.exists() else sys.executable
    repo_root = Path(__file__).resolve().parents[2]
    bootstrap = repo_root / "run_app.pyw"
    if bootstrap.is_file():
        return f'"{exe}" "{bootstrap}" --minimized'
    return f'"{exe}" -m mipcb --minimized'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _VALUE_NAME)
            return True
    except OSError:
        return False


def enable() -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
        winreg.SetValueEx(k, _VALUE_NAME, 0, winreg.REG_SZ, _command())


def disable() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, _VALUE_NAME)
    except OSError:
        pass
