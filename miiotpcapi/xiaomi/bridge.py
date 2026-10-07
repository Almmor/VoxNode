"""小爱音箱 ↔ 电脑命令桥接。

后台线程轮询音箱的最近对话（nlp_result_get），把新指令交给
TaskExecutor 匹配执行，并可让音箱 TTS 播报结果。
"""
from __future__ import annotations

import threading
import time
import traceback
from typing import Callable, Optional

from ..config import Config, TOKEN_FILE
from ..secure import load_password
from ..tasks import executor_from_config, format_reply, match
from .account import MiAccount
from .mina import MiNA


class XiaoaiBridge:
    """轮询小爱对话并执行电脑控制指令的后台线程。

    回调（均在工作线程中调用，GUI 侧需自行跨线程）：
      on_query(query)          捕获到一条新指令
      on_result(query, reply, ok, detail)
      on_log(msg)              运行日志
      on_state(running)        启停状态变化
      on_otp(method) -> str    需要验证码时返回用户输入
    """

    def __init__(self, config: Config,
                 on_query: Callable[[str], None] = lambda q: None,
                 on_result: Callable[[str, str, bool, str], None] = lambda q, r, ok, d: None,
                 on_log: Callable[[str], None] = lambda m: None,
                 on_state: Callable[[bool], None] = lambda r: None,
                 on_otp: Callable[[str], str] = lambda m: ""):
        self.config = config
        self.on_query = on_query
        self.on_result = on_result
        self.on_log = on_log
        self.on_state = on_state
        self.on_otp = on_otp
        self.account: Optional[MiAccount] = None
        self.mina: Optional[MiNA] = None
        self.device_id: str = ""
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._last_request_id = ""
        self._last_ts = 0

    # ------------------------------------------------------------------
    def _ensure_clients(self) -> None:
        username = self.config.get("xiaomi.username", "")
        if not username:
            raise RuntimeError("未配置小米账号，请先在「语音助手」页登录")
        if self.account is None or self.account.username != username:
            password = load_password(self.config)
            self.account = MiAccount(username, password, token_path=TOKEN_FILE,
                                     otp_callback=self._otp_sync)
            self.mina = MiNA(self.account)
        self.device_id = self.config.get("xiaomi.device.device_id", "")
        if not self.device_id:
            devices = self.mina.device_list()
            dev = MiNA.pick_speaker(devices)
            if not dev:
                raise RuntimeError("账号下没有找到小爱音箱设备")
            self.device_id = dev["deviceID"]
            self.config.set("xiaomi.device.device_id", dev["deviceID"])
            self.config.set("xiaomi.device.name", dev.get("name", ""))
            self.config.set("xiaomi.device.hardware", dev.get("hardware", ""))

    def _otp_sync(self, method: str) -> str:
        self.on_log(f"小米账号需要{method}验证码，等待输入…")
        return self.on_otp(method) or ""

    # ------------------------------------------------------------------
    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="xiaomi-bridge", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    # ------------------------------------------------------------------
    def _run(self) -> None:
        self.on_state(True)
        self.on_log("小爱桥接已启动")
        poll = max(1.0, float(self.config.get("bridge.poll_interval", 2.0)))
        backoff = 0
        try:
            while not self._stop.is_set():
                try:
                    self._ensure_clients()
                    self._poll_once()
                    backoff = 0
                except Exception as e:
                    backoff = min(backoff + 1, 6)
                    wait = poll * (2 ** backoff)
                    self.on_log(f"桥接异常: {e.__class__.__name__}: {e}，{wait:.0f}s 后重试")
                    self.on_log(traceback.format_exc(limit=1))
                    self._stop.wait(wait)
                    continue
                self._stop.wait(poll)
        finally:
            self.on_log("小爱桥接已停止")
            self.on_state(False)

    def _poll_once(self) -> None:
        assert self.mina is not None
        msgs = [m for m in self.mina.latest_asks(self.device_id) if m.get("query")]
        if not msgs:
            return
        msgs.sort(key=lambda m: m["timestamp_ms"])
        if self._last_ts == 0:
            # 首次轮询只记录基线，忽略启动前说过的历史指令
            self._last_ts = msgs[-1]["timestamp_ms"]
            self.on_log("已同步音箱对话记录（忽略历史指令）")
            return
        for m in msgs:
            if m["timestamp_ms"] > self._last_ts and m["request_id"] != self._last_request_id:
                self._last_request_id = m["request_id"]
                self._last_ts = m["timestamp_ms"]
                q = m["query"].strip()
                self.on_log(f"小爱收到指令: {q}")
                self._handle_query(q)

    def _handle_query(self, query: str) -> None:
        self.on_query(query)
        data = self.config.data()
        executor = executor_from_config(
            self.config, logger=self.on_log, miot_factory=self.miot_client)
        mt = match(query, data.get("tasks", []))
        if not mt:
            self.on_result(query, "", False, "未匹配到指令")
            return
        result = executor.execute(mt)
        reply = result.reply or format_reply(mt.rule, mt.groups)
        self.on_result(query, reply, result.ok, result.detail)
        if reply and self.config.get("bridge.tts_reply", True) and self.mina:
            try:
                self.mina.tts(self.device_id, reply)
            except Exception as e:
                self.on_log(f"TTS 播报失败: {e}")

    # ------------------------------------------------------------------
    def test_tts(self, text: str = "VoxNode 已连接，可以对我说关机或截屏") -> None:
        """测试链路：登录 + 找音箱 + 播报。"""
        self._ensure_clients()
        assert self.mina is not None
        self.mina.tts(self.device_id, text)

    # ------------------------------------------------------------------
    def miot_client(self):
        """返回可用于控制米家设备的 MiIO 客户端（语音指令用）。"""
        from .account import SID_MIIO
        from .miot import MiIO
        self._ensure_clients()
        assert self.account is not None
        if not self.account.is_logged_in(SID_MIIO):
            self.account.login(SID_MIIO)
        return MiIO(self.account)
