"""开机自启动：通过 HKCU 注册表 Run 键实现，无需管理员权限。"""
from __future__ import annotations

import sys
from pathlib import Path

import winreg

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "VoxNode"
# 旧版本（当时的名字是 MiPC Bridge）写入的项，启用/停用时一并清理
_LEGACY_VALUE_NAMES = ("MiPCBridge",)


def _command() -> str:
    """生成开机自启命令行。

    三种运行形态：
      1. 打包后的 exe（PyInstaller 冻结）——直接调用自身 exe
      2. 源码目录存在 run_app.pyw ——用 pythonw 拉起启动引导（无控制台窗口）
      3. 其它情况（已 pip 安装）——pythonw -m voxnode
    """
    if getattr(sys, "frozen", False):
        # 打包形态：sys.executable 即 VoxNode.exe
        return f'"{sys.executable}" --minimized'

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = str(pythonw) if pythonw.exists() else sys.executable
    repo_root = Path(__file__).resolve().parents[2]
    bootstrap = repo_root / "run_app.pyw"
    if bootstrap.is_file():
        return f'"{exe}" "{bootstrap}" --minimized'
    return f'"{exe}" -m voxnode --minimized'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _VALUE_NAME)
            return True
    except OSError:
        return False


def _delete_values(key) -> None:
    for name in (_VALUE_NAME, *_LEGACY_VALUE_NAMES):
        try:
            winreg.DeleteValue(key, name)
        except OSError:
            pass


def enable() -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
        _delete_values(k)  # 先清掉旧品牌名残留，避免重复自启
        winreg.SetValueEx(k, _VALUE_NAME, 0, winreg.REG_SZ, _command())


def disable() -> None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            _delete_values(k)
    except OSError:
        pass
