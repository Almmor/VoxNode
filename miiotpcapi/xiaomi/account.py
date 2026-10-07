"""小米账号登录（同步版）。

登录流程参考 Yonsm/MiService（MIT，© 2021-2026 Yonsm）的公开实现，以其协议为准：
1. GET  /pass/serviceLogin?sid=...  获取 qs / _sign / callback
2. POST /pass/serviceLoginAuth2     提交账号 + MD5(密码)
3. GET  location&clientSign=...     换取 serviceToken
支持 OTP（短信/邮箱验证码）与 passToken 会话续期。
"""
from __future__ import annotations

import hashlib
import json
import random
import re
import string
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import quote, urlparse, parse_qs

import requests

ACCOUNT_BASE = "https://account.xiaomi.com"
JSON_PREFIX = "&&&START&&&"

UA_LOGIN = (
    "APP/com.xiaomi.mihome APPV/11.3.203 iosPassportSDK/4.2.50 iOS/26.3.1 "
    "MK/aVBob25lMTcsMg== DEVT/aVBob25l DEVS/aU9T BRA/QXBwbGU= L/zh_CN"
)
UA_OTP = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Mobile/15E148 MiHome/11.3.203"
)
UA_MINA = "MiHome/6.0.103 (com.xiaomi.mihome; build:6.0.103.1; iOS 14.4.0) Alamofire/6.0.103 MICO/iOSApp/appStore/6.0.103"

SID_MINA = "micoapi"  # MiNA（小爱音箱）使用的 service id


class XiaomiAuthError(Exception):
    pass


def _rand(length: int) -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=length))


def _parse_resp(raw: str) -> dict:
    if raw.startswith(JSON_PREFIX):
        raw = raw[len(JSON_PREFIX):]
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        raise XiaomiAuthError(f"小米账号接口返回了无法解析的内容: {raw[:120]}")


class MiAccount:
    """管理小米账号登录、serviceToken 缓存与带会话的 API 请求（线程安全）。"""

    def __init__(self, username: str, password: str,
                 token_path: Optional[Path] = None,
                 otp_callback: Optional[Callable[[str], str]] = None):
        self.username = username
        self.password = password
        self.token_path = Path(token_path) if token_path else None
        self.otp_callback = otp_callback
        self.token: dict = {}
        self._lock = threading.RLock()
        self._session = requests.Session()
        self._load_token()

    # -- token 持久化 --------------------------------------------------
    def _load_token(self) -> None:
        if self.token_path and self.token_path.is_file():
            try:
                self.token = json.loads(self.token_path.read_text("utf-8"))
            except Exception:
                self.token = {}

    def _save_token(self, token: Optional[dict] = None) -> None:
        if not self.token_path:
            return
        if token:
            try:
                self.token_path.parent.mkdir(parents=True, exist_ok=True)
                self.token_path.write_text(json.dumps(token, indent=2), "utf-8")
            except Exception:
                pass
        elif self.token_path.is_file():
            try:
                self.token_path.unlink()
            except Exception:
                pass

    # -- 登录 ----------------------------------------------------------
    def login(self, sid: str = SID_MINA) -> bool:
        """登录并缓存 serviceToken。需要验证码时通过 otp_callback 获取。"""
        with self._lock:
            if not self.token.get("deviceId"):
                self.token["deviceId"] = _rand(16).upper()
            try:
                resp = self._service_login(f"serviceLogin?sid={sid}&_json=true")
                if resp.get("code") != 0:
                    data = {
                        "_json": "true",
                        "qs": resp["qs"],
                        "sid": resp["sid"],
                        "_sign": resp["_sign"],
                        "callback": resp["callback"],
                        "user": self.username,
                        "hash": hashlib.md5(self.password.encode()).hexdigest().upper(),
                    }
                    resp = self._service_login("serviceLoginAuth2", data)
                    if resp.get("code") != 0:
                        raise XiaomiAuthError(f"账号或密码错误: {resp.get('description', resp)}")
                    if ntf := resp.get("notificationUrl"):
                        resp = self._verify_otp(sid, ntf)
                for key in ("userId", "passToken", "location", "nonce", "ssecurity"):
                    if key not in resp:
                        raise XiaomiAuthError(f"登录响应缺少 {key}: {resp}")
                self.token["userId"] = resp["userId"]
                self.token["passToken"] = resp["passToken"]
                service_token = self._security_token_service(resp["location"], resp["nonce"], resp["ssecurity"])
                self.token[sid] = [resp["ssecurity"], service_token]
                self._save_token(self.token)
                return True
            except Exception:
                self.token = {}
                self._save_token()
                raise

    def _service_login(self, uri: str, data: Optional[dict] = None) -> dict:
        headers = {"User-Agent": UA_LOGIN}
        cookies = {"sdkVersion": "3.9", "deviceId": self.token["deviceId"]}
        if "passToken" in self.token:
            cookies["userId"] = str(self.token["userId"])
            cookies["passToken"] = self.token["passToken"]
        url = f"{ACCOUNT_BASE}/pass/{uri}"
        if data is None:
            r = self._session.get(url, cookies=cookies, headers=headers, timeout=30)
        else:
            r = self._session.post(url, data=data, cookies=cookies, headers=headers, timeout=30)
        r.raise_for_status()
        return _parse_resp(r.text)

    def _security_token_service(self, location: str, nonce: str, ssecurity: str) -> str:
        client_sign = hashlib.sha1(f"nonce={nonce}&{ssecurity}".encode()).digest()
        import base64
        sign = quote(base64.b64encode(client_sign).decode())
        r = self._session.get(f"{location}&clientSign={sign}", timeout=30)
        service_token = r.cookies.get("serviceToken")
        if not service_token:
            raise XiaomiAuthError(f"获取 serviceToken 失败: {r.text[:200]}")
        return service_token

    def _verify_otp(self, sid: str, ntf: str) -> dict:
        """OTP 两步验证（短信优先）。"""
        if not self.otp_callback:
            raise XiaomiAuthError("需要短信/邮箱验证码，但未提供输入回调")
        if not ntf.startswith("http"):
            ntf = ACCOUNT_BASE + ntf
        headers = {"User-Agent": UA_OTP}
        cookies = {"deviceId": self.token["deviceId"]}
        self._session.get(ntf, cookies=cookies, headers=headers, timeout=30)

        qs = parse_qs(urlparse(ntf).query)
        context = qs.get("context", [""])[0]
        sid_param = qs.get("sid", [sid])[0]
        list_url = f"{ACCOUNT_BASE}/identity/list?sid={sid_param}&supportedMask=0&_locale=zh_CN&context={context}"
        idata = _parse_resp(self._session.get(list_url, cookies=cookies, headers=headers, timeout=30).text)
        flag = idata.get("flag", 4)
        method = "Email" if flag == 8 else "Phone"

        tresp = _parse_resp(self._session.get(
            f"{ACCOUNT_BASE}/identity/auth/verify{method}?_flag={flag}&_json=true",
            cookies=cookies, headers=headers, timeout=30).text)
        if tresp.get("code") not in (0, None):
            raise XiaomiAuthError(f"触发{method}验证码失败: {tresp}")
        if method == "Phone":
            sresp = _parse_resp(self._session.post(
                f"{ACCOUNT_BASE}/identity/auth/sendPhoneTicket",
                data={"retry": "0", "icode": "", "_json": "true"},
                cookies=cookies, headers=headers, timeout=30).text)
            if sresp.get("code") not in (0, None):
                raise XiaomiAuthError(f"发送短信验证码失败: {sresp}")

        code = (self.otp_callback(method) or "").strip()
        if not code:
            raise XiaomiAuthError("未提供验证码")
        vresp = _parse_resp(self._session.post(
            f"{ACCOUNT_BASE}/identity/auth/verify{method}?_dc={int(time.time() * 1000)}",
            data={"_flag": str(flag), "ticket": code, "trust": "false", "_json": "true"},
            cookies=cookies, headers=headers, timeout=30).text)
        location = vresp.get("location")
        if not location:
            raise XiaomiAuthError(f"验证码校验失败: {vresp}")
        if not location.startswith("http"):
            location = ACCOUNT_BASE + location
        self._session.get(location, cookies=cookies, headers=headers, timeout=30)
        resp = self._service_login(f"serviceLogin?sid={sid}&_json=true")
        if resp.get("code") == 0:
            return resp
        raise XiaomiAuthError(f"验证码验证成功但登录恢复失败: {resp}")

    # -- 业务请求 ------------------------------------------------------
    def is_logged_in(self, sid: str = SID_MINA) -> bool:
        return bool(self.token.get(sid)) and bool(self.token.get("userId"))

    def request(self, url: str, data: Optional[dict] = None, headers: Optional[dict] = None,
                relogin: bool = True) -> dict:
        """带登录态的 API 请求；401/鉴权失效时自动重登一次。"""
        with self._lock:
            if not self.is_logged_in() and not self.login():
                raise XiaomiAuthError("登录失败")
            cookies = {
                "userId": str(self.token["userId"]),
                "serviceToken": self.token[SID_MINA][1],
            }
            method = "GET" if data is None else "POST"
            r = self._session.request(method, url, data=data, cookies=cookies,
                                     headers=headers or {"User-Agent": UA_MINA}, timeout=30)
            if r.status_code == 401:
                if relogin:
                    self.token = {}
                    self._save_token()
                    return self.request(url, data, headers, relogin=False)
                raise XiaomiAuthError(f"鉴权失败(HTTP 401): {url}")
            try:
                resp = r.json()
            except ValueError:
                raise XiaomiAuthError(f"接口响应不是 JSON: {url} -> {r.text[:200]}")
            if resp.get("code", -1) == 0:
                return resp
            if "auth" in str(resp.get("message", "")).lower():
                if relogin:
                    self.token = {}
                    self._save_token()
                    return self.request(url, data, headers, relogin=False)
                raise XiaomiAuthError(f"鉴权失败: {url} -> {resp.get('message')}")
            raise XiaomiAuthError(f"接口返回错误: {url} -> {resp}")


def logout(token_path: Path) -> None:
    MiAccount("", "", token_path=token_path)._save_token()
