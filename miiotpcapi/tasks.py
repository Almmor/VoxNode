"""任务引擎：把语音 / 文本指令匹配到具体动作并执行。

一条任务规则：
    {"id": "...", "enabled": true, "patterns": ["关机", ...],
     "action": "shutdown", "params": {...}, "reply": "已...{app}"}

支持的动作见 ACTIONS：shutdown / restart / lock / sleep / hibernate /
signout / cancel_shutdown / screenshot / report_status / open_app /
close_app / wol / volume / media / tts。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import SCREENSHOT_DIR
from .core import apps, inputctl, power, screenshot, sysinfo, wol


@dataclass
class TaskResult:
    ok: bool
    reply: str
    detail: str = ""


# 音量 / 媒体指令词表（供执行与测试共用，避免魔法字符串散落）
VOLUME_OPS = {
    "大": "volume_up", "加": "volume_up", "高": "volume_up",
    "小": "volume_down", "减": "volume_down", "低": "volume_down",
    "静音": "mute", "取消静音": "mute",
}
MEDIA_OPS = {
    "暂停": "play_pause", "继续": "play_pause", "播放": "play_pause",
    "下一首": "next_track", "上一首": "prev_track",
}

# 会造成中断或数据丢失的动作：受「设置 → 电源与安全」的二次确认与总开关约束
DANGEROUS_ACTIONS: frozenset[str] = frozenset(
    {"shutdown", "restart", "hibernate", "signout", "sleep"}
)


@dataclass
class MatchedTask:
    rule: dict[str, Any]
    groups: dict[str, str] = field(default_factory=dict)


def _norm(text: str) -> str:
    return re.sub(r"[，。！？?!,.\s]", "", text or "").strip().lower()


def match(query: str, tasks: list[dict]) -> MatchedTask | None:
    """返回第一条匹配的规则；多 pattern 依次尝试（regex，支持命名组）。"""
    q = _norm(query)
    if not q:
        return None
    for rule in tasks:
        if not rule.get("enabled", True):
            continue
        for pat in rule.get("patterns", []):
            try:
                m = re.search(pat, q)
            except re.error:
                continue
            if m:
                return MatchedTask(rule=rule, groups={k: v for k, v in (m.groupdict() or {}).items() if v})
    return None


def format_reply(rule: dict, groups: dict) -> str:
    reply = rule.get("reply", "")
    for k, v in groups.items():
        reply = reply.replace("{" + k + "}", v)
    return reply


class TaskExecutor:
    """执行匹配到的动作。context 至少包含 apps / wol 两个列表。"""

    def __init__(self, screenshot_dir: str = "", apps_list: list[dict] | None = None,
                 wol_hosts: list[dict] | None = None, logger: Callable[[str], None] | None = None,
                 miot_factory: Callable[[], Any] | None = None,
                 screenshot_format: str = "png", block_dangerous: bool = False):
        self.screenshot_dir = screenshot_dir
        self.screenshot_format = screenshot_format or "png"
        # 设为 True 后，语音 / 米家 / 遥控台等所有入口都无法触发危险操作
        self.block_dangerous = bool(block_dangerous)
        self.apps = apps_list or []
        self.wol_hosts = wol_hosts or []
        self.log = logger or (lambda msg: None)
        self.miot_factory = miot_factory  # 惰性创建 MiIO 客户端，避免无账号时崩溃
        self._actions: dict[str, Callable[[dict], TaskResult]] = {
            "shutdown": self._do_shutdown,
            "restart": self._do_restart,
            "lock": self._do_lock,
            "sleep": self._do_sleep,
            "hibernate": self._do_hibernate,
            "signout": self._do_signout,
            "cancel_shutdown": self._do_cancel,
            "screenshot": self._do_screenshot,
            "report_status": self._do_status,
            "open_app": self._do_open_app,
            "close_app": self._do_close_app,
            "wol": self._do_wol,
            "volume": self._do_volume,
            "media": self._do_media,
            "tts": self._do_tts,
            "miot_power": self._do_miot_power,
        }

    # ------------------------------------------------------------------
    def execute(self, mt: MatchedTask) -> TaskResult:
        action = mt.rule.get("action", "")
        handler = self._actions.get(action)
        if not handler:
            return TaskResult(False, f"未知的动作类型：{action}")
        if self.block_dangerous and action in DANGEROUS_ACTIONS:
            self.log(f"危险动作 {action} 已被安全策略拦截")
            return TaskResult(False, "危险操作已在「设置 → 电源与安全」中被禁止")
        ctx = {**mt.rule.get("params", {}), **mt.groups}
        try:
            return handler(ctx)
        except Exception as e:
            self.log(f"执行动作 {action} 失败: {e}")
            return TaskResult(False, f"执行失败：{e}")

    # ------------------------------------------------------------------
    def _delay(self, ctx: dict, default: int = 60) -> int:
        return int(ctx.get("delay") or default)

    def _do_shutdown(self, g: dict) -> TaskResult:
        delay = self._delay(g)
        power.shutdown(delay)
        return TaskResult(True, f"电脑将在{delay}秒后关机")

    def _do_restart(self, g: dict) -> TaskResult:
        delay = self._delay(g)
        power.restart(delay)
        return TaskResult(True, f"电脑将在{delay}秒后重启")

    def _do_lock(self, g: dict) -> TaskResult:
        power.lock()
        return TaskResult(True, "已锁定电脑")

    def _do_sleep(self, g: dict) -> TaskResult:
        power.sleep()
        return TaskResult(True, "电脑已进入睡眠")

    def _do_hibernate(self, g: dict) -> TaskResult:
        power.hibernate()
        return TaskResult(True, "电脑已休眠")

    def _do_signout(self, g: dict) -> TaskResult:
        power.signout()
        return TaskResult(True, "正在注销")

    def _do_cancel(self, g: dict) -> TaskResult:
        power.cancel()
        return TaskResult(True, "已取消关机/重启任务")

    def _do_screenshot(self, g: dict) -> TaskResult:
        path = screenshot.capture(self.screenshot_dir or str(SCREENSHOT_DIR),
                                  fmt=self.screenshot_format)
        return TaskResult(True, f"已截图：{path.name}", detail=str(path))

    def _do_status(self, g: dict) -> TaskResult:
        return TaskResult(True, sysinfo.status_text())

    def _do_open_app(self, g: dict) -> TaskResult:
        name = g.get("app", "")
        app = apps.open_by_name(name, self.apps)
        return TaskResult(True, f"已打开{app['name']}", detail=app["path"])

    def _do_close_app(self, g: dict) -> TaskResult:
        name = g.get("app", "")
        n = apps.close_by_name(name, self.apps)
        if n:
            return TaskResult(True, f"已关闭{name}（{n}个进程）")
        return TaskResult(False, f"没有找到正在运行的{name}")

    def _do_wol(self, g: dict) -> TaskResult:
        host = g.get("host", "")
        wol.wake(host, self.wol_hosts)
        return TaskResult(True, f"已发送唤醒指令到{host}")

    def _do_volume(self, g: dict) -> TaskResult:
        op = g.get("op", "")
        fn = VOLUME_OPS.get(op)
        if not fn:
            return TaskResult(False, f"听不懂音量指令：{op}")
        inputctl.ACTIONS[fn]()
        return TaskResult(True, "已调整音量")

    def _do_media(self, g: dict) -> TaskResult:
        op = g.get("op", "")
        fn = MEDIA_OPS.get(op)
        if not fn:
            return TaskResult(False, f"听不懂播放指令：{op}")
        inputctl.ACTIONS[fn]()
        return TaskResult(True, "已发送媒体控制")

    def _do_tts(self, g: dict) -> TaskResult:
        return TaskResult(True, g.get("text", ""))

    def _do_miot_power(self, g: dict) -> TaskResult:
        """按名称控制米家设备的开关，如「米家打开客厅灯」。"""
        if self.miot_factory is None:
            return TaskResult(False, "未配置小米账号，无法控制米家设备")
        name = str(g.get("dev") or "").strip()
        if not name:
            return TaskResult(False, "没有听出设备名")
        on = bool(g.get("on", True))
        try:
            miio = self.miot_factory()
            devices = miio.device_list_with_room()
        except Exception as e:
            return TaskResult(False, f"获取米家设备失败：{e}")

        key = name.lower()
        target = next((d for d in devices if key == (d.get("name") or "").lower()), None)
        if target is None:
            target = next((d for d in devices if key and key in (d.get("name") or "").lower()), None)
        if target is None:
            known = "、".join(str(d.get("name", "")) for d in devices[:12]) or "（账号下没有可用设备）"
            return TaskResult(False, f"没找到米家设备「{name}」。已有：{known}")
        try:
            if miio.set_power(target["did"], on):
                return TaskResult(True, f"已{'打开' if on else '关闭'}{target['name']}")
        except Exception as e:
            return TaskResult(False, f"控制 {target['name']} 失败：{e}")
        return TaskResult(False, f"{target['name']} 似乎不支持开关控制")


ACTIONS = list(TaskExecutor({})._actions.keys())


def executor_from_config(config, logger: Callable[[str], None] | None = None,
                         miot_factory: Callable[[], Any] | None = None) -> TaskExecutor:
    """按当前配置构造执行器。

    语音桥接、米家指令通道、网页遥控台三个入口都用它，
    这样「截图格式」与「危险操作总开关」在任何入口都一致生效。
    """
    data = config.data()
    return TaskExecutor(
        screenshot_dir=data.get("screenshot_dir", ""),
        apps_list=data.get("apps", []),
        wol_hosts=data.get("wol", []),
        logger=logger,
        miot_factory=miot_factory,
        screenshot_format=(data.get("screenshot") or {}).get("format", "png"),
        block_dangerous=bool((data.get("safety") or {}).get("block_dangerous", False)),
    )


