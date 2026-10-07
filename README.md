# MiPC Bridge · 小爱电脑管家

> 把小爱音箱变成你电脑的语音管家 —— 说一句「关机」「截屏」「打开浏览器」，电脑就照做。

`miiotpcapi` 是一个把 **Windows 电脑接入小米生态** 的 Python 库，附带一款基于 **PyQt6** 的图形控制软件
（MiPC Bridge / 小爱电脑管家）。它通过小米账号登录后轮询小爱音箱的对话记录，把语音指令映射为电脑操作；
同时提供电源控制、屏幕截取、进程管理、系统监控、网络唤醒（WOL）等本地功能。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://pypi.org/project/PyQt6/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6.svg)](#)

---

## 功能特性

**小米生态接入**

- 小米账号登录（含短信 / 邮箱 OTP 两步验证），密码用 Windows DPAPI 加密后仅存本机
- 自动发现账号下的小爱音箱，轮询其对话记录，将语音指令映射为电脑操作
- 执行结果可通过小爱音箱 TTS 语音播报
- 语音指令规则可视化编辑，支持正则与自定义回复

**本机控制能力**

| 模块 | 能力 |
|------|------|
| 电源控制 | 关机 / 重启 / 锁屏 / 睡眠 / 休眠 / 注销 / 定时关机 / 取消 |
| 屏幕截取 | 全屏或指定显示器截图，预览与历史记录 |
| 进程管理 | 按内存排序、搜索、结束进程 |
| 系统监控 | CPU / 内存 / 磁盘 / 网络 / 运行时长实时仪表盘 |
| 应用任务 | 别名注册表，语音「打开 XX」「关闭 XX」 |
| 网络唤醒 | WOL 魔术包，唤醒局域网内其他电脑，并显示本机 WOL 状态 |

**易用性**

- **首次运行引导式部署向导**：环境自检 → 账号登录 → 选择音箱 → 指令预览 → 完成设置，全程约 2 分钟
- 系统托盘常驻，关闭窗口不退出，桥接在后台持续运行
- 开机自启（当前用户注册表 `Run` 键，无需管理员权限）
- 深色主题，小米橙配色

---

## 首次部署（引导式）

安装依赖后启动程序，**首次运行会自动进入部署向导**：

1. **环境自检** —— 检查 Python 版本、PyQt6 / psutil / mss 是否就绪、操作系统是否为 Windows
2. **登录小米账号** —— 填写小米账号密码；若触发安全验证，会弹出验证码输入框
3. **选择小爱音箱** —— 自动拉取账号下的音箱设备列表
4. **查看语音指令** —— 预览默认支持的语音指令
5. **完成设置** —— 勾选开机自启 / 最小化启动 / 立即启动桥接

向导可随时通过 `python -m mipcb --setup` 重新运行。配置保存在 `~/.miiotpcapi/config.json`。

> **开机（WOL）提示**：小爱音箱无法直接发送 WOL 魔术包。若要「对小爱说一句话就把关机的电脑开起来」，
> 推荐用 **米家智能插座** 控制电脑供电，并在主板 BIOS 中开启「断电恢复后自动开机（AC Power Loss → Power On）」，
> 这样对小爱说「打开插座」即可实现远程开机。本软件的 WOL 模块则用于从本机唤醒 **其他** 局域网设备。

---

## 快速开始

### 1. 环境要求

- Windows 10 / 11
- Python 3.10 及以上（**推荐 3.12**；请勿使用过新的 Python 版本，PyQt6 预编译包可能尚未覆盖）

### 2. 安装

```powershell
git clone https://github.com/Almmor/miiotpcapi.git
cd miiotpcapi

# 建议使用虚拟环境
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt
```

### 3. 运行

```powershell
# 图形界面（首次运行会自动进入部署向导）
python run_app.pyw

# 或作为模块运行
python -m mipcb

# 强制重新运行部署向导 / 最小化启动
python -m mipcb --setup
python -m mipcb --minimized
```

也可以安装为命令：

```powershell
pip install -e .
mipcb
```

---

## 作为 Python 库使用

`miiotpcapi` 的核心能力不依赖 GUI，可在脚本或服务中直接调用。

### 本机控制

```python
from miiotpcapi.core import power, screenshot, monitor, sysinfo, wol
from miiotpcapi.config import SCREENSHOT_DIR

# 电源
power.lock()                       # 锁屏
power.shutdown(delay=60)           # 60 秒后关机
power.cancel()                     # 取消关机

# 截图
path = screenshot.capture(SCREENSHOT_DIR)
print("已保存到", path)

# 系统信息
print(sysinfo.summary())
print(sysinfo.status_text())       # 可直接用于语音播报

# 进程
for p in monitor.processes()[:5]:
    print(p["pid"], p["name"], f"{p['mem'] / 1024**2:.0f} MB")

# 网络唤醒
wol.send("AA:BB:CC:DD:EE:FF")      # 广播魔术包
```

### 语音指令匹配与执行

```python
from miiotpcapi.config import Config
from miiotpcapi.tasks import match, TaskExecutor

cfg = Config()
rule = match("帮我关机", cfg.get("tasks"))
print(rule.rule["action"])         # shutdown

executor = TaskExecutor(
    screenshot_dir=cfg.get("screenshot_dir"),
    apps_list=cfg.get("apps"),
    wol_hosts=cfg.get("wol"),
)
result = executor.execute(rule)
print(result.ok, result.reply)
```

### 接入小爱音箱（后台轮询）

```python
from miiotpcapi.config import Config
from miiotpcapi.xiaomi.bridge import XiaoaiBridge

bridge = XiaoaiBridge(
    Config(),
    on_query=lambda q: print("小爱说:", q),
    on_result=lambda q, reply, ok, detail: print("结果:", reply),
    on_log=print,
    on_state=lambda running: print("桥接运行中" if running else "桥接已停止"),
)
bridge.start()          # 后台线程轮询
# ...
bridge.stop()
```

### 命令行

```powershell
python -m miiotpcapi status                 # 查看系统状态
python -m miiotpcapi shot                    # 截图
python -m miiotpcapi power lock              # 锁屏
python -m miiotpcapi power shutdown 60       # 60 秒后关机
python -m miiotpcapi wol AA:BB:CC:DD:EE:FF   # 发送唤醒包
```

---

## 默认语音指令

配置位于 `~/.miiotpcapi/config.json`，可在软件「小爱控制」页可视化编辑。

| 对小爱说 | 电脑执行 |
|----------|----------|
| 关机 / 关闭电脑 | 延迟 60 秒关机（可说「取消关机」撤销） |
| 重启电脑 / 重启 | 延迟 60 秒重启 |
| 锁屏 / 锁定电脑 | 立即锁定电脑 |
| 电脑睡眠 | 进入睡眠 |
| 截屏 / 截图 | 截图并保存到图片文件夹 |
| 电脑状态 | 语音播报 CPU / 内存 / 运行时长 |
| 打开 XX（如「打开记事本」） | 启动已配置的应用 |
| 关闭 XX（如「关闭浏览器」） | 结束对应进程 |
| 唤醒 XX（如「唤醒客厅台式机」） | 向已配置目标发送 WOL 魔术包 |

> 指令匹配基于正则表达式，支持命名捕获组，例如 `打开(?P<app>.+)` 会把「打开微信」中的
> 「微信」作为 `app` 参数传给 `open_app` 动作。可在「添加 / 编辑指令」中自定义。

---

## 项目结构

```
miiotpcapi/
├── miiotpcapi/                 # 核心库（不依赖 GUI）
│   ├── config.py               # 配置读写（~/.miiotpcapi/config.json）
│   ├── secure.py               # Windows DPAPI 密码加密存储
│   ├── tasks.py                # 语音指令匹配与执行引擎
│   ├── __main__.py             # 命令行入口
│   ├── core/                   # 本机控制能力
│   │   ├── power.py            #   电源控制
│   │   ├── screenshot.py       #   屏幕截取
│   │   ├── monitor.py          #   进程与系统监控
│   │   ├── sysinfo.py          #   系统信息
│   │   ├── apps.py             #   应用管理
│   │   ├── inputctl.py         #   音量 / 媒体键
│   │   ├── wol.py              #   网络唤醒
│   │   └── autostart.py        #   开机自启
│   └── xiaomi/                 # 小米生态接入
│       ├── account.py          #   账号登录（OTP 两步验证）
│       ├── mina.py             #   小爱音箱 MiNA API
│       └── bridge.py           #   语音指令轮询桥接
├── mipcb/                      # PyQt6 图形软件（MiPC Bridge）
│   ├── app.py                  #   应用入口（首启进向导）
│   ├── wizard.py               #   引导式部署向导
│   ├── main_window.py          #   主窗口 + 系统托盘
│   ├── theme.py                #   深色主题
│   ├── bridge_signals.py       #   跨线程信号 / 验证码输入桥
│   ├── workers.py              #   后台线程工具
│   └── pages/                  #   8 个功能页
│       ├── dashboard_page.py   #     仪表盘
│       ├── power_page.py       #     电源控制
│       ├── screenshot_page.py  #     屏幕截取
│       ├── processes_page.py   #     进程管理
│       ├── apps_page.py        #     应用任务
│       ├── wol_page.py         #     网络唤醒
│       ├── xiaomi_page.py      #     小爱控制
│       └── settings_page.py    #     设置
├── run_app.pyw                 # 双击启动（无控制台窗口）
├── requirements.txt
├── pyproject.toml
├── LICENSE
└── THIRD_PARTY_NOTICES.md
```

---

## 安全与隐私

- **密码不出本机**：小米账号密码使用 Windows DPAPI（`CryptProtectData`）加密后写入本地配置，
  只能由当前 Windows 用户账户解密；也可选择不保存密码。
- **令牌本地保存**：登录换取的 `serviceToken` 保存在 `~/.miiotpcapi/mi_token.json`。
- **配置与日志不含敏感信息**，`.gitignore` 已排除令牌与配置文件，不会误提交到仓库。
- **网络请求仅发往小米官方域名**：`account.xiaomi.com`、`api2.mina.mi.com`。
- 本软件为本地工具，不对外暴露任何网络端口。

---

## 常见问题

**Q：PowerShell 里 `Activate.ps1` 报「禁止运行脚本」？**

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**Q：安装 PyQt6 时报错 `Failed building wheel for PyQt6-sip`？**

你的 Python 版本过新，PyQt6 尚无对应预编译包。请改用 3.12：

```powershell
winget install --id Python.Python.3.12 -e
py -3.12 -m venv .venv
```

**Q：登录时提示需要验证码？**

这是小米账号的安全验证。按弹窗提示输入短信或邮箱收到的验证码即可。若频繁失败，
请等待一段时间后重试（小米对登录失败有频率限制）。

**Q：桥接启动了但小爱没反应？**

请确认：①「小爱控制」页已选中小爱音箱；② 对音箱说话后等待一个轮询周期（默认 2 秒）；
③ 说的话能匹配到某条指令，可在「运行日志」中查看实时结果。

---

## 许可证

本项目基于 **MIT 许可证** 发布，详见 [LICENSE](LICENSE)。

在实现小米账号登录与小爱音箱通信协议时，本项目参考了以下 **MIT 协议** 的开源项目，
并依其要求保留版权与许可声明：

- [Yonsm/MiService](https://github.com/Yonsm/MiService) —— Copyright (c) 2021-2026 Yonsm
- [hanxi/xiaomusic](https://github.com/hanxi/xiaomusic) —— Copyright (c) 2023 涵曦

完整声明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

> 注意：GUI 依赖 **PyQt6** 采用 **GPL-3.0** 授权。本项目自身代码为 MIT，但若你计划
> **闭源分发** 含 GUI 的完整软件，需将 GUI 依赖替换为 LGPL 授权的 PySide6，或遵循 PyQt6 的 GPL 条款。

## 免责声明

本软件涉及关机、重启、结束进程等高风险操作，请自行确认指令配置后再使用。
因使用本软件导致的任何数据丢失或设备问题，作者不承担责任。

「小米」「小爱同学」「米家」为小米科技有限责任公司商标，本项目为第三方工具，与小米公司无关联。

## 致谢

- [Yonsm/MiService](https://github.com/Yonsm/MiService) —— 小米账号登录与小爱音箱 API 协议参考
- [hanxi/xiaomusic](https://github.com/hanxi/xiaomusic) —— MiNA 音箱控制实现参考
- [PyQt6](https://pypi.org/project/PyQt6/) / [psutil](https://github.com/giampaolo/psutil) / [mss](https://github.com/BoboTiG/python-mss) / [requests](https://github.com/psf/requests)
