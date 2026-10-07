"""MiNA（小爱音箱）客户端：设备列表 / TTS / 最新对话轮询。"""
from __future__ import annotations

import json
import random
import string
from typing import Optional

from .account import MiAccount, SID_MINA, UA_MINA

MINA_BASE = "https://api2.mina.mi.com"


def _request_id() -> str:
    return "app_ios_" + "".join(random.choices(string.ascii_letters + string.digits, k=30))


class MiNA:
    def __init__(self, account: MiAccount):
        self.account = account

    # ------------------------------------------------------------------
    def _get(self, uri: str) -> dict:
        return self.account.request(MINA_BASE + uri + "&requestId=" + _request_id(),
                                    headers={"User-Agent": UA_MINA})

    def _post(self, uri: str, data: dict) -> dict:
        data["requestId"] = _request_id()
        return self.account.request(MINA_BASE + uri, data=data, headers={"User-Agent": UA_MINA})

    def _ubus(self, device_id: str, method: str, path: str, message: dict) -> dict:
        return self._post("/remote/ubus", {
            "deviceId": device_id,
            "message": json.dumps(message),
            "method": method,
            "path": path,
        })

    # ------------------------------------------------------------------
    def device_list(self) -> list[dict]:
        result = self._get("/admin/v2/device_list?master=0")
        return result.get("data") or []

    def tts(self, device_id: str, text: str) -> bool:
        res = self._ubus(device_id, "text_to_speech", "mibrain", {"text": text})
        return res.get("code") == 0

    def latest_asks(self, device_id: str) -> list[dict]:
        """获取音箱最近几轮对话，返回 [{request_id, timestamp_ms, query, answer}]。

        对应 MiService 的 nlp_result_get ubus 调用
        （MIT，© 2021-2026 Yonsm，https://github.com/Yonsm/MiService）。
        """
        out: list[dict] = []
        try:
            res = self._ubus(device_id, "nlp_result_get", "mibrain", {})
        except Exception:
            return out
        data = res.get("data") or {}
        if not isinstance(data, dict) or data.get("code") != 0:
            return out
        try:
            items = json.loads(data.get("info") or "{}").get("result", [])
        except (json.JSONDecodeError, TypeError):
            return out
        for item in items:
            if "nlp" not in item:
                continue
            try:
                nlp = json.loads(item["nlp"])
                meta = nlp.get("meta", {})
                answers = nlp.get("response", {}).get("answer", [])
                query = ""
                if answers:
                    first = answers[0]
                    intention = first.get("intention") or {}
                    if isinstance(intention, dict):
                        query = intention.get("query", "")
                out.append({
                    "request_id": str(meta.get("request_id", "")),
                    "timestamp_ms": int(meta.get("timestamp", 0)),
                    "query": query,
                    "answer": str(answers[0]["content"]) if answers else "",
                })
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
        return out

    @staticmethod
    def pick_speaker(devices: list[dict]) -> Optional[dict]:
        """从设备列表中选出第一个支持云 TTS 的小爱设备。"""
        for d in devices:
            caps = d.get("capabilities") or {}
            if isinstance(caps, str):
                try:
                    caps = json.loads(caps)
                except json.JSONDecodeError:
                    caps = {}
            if d.get("hardware") and d.get("deviceID"):
                return d
        return None
