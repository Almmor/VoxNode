"""Wake-on-LAN：发送魔术包唤醒局域网设备，并提供本机 WOL 信息。"""
from __future__ import annotations

import re
import socket
import subprocess

MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")


def normalize_mac(mac: str) -> str:
    mac = mac.strip().replace(" ", "").replace("-", ":").upper()
    if not MAC_RE.match(mac):
        raise ValueError(f"无效的 MAC 地址: {mac}")
    return mac


def send(mac: str, ip: str = "255.255.255.255", port: int = 9) -> None:
    """向目标 MAC 发送 WOL 魔术包（6 字节 0xFF + 16 次重复 MAC，默认全网广播）。"""
    mac = normalize_mac(mac)
    packet = b"\xff" * 6 + bytes.fromhex(mac.replace(":", "")) * 16
    target = ip if ip and ip not in ("", "0.0.0.0") else "255.255.255.255"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(packet, (target, port))


def wake(name_or_mac: str, hosts: list[dict]) -> bool:
    """按配置中的名称或 MAC 唤醒主机，返回是否找到并已发送。"""
    key = name_or_mac.strip().lower()
    for h in hosts:
        if key in (h.get("name", "").lower(), h.get("mac", "").lower()):
            send(h["mac"], h.get("ip", "255.255.255.255"), int(h.get("port", 9) or 9))
            return True
    raise KeyError(f"未找到名为「{name_or_mac}」的唤醒目标，请先在 VoxNode 中添加")


def wake_armed_devices() -> list[str]:
    """列出当前允许唤醒本机的设备（powercfg 查询）。"""
    try:
        out = subprocess.run(
            ["powercfg", "/devicequery", "wake_armed"],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        text = (out.stdout or b"").decode("utf-8", errors="replace")
        return [l.strip() for l in text.splitlines() if l.strip()]
    except Exception:
        return []
