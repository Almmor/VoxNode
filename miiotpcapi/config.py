"""配置管理：JSON 持久化 + 默认值合并。"""
from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

IS_WINDOWS = True  # 本项目当前仅支持 Windows

APP_DIR = Path.home() / ".voxnode"
CONFIG_FILE = APP_DIR / "config.json"
TOKEN_FILE = APP_DIR / "mi_token.json"
SCREENSHOT_DIR = Path.home() / "Pictures" / "VoxNode"

# 旧版本（当时的名字是 MiPC Bridge）使用的配置目录，首次启动时自动迁移
_LEGACY_APP_DIR = Path.home() / ".miiotpcapi"


def _migrate_legacy_dir() -> None:
    try:
        if _LEGACY_APP_DIR.is_dir() and not APP_DIR.exists():
            _LEGACY_APP_DIR.rename(APP_DIR)
    except OSError:
        pass


_migrate_legacy_dir()

DEFAULT_TASKS: list[dict[str, Any]] = [
    {
        "id": "cancel-shutdown",
        "enabled": True,
        "patterns": ["取消关机", "不要关机", "取消重启"],
        "action": "cancel_shutdown",
        "reply": "已取消关机任务",
    },
    {
        "id": "shutdown",
        "enabled": True,
        "patterns": ["关机", "关闭电脑", "把电脑关了", "电脑关机"],
        "action": "shutdown",
        "params": {"delay": 60},
        "reply": "电脑将在60秒后关机，说“取消关机”可以撤销",
    },
    {
        "id": "restart",
        "enabled": True,
        "patterns": ["重启电脑", "重新启动电脑", "重启", "把电脑重启"],
        "action": "restart",
        "params": {"delay": 60},
        "reply": "电脑将在60秒后重启",
    },
    {
        "id": "lock",
        "enabled": True,
        "patterns": ["锁屏", "锁定电脑", "把电脑锁了"],
        "action": "lock",
        "reply": "已锁定电脑",
    },
    {
        "id": "sleep",
        "enabled": True,
        "patterns": ["电脑睡眠", "让电脑睡眠", "睡眠"],
        "action": "sleep",
        "reply": "电脑已进入睡眠",
    },
    {
        "id": "screenshot",
        "enabled": True,
        "patterns": ["截屏", "截个屏", "截图", "帮我截屏", "电脑截屏"],
        "action": "screenshot",
        "reply": "已截图并保存到图片文件夹",
    },
    {
        "id": "status",
        "enabled": True,
        "patterns": ["电脑状态", "电脑配置", "查看电脑状态", "电脑运行状态"],
        "action": "report_status",
        "reply": "",
    },
    {
        "id": "open-app",
        "enabled": True,
        "patterns": ["打开(?P<app>.+)", "启动(?P<app>.+)", "运行(?P<app>.+)"],
        "action": "open_app",
        "reply": "正在打开{app}",
    },
    {
        "id": "close-app",
        "enabled": True,
        "patterns": ["关闭(?P<app>.+)", "退出(?P<app>.+)"],
        "action": "close_app",
        "reply": "正在关闭{app}",
    },
    {
        "id": "wol",
        "enabled": True,
        "patterns": ["网络唤醒(?P<host>.+)", "唤醒(?P<host>.+)", "远程唤醒(?P<host>.+)"],
        "action": "wol",
        "reply": "已发送唤醒包到{host}",
    },
    {
        "id": "miot-on",
        "enabled": True,
        "patterns": ["米家打开(?P<dev>.+)", "米家开(?P<dev>.+)"],
        "action": "miot_power",
        "params": {"on": True},
        "reply": "已打开米家设备{dev}",
    },
    {
        "id": "miot-off",
        "enabled": True,
        "patterns": ["米家关闭(?P<dev>.+)", "米家关(?P<dev>.+)"],
        "action": "miot_power",
        "params": {"on": False},
        "reply": "已关闭米家设备{dev}",
    },
]

DEFAULT_APPS: list[dict[str, Any]] = [
    {"name": "记事本", "path": "notepad.exe", "args": ""},
    {"name": "计算器", "path": "calc.exe", "args": ""},
    {"name": "文件管理器", "path": "explorer.exe", "args": ""},
    {"name": "浏览器", "path": "https://www.mi.com", "args": ""},
]

DEFAULTS: dict[str, Any] = {
    "setup_completed": False,
    "autostart": False,
    "start_minimized": False,
    "screenshot_dir": str(SCREENSHOT_DIR),
    # 界面外观
    "ui": {
        "accent": "orange",          # orange / blue / green / violet / magenta
        "scale": 1.0,                # 0.9 / 1.0 / 1.1 / 1.25
        "nav_labels": True,          # 顶部导航栏是否显示文字（关闭则只留图标）
        "close_action": "tray",      # 点关闭按钮时：tray=最小化到托盘，quit=直接退出
        "tray_double_click": "show",  # 双击托盘：show=显示主界面，toggle_bridge=启停桥接
        "notifications": True,       # 操作结果是否弹桌面通知
    },
    # 危险操作（关机 / 重启 / 休眠 / 注销）的安全策略
    "safety": {
        "confirm_dangerous": True,   # 二次确认
        "block_dangerous": False,    # 一律禁止，防止误触或语音误触发
    },
    "screenshot": {
        "format": "png",             # png / jpeg
        "auto_clean_days": 0,        # 自动清理多少天前的截图，0 = 不清理
    },
    "power": {"default_delay": 60},
    "xiaomi": {
        "username": "",
        "save_password": True,
        "device": {"name": "", "device_id": "", "hardware": ""},
    },
    "bridge": {
        "enabled": False,
        "poll_interval": 2.0,
        "tts_reply": True,
    },
    "tasks": deepcopy(DEFAULT_TASKS),
    "apps": deepcopy(DEFAULT_APPS),
    "wol": [],
    # 米家指令通道：用米家设备属性控制本机（支持多属性组合编码）
    "mijia_channel": {
        "enabled": False,
        "poll_interval": 3.0,
        "device": {"did": "", "name": ""},
        "props": [{"siid": 2, "piid": 1, "label": "开关"}],
        "mappings": [
            {"value": "1", "action": "shutdown", "params": {"delay": 60}, "reply": "电脑将在60秒后关机"},
            {"value": "0", "action": "lock", "params": {}, "reply": "已锁定电脑"},
        ],
        "reset": [],
    },
    # 手机网页遥控台
    "remote": {
        "enabled": False,
        "port": 8765,
        "bind": "0.0.0.0",
        "token": "",
    },
}


def _migrate(data: dict) -> None:
    """把旧版本的配置结构就地升级为新结构（在合并默认值之前调用）。"""
    channel = data.get("mijia_channel")
    if isinstance(channel, dict):
        # 单属性 prop -> 多属性 props
        legacy_prop = channel.get("prop")
        if "props" not in channel and isinstance(legacy_prop, dict) \
                and legacy_prop.get("siid") is not None:
            channel["props"] = [legacy_prop]
        channel.pop("prop", None)
        # 单值 reset_value -> reset 列表
        legacy_reset = channel.get("reset_value")
        if "reset" not in channel and legacy_reset not in (None, ""):
            first = (channel.get("props") or [{}])[0]
            if first.get("siid") is not None:
                channel["reset"] = [{
                    "siid": first["siid"],
                    "piid": first.get("piid", 1),
                    "value": legacy_reset,
                }]
        channel.pop("reset_value", None)


def _deep_merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


class Config:
    """线程安全的配置对象，保存到 ~/.voxnode/config.json。"""

    def __init__(self, path: Path = CONFIG_FILE):
        self.path = path
        self._lock = threading.RLock()
        self._data: dict[str, Any] = deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        with self._lock:
            if self.path.is_file():
                try:
                    raw = json.loads(self.path.read_text("utf-8"))
                    if isinstance(raw, dict):
                        _migrate(raw)  # 升级旧结构后再与默认值合并
                        self._data = _deep_merge(deepcopy(DEFAULTS), raw)
                    else:
                        self._data = deepcopy(DEFAULTS)
                    return
                except Exception:
                    pass
            self._data = deepcopy(DEFAULTS)

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), "utf-8")

    # -- 字典式访问 --------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            cur: Any = self._data
            for part in key.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return default
            return cur

    def set(self, key: str, value: Any, save: bool = True) -> None:
        with self._lock:
            parts = key.split(".")
            cur = self._data
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
            cur[parts[-1]] = value
            if save:
                self.save()

    def data(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._data)

    def reset(self) -> None:
        with self._lock:
            self._data = deepcopy(DEFAULTS)
            self.save()
