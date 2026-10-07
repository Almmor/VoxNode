"""命令行入口：python -m miiotpcapi <command>

用法示例：
  python -m miiotpcapi status          查看系统状态
  python -m miiotpcapi shot            截图
  python -m miiotpcapi power lock      锁屏（lock/sleep/hibernate/signout/cancel）
  python -m miiotpcapi wol AA:BB:CC:DD:EE:FF   发送唤醒包
"""
from __future__ import annotations

import sys

from .core import power, screenshot, sysinfo, wol
from .config import SCREENSHOT_DIR


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = args[0]
    if cmd == "status":
        for k, v in sysinfo.summary().items():
            print(f"{k:14}: {v}")
    elif cmd == "shot":
        path = screenshot.capture(args[1] if len(args) > 1 else SCREENSHOT_DIR)
        print(path)
    elif cmd == "power":
        if len(args) < 2:
            print("用法: power <shutdown|restart|lock|sleep|hibernate|signout|cancel> [延迟秒]")
            return 2
        if args[1] == "cancel":
            power.cancel()
        else:
            power.execute(args[1], int(args[2]) if len(args) > 2 else 0)
        print(f"已执行: {args[1]}")
    elif cmd == "wol":
        if len(args) < 2:
            print("用法: wol <MAC地址|配置名>")
            return 2
        from .config import Config
        cfg = Config()
        wol.wake(args[1], cfg.get("wol", []))
        print(f"已发送唤醒包: {args[1]}")
    else:
        print(f"未知命令: {cmd}\n")
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
