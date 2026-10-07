"""miiotpcapi —— 把 Windows 电脑接入小米智能家居生态的 Python 库。

提供电源控制、屏幕截取、进程与系统监控、系统信息、Wake-on-LAN、应用管理，
以及小米账号登录（密码 / 扫码）、小爱音箱语音桥接、米家设备控制与
「米家指令通道」（用米家设备属性反向控制本机）。

配套图形软件：VoxNode（声枢）—— 见 voxnode/ 包。

本项目的登录、小爱音箱与米家云 API 实现参考了以下 MIT 协议的开源项目：
  - Yonsm/MiService      (c) 2021-2026 Yonsm
  - hanxi/xiaomusic      (c) 2023 涵曦
本项目同样以 MIT 协议发布，并保留上述项目的版权与许可声明，
详见 LICENSE 与 THIRD_PARTY_NOTICES.md。
"""

__version__ = "0.2.0"
APP_NAME = "VoxNode"
APP_NAME_ZH = "声枢"
