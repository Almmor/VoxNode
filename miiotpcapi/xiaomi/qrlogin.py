"""小米账号扫码登录。

流程（基于公开的第三方实现交叉验证）：
  1. GET /pass/serviceLogin?sid=...        取 qs / _sign / callback
  2. GET /longPolling/loginUrl?....        取 qr(二维码图) / loginUrl(二维码内容) / lp(长轮询地址)
  3. 循环 GET <lp>                          用户米家 App 扫码并确认后返回 passToken + userId
  4. 用 passToken 通过 MiAccount.login_with_pass_token() 换取各业务 sid 的 serviceToken

注意：这是未公开协议，字段可能变化；本模块对 code 做了兜底处理。
"""
from __future__ import annotations

import time
from typing import Optional
from urllib.parse import quote

import requests

from .account import ACCOUNT_BASE, UA_LOGIN, _parse_resp, _rand

# 长轮询状态
WAITING = "waiting"      # 未扫描 / 已扫描待确认
SCANNED = "scanned"      # 已扫描，等待用户在手机上确认
CONFIRMED = "confirmed"  # 已确认
EXPIRED = "expired"      # 二维码过期，需要重新获取
FAILED = "failed"

# 视为二维码失效的返回码
_EXPIRED_CODES = {90002, 2002, 10003}
# 视为等待中的返回码
_WAITING_CODES = {87001}


class QrLoginError(Exception):
    pass


class XiaomiQrLogin:
    """一次扫码登录会话。"""

    def __init__(self, sid: str = "mijia", qr_size: int = 300,
                 poll_timeout: float = 35.0, session: Optional[requests.Session] = None):
        self.sid = sid
        self.qr_size = qr_size
        self.poll_timeout = poll_timeout
        self.device_id = _rand(16).upper()

        self.qr_image_url = ""      # 二维码图片地址
        self.login_url = ""         # 二维码真正编码的内容
        self.lp = ""                # 长轮询地址
        self.expires_in = 300
        self.status = WAITING
        self.error = ""

        # 扫码确认后填充
        self.pass_token = ""
        self.user_id = ""
        self.c_user_id = ""
        self.ssecurity = ""
        self.location = ""

        self._session = session or requests.Session()

    # ------------------------------------------------------------------
    def start(self) -> None:
        """发起一次扫码会话，成功后可用 fetch_qr_image() 显示二维码。"""
        self.status = WAITING
        self.error = ""
        headers = {"User-Agent": UA_LOGIN}
        cookies = {"sdkVersion": "3.9", "deviceId": self.device_id}

        # Step 1：取 qs / _sign / callback
        r = self._session.get(
            f"{ACCOUNT_BASE}/pass/serviceLogin?sid={self.sid}&_json=true",
            headers=headers, cookies=cookies, timeout=30)
        r.raise_for_status()
        info = _parse_resp(r.text)
        if not info.get("qs"):
            if info.get("location"):
                raise QrLoginError("该账号会话仍然有效，无需扫码登录")
            raise QrLoginError(f"获取登录参数失败: {info}")

        # Step 2：申请二维码与长轮询地址
        params = {
            "_qrsize": str(self.qr_size),
            "qs": quote(info["qs"], safe=""),
            "sid": info.get("sid", self.sid),
            "_sign": info.get("_sign", ""),
            "callback": info.get("callback", ""),
            "_json": "true",
            "_locale": "zh_CN",
            "_hasLogo": "false",
            "_dc": str(int(time.time() * 1000)),
        }
        r = self._session.get(f"{ACCOUNT_BASE}/longPolling/loginUrl",
                              params=params, headers=headers, cookies=cookies, timeout=30)
        r.raise_for_status()
        data = _parse_resp(r.text)
        if data.get("code") not in (0, None) or not data.get("lp"):
            raise QrLoginError(f"申请二维码失败: {data.get('desc') or data}")

        self.qr_image_url = data.get("qr", "")
        self.login_url = data.get("loginUrl", "")
        self.lp = data["lp"]
        if self.lp and not self.lp.startswith("http"):
            self.lp = ACCOUNT_BASE + self.lp
        try:
            self.expires_in = int(data.get("timeout", 300))
        except (TypeError, ValueError):
            self.expires_in = 300

    def fetch_qr_image(self) -> bytes:
        """下载二维码图片（PNG 字节），可直接交给 GUI 显示。"""
        if not self.qr_image_url:
            raise QrLoginError("尚未申请二维码，请先调用 start()")
        r = self._session.get(self.qr_image_url, timeout=30)
        r.raise_for_status()
        return r.content

    # ------------------------------------------------------------------
    def poll(self) -> str:
        """长轮询一次，返回 WAITING / SCANNED / CONFIRMED / EXPIRED / FAILED。"""
        if self.status in (CONFIRMED, EXPIRED, FAILED):
            return self.status
        if not self.lp:
            self.status = FAILED
            self.error = "尚未申请二维码"
            return self.status
        url = f"{self.lp}&_dc={int(time.time() * 1000)}"
        try:
            r = self._session.get(url, timeout=self.poll_timeout)
        except requests.Timeout:
            return WAITING          # 服务端挂起超时 == 用户还没扫码
        except requests.RequestException as e:
            self.error = str(e)
            return WAITING

        if r.status_code == 403:
            self.status = EXPIRED
            return self.status
        if r.status_code >= 400:
            self.error = f"HTTP {r.status_code}"
            return WAITING

        data = _parse_resp(r.text)
        code = data.get("code", -1)

        if code == 0 and data.get("passToken"):
            self.pass_token = data.get("passToken", "")
            self.user_id = str(data.get("userId", ""))
            self.c_user_id = str(data.get("cUserId", ""))
            self.ssecurity = data.get("ssecurity", "")
            self.location = data.get("location", "")
            self.status = CONFIRMED
            return self.status

        if code in _EXPIRED_CODES:
            self.status = EXPIRED
            return self.status
        if code in _WAITING_CODES:
            self.status = WAITING
            return self.status
        if code == 0:
            # 正常返回但没有 passToken —— 已扫码，等待手机端确认
            self.status = SCANNED
            return self.status

        self.error = data.get("desc") or str(data)
        self.status = WAITING
        return self.status
