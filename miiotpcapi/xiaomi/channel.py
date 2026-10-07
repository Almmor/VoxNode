"""米家指令通道：用米家设备属性控制这台电脑。

原理（小米未开放个人虚拟设备，这是社区通行做法）：
  在米家 App 里对某个可控设备（智能插座 / 灯 / 开关等）做一个手动场景，
  把它的某个属性设成特定值；本程序轮询该属性，取值变化且命中映射时，
  在本机执行对应动作（关机 / 锁屏 / 截屏 / 打开软件 / 发送 WOL 等）。

配置结构（config["mijia_channel"]）：
    {
      "enabled": false,
      "poll_interval": 3.0,
      "device": {"did": "...", "name": "客厅插座"},
      "prop": {"siid": 2, "piid": 1, "label": "开关"},
      "mappings": [
        {"value": "1", "action": "shutdown", "params": {"delay": 60}, "reply": "已关机"},
        {"value": "0", "action": "lock", "reply": "已锁屏"}
      ],
      "reset_value": null
    }
"""
from __future__ import annotations

import threading
import traceback
from typing import Any, Callable, Optional

from ..config import Config, TOKEN_FILE
from ..secure import load_password
from ..tasks import MatchedTask, TaskExecutor
from .account import MiAccount
from .miot import MiIO, MiIOError


def value_matches(value: Any, target: str) -> bool:
    """判断属性值是否命中映射中的目标值（兼容 0/1、on/off、true/false）。"""
    if value is None or target is None:
        return False
    candidates = {str(value).strip().lower()}
    if isinstance(value, bool):
        candidates |= {"1", "on", "true"} if value else {"0", "off", "false"}
    else:
        try:
            iv = int(value)
            if iv in (0, 1):
                candidates |= ({"on", "true"} if iv else {"off", "false"})
        except (TypeError, ValueError):
            pass
    return str(target).strip().lower() in candidates


class MijiaChannel:
    """轮询米家设备属性的后台线程，命中映射即执行电脑动作。"""

    def __init__(self, config: Config,
                 executor_factory: Callable[[], TaskExecutor],
                 on_log: Callable[[str], None] = lambda m: None,
                 on_state: Callable[[bool], None] = lambda r: None,
                 on_trigger: Callable[[str, str, bool], None] = lambda v, r, ok: None):
        self.config = config
        self.executor_factory = executor_factory
        self.on_log = on_log
        self.on_state = on_state
        self.on_trigger = on_trigger
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_value: Any = None
        self._primed = False

    # ------------------------------------------------------------------
    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> bool:
        if self.running:
            return True
        self._stop.clear()
        self._primed = False
        self._thread = threading.Thread(target=self._run, name="mijia-channel", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------
    def _client(self) -> MiIO:
        username = self.config.get("xiaomi.username", "")
        if not username:
            raise RuntimeError("未配置小米账号，请先在「账号」页登录")
        account = MiAccount(username, load_password(self.config), token_path=TOKEN_FILE)
        return MiIO(account)

    def _run(self) -> None:
        self.on_state(True)
        self.on_log("米家指令通道已启动")
        try:
            client = self._client()
            cfg = self.config.get("mijia_channel", {}) or {}
            device = cfg.get("device") or {}
            prop = cfg.get("prop") or {}
            did = device.get("did", "")
            siid, piid = prop.get("siid"), prop.get("piid")
            if not did or siid is None or piid is None:
                raise RuntimeError("尚未配置米家设备与属性，请先在「米家遥控」页设置并保存")

            executor = self.executor_factory()
            interval = max(1.0, float(cfg.get("poll_interval", 3.0)))
            label = f"{device.get('name', did)} · {prop.get('label', f'{siid}-{piid}')}"
            self.on_log(f"监听 {label}，轮询间隔 {interval:.0f} 秒")

            backoff = 0
            while not self._stop.is_set():
                try:
                    value = client.get_prop(did, int(siid), int(piid))
                    backoff = 0
                    if value is None:
                        self.on_log("读取属性失败（可能设备离线或属性不支持）")
                    else:
                        self._handle(value, cfg, executor)
                except MiIOError as e:
                    backoff = min(backoff + 1, 5)
                    self.on_log(f"米家接口异常: {e}")
                except Exception as e:  # 网络等临时问题
                    backoff = min(backoff + 1, 5)
                    self.on_log(f"轮询异常: {e.__class__.__name__}: {e}")
                    self.on_log(traceback.format_exc(limit=1))
                wait = interval * (2 ** backoff) if backoff else interval
                self._stop.wait(wait)
        except Exception as e:
            self.on_log(f"米家指令通道启动失败: {e}")
        finally:
            self.on_log("米家指令通道已停止")
            self.on_state(False)

    def _handle(self, value: Any, cfg: dict, executor: TaskExecutor) -> None:
        # 首次读取只作为基线，避免启动瞬间误触发
        if not self._primed:
            self._last_value = value
            self._primed = True
            self.on_log(f"基线值：{value!r}（已忽略历史状态）")
            return
        if value == self._last_value:
            return
        previous, self._last_value = self._last_value, value

        for mapping in cfg.get("mappings", []) or []:
            if not value_matches(value, mapping.get("value", "")):
                continue
            action = mapping.get("action", "")
            if not action:
                continue
            self.on_log(f"属性 {previous!r} → {value!r}，触发动作 {action}")
            result = executor.execute(MatchedTask(
                rule={"action": action, "params": mapping.get("params", {}) or {}},
                groups={},
            ))
            reply = result.reply or mapping.get("reply", "")
            self.on_trigger(str(value), reply, result.ok)
            self.on_log(f"执行{'成功' if result.ok else '失败'}：{reply}")

            reset = cfg.get("reset_value")
            if reset not in (None, ""):
                try:
                    self._client().set_prop(
                        cfg["device"]["did"],
                        int(cfg["prop"]["siid"]), int(cfg["prop"]["piid"]),
                        type(value)(reset) if isinstance(value, (int, float)) and not isinstance(value, bool) else reset,
                    )
                    self._last_value = reset
                    self.on_log(f"属性已复位为 {reset!r}")
                except Exception as e:
                    self.on_log(f"属性复位失败: {e}")
            return
