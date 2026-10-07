"""miiotpcapi — 将 Windows 电脑接入小米生态的 Python 库。

提供电源控制、屏幕截取、进程与系统监控、系统信息、
Wake-on-LAN、应用管理，以及小米账号 / 小爱音箱桥接能力，
可用于构建自己的电脑控制软件（如 MiPC Bridge / 小爱电脑管家）。

本项目的登录与音箱控制协议实现参考了以下 MIT 协议的开源项目：
  - Yonsm/MiService      (c) 2021-2026 Yonsm
  - hanxi/xiaomusic      (c) 2023 涵曦
本项目同样以 MIT 协议发布，并保留上述项目的版权与许可声明，
详见 LICENSE 与 THIRD_PARTY_NOTICES.md 中的致谢说明。
"""

__version__ = "0.1.0"
APP_NAME = "MiPC Bridge"
APP_NAME_ZH = "小爱电脑管家"
