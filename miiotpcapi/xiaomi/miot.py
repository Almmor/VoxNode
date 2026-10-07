"""米家（MIoT / MiIO）云服务客户端。

可在已登录的小米账号下：列出米家设备、读取/设置设备属性、调用设备动作。
请求签名算法与接口路径参考 Yonsm/MiService（MIT，© 2021-2026 Yonsm）。

要点：
  - 服务域名 https://api.io.mi.com/app，service id 为 xiaomiio
  - 请求为表单 POST，字段 data / nonce / signature
  - signature = base64(HMAC-SHA256(key=base64decode(signed_nonce),
                 msg="&".join([uri, signed_nonce, nonce, "data=" + data_json])))
  - signed_nonce = base64(sha256(base64decode(ssecurity) + base64decode(nonce)))
"""
from __future__ import annotations

import json
import time
from base64 import b64decode, b64encode
from hashlib import sha256
from hmac import new as hmac_new
from os import urandom
from typing import Any, Iterable, Optional

from .account import MiAccount, SID_MIIO, UA_MIIO

MIOT_BASE = "https://api.io.mi.com/app"
# 米家 App 在局域网/云 RPC 中使用的固定 accessKey
_ACCESS_KEY = "IOS00026747c5acafc2"

# MIoT 通用约定：service 2 的 property 1 通常是「开关」
POWER_IID = (2, 1)


class MiIOError(Exception):
    pass


# ---------------------------------------------------------------- 签名
def sign_nonce(ssecurity: str, nonce: str) -> str:
    m = sha256()
    m.update(b64decode(ssecurity))
    m.update(b64decode(nonce))
    return b64encode(m.digest()).decode()


def sign_data(uri: str, data: str, ssecurity: str) -> dict:
    """生成米家接口所需的 data / nonce / signature 表单字段。"""
    nonce = b64encode(urandom(8) + int(time.time() / 60).to_bytes(4, "big")).decode()
    snonce = sign_nonce(ssecurity, nonce)
    msg = "&".join([uri, snonce, nonce, "data=" + data])
    signature = hmac_new(key=b64decode(snonce), msg=msg.encode(), digestmod=sha256).digest()
    return {"data": data, "nonce": nonce, "signature": b64encode(signature).decode()}


# ---------------------------------------------------------------- 客户端
class MiIO:
    """米家云服务客户端（同步）。"""

    def __init__(self, account: MiAccount, server: str = MIOT_BASE):
        self.account = account
        self.server = server

    # -- 底层请求 ------------------------------------------------------
    def _signer(self, uri: str):
        def sign(data: Any, token: dict, cookies: dict, headers: dict) -> dict:
            cookies["PassportDeviceId"] = token.get("deviceId", "")
            headers["User-Agent"] = UA_MIIO
            headers["x-xiaomi-protocal-flag-cli"] = "PROTOCAL-HTTP2"
            payload = data if isinstance(data, str) else json.dumps(data)
            return sign_data(uri, payload, token[SID_MIIO][0])
        return sign

    def request(self, uri: str, data: Any) -> Any:
        """发起一次已签名的米家接口请求，返回 result 字段。"""
        if not self.account.is_logged_in(SID_MIIO):
            self.account.login(SID_MIIO)
        resp = self.account.raw_request(
            SID_MIIO, self.server + uri, data, sign=self._signer(uri),
            headers={"User-Agent": UA_MIIO},
        )
        if not isinstance(resp, dict) or "result" not in resp:
            raise MiIOError(f"米家接口返回异常: {resp}")
        return resp["result"]

    # -- 设备 / 家庭 ----------------------------------------------------
    def device_list(self) -> list[dict]:
        """账号下的米家设备列表（含 did / 名称 / 型号 / 在线状态）。"""
        result = self.request("/home/device_list", {
            "getVirtualModel": False, "getHuamiDevices": 0,
        })
        items = (result or {}).get("list") or []
        devices = []
        for it in items:
            did = it.get("did")
            if not did:
                continue
            devices.append({
                "did": did,
                "name": it.get("name") or it.get("model") or did,
                "model": it.get("model", ""),
                "online": bool(it.get("isOnline", it.get("online", False))),
                "room": it.get("room_name") or "",
                "token": it.get("token", ""),
            })
        return devices

    def rooms(self) -> dict[str, str]:
        """返回 did -> 房间名 的映射。"""
        try:
            result = self.request("/homeroom/gethome", {})
        except Exception:
            return {}
        homelist = result if isinstance(result, list) else (result or {}).get("homelist", [])
        mapping: dict[str, str] = {}
        for home in homelist or []:
            for room in home.get("roomlist", []) or []:
                for did in room.get("dids", []) or []:
                    mapping[str(did)] = room.get("name", "")
        return mapping

    def device_list_with_room(self) -> list[dict]:
        """设备列表并补上房间名。"""
        devices = self.device_list()
        try:
            rooms = self.rooms()
        except Exception:
            rooms = {}
        for d in devices:
            if not d.get("room"):
                d["room"] = rooms.get(str(d["did"]), "")
        return devices

    # -- 属性读写 / 动作 ------------------------------------------------
    def get_props(self, did: str, iids: Iterable[tuple[int, int]]) -> list:
        """读取属性，返回与 iids 等长的值列表（失败为 None）。"""
        params = [{"did": did, "siid": s, "piid": p} for s, p in iids]
        result = self.request("/miotspec/prop/get", {"params": params})
        if not isinstance(result, list):
            raise MiIOError(f"读取属性返回异常: {result}")
        return [it.get("value") if it.get("code") == 0 else None for it in result]

    def get_prop(self, did: str, siid: int, piid: int):
        return self.get_props(did, [(siid, piid)])[0]

    def set_props(self, did: str, props: Iterable[tuple[int, int, Any]]) -> list[int]:
        """写入属性，返回与 props 等长的状态码列表（0 为成功）。"""
        params = [{"did": did, "siid": s, "piid": p, "value": v} for s, p, v in props]
        result = self.request("/miotspec/prop/set", {"params": params})
        if not isinstance(result, list):
            raise MiIOError(f"写入属性返回异常: {result}")
        return [it.get("code", -1) for it in result]

    def set_prop(self, did: str, siid: int, piid: int, value: Any) -> int:
        return self.set_props(did, [(siid, piid, value)])[0]

    def action(self, did: str, siid: int, aiid: int, args: Optional[list] = None) -> int:
        """调用设备动作，返回状态码（0 为成功）。"""
        result = self.request("/miotspec/action", {
            "params": {"did": did, "siid": siid, "aiid": aiid, "in": args or []},
        })
        if isinstance(result, dict):
            return result.get("code", -1)
        return -1

    # -- 老版 RPC（部分设备仍然只支持） ---------------------------------
    def legacy_get_props(self, did: str, props: list[str]) -> list:
        return self.request(f"/home/rpc/{did}", {
            "id": 1, "method": "get_prop", "accessKey": _ACCESS_KEY, "params": props,
        })

    def legacy_set_prop(self, did: str, prop: str, value: Any) -> int:
        result = self.request(f"/home/rpc/{did}", {
            "id": 1, "method": f"set_{prop}", "accessKey": _ACCESS_KEY,
            "params": value if isinstance(value, list) else [value],
        })
        first = result[0] if isinstance(result, list) and result else result
        if first == "ok":
            return 0
        return first if isinstance(first, int) else -1

    # -- 开关便捷方法 ----------------------------------------------------
    def get_power(self, did: str) -> Optional[bool]:
        """读取开关状态：先试 MIoT 约定，再退回老版 RPC。"""
        try:
            value = self.get_props(did, [POWER_IID])[0]
            if value is not None:
                return bool(value)
        except Exception:
            pass
        try:
            value = self.legacy_get_props(did, ["power"])[0]
            return str(value).lower() in ("on", "true", "1")
        except Exception:
            return None

    def set_power(self, did: str, on: bool) -> bool:
        """设置开关：先试 MIoT，再退回老版 RPC。"""
        try:
            if self.set_props(did, [(POWER_IID[0], POWER_IID[1], bool(on))])[0] == 0:
                return True
        except Exception:
            pass
        try:
            return self.legacy_set_prop(did, "power", "on" if on else "off") == 0
        except Exception:
            return False
