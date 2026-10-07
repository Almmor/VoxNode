"""小米账号密码的安全存储：使用 Windows DPAPI 加密后写入配置。"""
from __future__ import annotations

import base64
import ctypes
import ctypes.wintypes as wt

from .config import Config

_entropy = b"VoxNode-v1"
# 旧版本（当时的名字是 MiPC Bridge）加密时使用的 entropy，用于解密历史数据
_legacy_entropy = b"MiPCBridge-v1"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wt.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _unblob(blob: _DATA_BLOB) -> bytes:
    out = ctypes.string_at(blob.pbData, blob.cbData)
    ctypes.windll.kernel32.LocalFree(blob.pbData)
    return out


def protect(data: bytes) -> bytes:
    out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(_blob(data)), None, ctypes.byref(_blob(_entropy)),
        None, None, 0, ctypes.byref(out),
    ):
        raise OSError("CryptProtectData failed")
    return _unblob(out)


def unprotect(data: bytes) -> bytes:
    """解密；兼容旧品牌名时期的密文。"""
    for entropy in (_entropy, _legacy_entropy):
        out = _DATA_BLOB()
        if ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(_blob(data)), None, ctypes.byref(_blob(entropy)),
            None, None, 0, ctypes.byref(out),
        ):
            return _unblob(out)
    raise OSError("CryptUnprotectData failed")


def save_password(config: Config, password: str) -> None:
    enc = base64.b64encode(protect(password.encode("utf-8"))).decode("ascii")
    config.set("xiaomi.password_enc", enc)
    config.set("xiaomi.save_password", True, save=False)


def load_password(config: Config) -> str:
    enc = config.get("xiaomi.password_enc", "")
    if not enc:
        return ""
    try:
        return unprotect(base64.b64decode(enc)).decode("utf-8")
    except Exception:
        return ""


def clear_password(config: Config) -> None:
    config.set("xiaomi.password_enc", "", save=False)
    config.set("xiaomi.save_password", False, save=False)
    config.save()
