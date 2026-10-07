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
                 wol_hosts: list[dict] | None = None, logger: Callable[[str], None] | None = None):
        self.screenshot_dir = screenshot_dir
        self.apps = apps_list or []
        self.wol_hosts = wol_hosts or []
        self.log = logger or (lambda msg: None)
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
        }

    # ------------------------------------------------------------------
    def execute(self, mt: MatchedTask) -> TaskResult:
        action = mt.rule.get("action", "")
        handler = self._actions.get(action)
        if not handler:
            return TaskResult(False, f"未知的动作类型：{action}")
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
        path = screenshot.capture(self.screenshot_dir or str(SCREENSHOT_DIR))
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
        mapping = {"大": "volume_up", "加": "volume_up", "高": "volume_up",
                   "小": "volume_down", "减": "volume_down", "低": "volume_down",
                   "静音": "mute", "取消静音": "mute"}
        fn = mapping.get(op)
        if not fn:
            return TaskResult(False, f"听不懂音量指令：{op}")
        inputctl.ACTIONS[fn]()
        return TaskResult(True, "已调整音量")

    def _do_media(self, g: dict) -> TaskResult:
        op = g.get("op", "")
        mapping = {"暂停": "play_pause", "继续": "play_pause", "播放": "play_pause",
                   "下一首": "next_track", "上一首": "prev_track"}
        fn = mapping.get(op)
        if not fn:
            return TaskResult(False, f"听不懂播放指令：{op}")
        inputctl.ACTIONS[fn]()
        return TaskResult(True, "已发送媒体控制")

    def _do_tts(self, g: dict) -> TaskResult:
        return TaskResult(True, g.get("text", ""))


ACTIONS = list(TaskExecutor({})._actions.keys())
