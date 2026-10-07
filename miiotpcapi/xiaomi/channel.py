"""米家指令通道：用米家设备控制这台电脑。

原理（小米未开放个人虚拟设备，这是社区通行做法）：
  在米家 App 里对某个可控设备（智能插座 / 多键开关 / 可调灯等）做一个手动场景，
  把它的属性设成特定值；本程序轮询这些属性，取值组合变化且命中映射时，
  在本机执行对应动作（关机 / 锁屏 / 截屏 / 打开软件 / 发送 WOL 等）。

支持「多属性组合编码」，一个设备即可携带多条指令：
  - 四键开关：4 路 × 2 值 = 16 种组合
  - 多路插排：按可独立控制的路数组合
  - 可调灯  ：亮度 1~100 = 100 档

配置结构（config["mijia_channel"]）：
    {
      "enabled": false,
      "poll_interval": 3.0,
      "device": {"did": "...", "name": "客厅四键开关"},
      "props": [
        {"siid": 2, "piid": 1, "label": "按键1"},
        {"siid": 3, "piid": 1, "label": "按键2"}
      ],
      "mappings": [
        {"value": "1,0", "action": "shutdown", "params": {"delay": 60}, "reply": "已关机"},
        {"value": "0,1", "action": "lock", "params": {}, "reply": "已锁屏"}
      ],
      "reset": [{"siid": 2, "piid": 1, "value": 0}]
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


def _norm_one(value: Any) -> str:
    """把单个属性值归一化为字符串，便于组合比较。"""
    if isinstance(value, bool):
        return "1" if value else "0"
    if value is None:
        return ""
    return str(value).strip().lower()


def value_matches(value: Any, target: str) -> bool:
    """判断单个属性值是否命中目标值（兼容 0/1、on/off、true/false）。"""
    if value is None or target is None:
        return False
    candidates = {_norm_one(value)}
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


def values_match(values: list, target: str) -> bool:
    """多属性组合匹配：target 用逗号分隔，逐项按 value_matches 语义比较。

    单属性时退化为 value_matches 的行为，因此旧的单属性配置完全兼容。
    """
    if not values:
        return False
    parts = [p.strip() for p in str(target).split(",")]
    if len(parts) != len(values):
        return False
    return all(value_matches(v, p) for v, p in zip(values, parts))


def values_key(values: list) -> str:
    """组合值的展示/日志用字符串。"""
    return ",".join(_norm_one(v) for v in values)


def normalize_props(raw: dict) -> list[dict]:
    """从配置中取出属性列表，兼容旧版单属性格式 {"prop": {...}}。"""
    props = raw.get("props")
    if isinstance(props, list) and props:
        return [p for p in props if p.get("siid") is not None and p.get("piid") is not None]
    legacy = raw.get("prop")
    if isinstance(legacy, dict) and legacy.get("siid") is not None:
        return [legacy]
    return []


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
        self._last_key: Optional[str] = None
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
        self._last_key = None
        self._thread = threading.Thread(target=self._run, name="mijia-channel", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------
    def _client(self) -> MiIO:
        username = self.config.get("xiaomi.username", "")
        if not username:
            raise RuntimeError("未配置小米账号，请先在「语音助手」页登录")
        account = MiAccount(username, load_password(self.config), token_path=TOKEN_FILE)
        return MiIO(account)

    def _run(self) -> None:
        self.on_state(True)
        self.on_log("米家指令通道已启动")
        try:
            client = self._client()
            cfg = self.config.get("mijia_channel", {}) or {}
            device = cfg.get("device") or {}
            props = normalize_props(cfg)
            did = device.get("did", "")
            if not did or not props:
                raise RuntimeError("尚未配置米家设备与属性，请先在「米家遥控」页设置并保存")

            executor = self.executor_factory()
            interval = max(1.0, float(cfg.get("poll_interval", 3.0)))
            labels = " / ".join(p.get("label") or f"{p['siid']}-{p['piid']}" for p in props)
            self.on_log(f"监听 {device.get('name', did)}（{labels}），轮询间隔 {interval:.0f} 秒")

            backoff = 0
            while not self._stop.is_set():
                try:
                    values = client.get_props(
                        did, [(int(p["siid"]), int(p["piid"])) for p in props])
                    backoff = 0
                    if any(v is None for v in values):
                        self.on_log("读取属性失败（可能设备离线或属性不支持）")
                    else:
                        self._handle(values, cfg, executor)
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

    def _handle(self, values: list, cfg: dict, executor: TaskExecutor) -> None:
        key = values_key(values)
        # 首次读取只作为基线，避免启动瞬间误触发
        if not self._primed:
            self._last_key = key
            self._primed = True
            self.on_log(f"基线值：{key}（已忽略历史状态）")
            return
        if key == self._last_key:
            return
        previous, self._last_key = self._last_key, key

        for mapping in cfg.get("mappings", []) or []:
            if not values_match(values, mapping.get("value", "")):
                continue
            action = mapping.get("action", "")
            if not action:
                continue
            self.on_log(f"属性 {previous} → {key}，触发动作 {action}")
            result = executor.execute(MatchedTask(
                rule={"action": action, "params": mapping.get("params", {}) or {}},
                groups={},
            ))
            reply = result.reply or mapping.get("reply", "")
            self.on_trigger(key, reply, result.ok)
            self.on_log(f"执行{'成功' if result.ok else '失败'}：{reply}")

            resets = cfg.get("reset") or []
            if not resets and cfg.get("reset_value") not in (None, ""):
                # 兼容旧版单一复位值
                first = normalize_props(cfg)[0]
                resets = [{"siid": first["siid"], "piid": first["piid"],
                           "value": cfg.get("reset_value")}]
            if resets:
                self._apply_reset(cfg, resets)
            return

    def _apply_reset(self, cfg: dict, resets: list) -> None:
        did = (cfg.get("device") or {}).get("did", "")
        try:
            client = self._client()
            for item in resets:
                client.set_prop(did, int(item["siid"]), int(item["piid"]), item.get("value"))
            self._last_key = values_key([item.get("value") for item in resets])
            self.on_log("属性已复位，等待下一次触发")
        except Exception as e:
            self.on_log(f"属性复位失败: {e}")
