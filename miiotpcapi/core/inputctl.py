"""输入控制：音量 / 播放 / 暂停等媒体键（Windows user32 keybd_event）。"""
from __future__ import annotations

import ctypes

VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT = 0xB0
VK_MEDIA_PREV = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3

_KEYEVENTF_KEYUP = 0x0002


def _tap(vk: int, times: int = 1) -> None:
    for _ in range(max(1, times)):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)


def volume_up(times: int = 2) -> None:
    _tap(VK_VOLUME_UP, times)


def volume_down(times: int = 2) -> None:
    _tap(VK_VOLUME_DOWN, times)


def mute() -> None:
    _tap(VK_VOLUME_MUTE)


def play_pause() -> None:
    _tap(VK_MEDIA_PLAY_PAUSE)


def next_track() -> None:
    _tap(VK_MEDIA_NEXT)


def prev_track() -> None:
    _tap(VK_MEDIA_PREV)


ACTIONS = {
    "volume_up": volume_up,
    "volume_down": volume_down,
    "mute": mute,
    "play_pause": play_pause,
    "next_track": next_track,
    "prev_track": prev_track,
}
