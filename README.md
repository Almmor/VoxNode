# VoxNode · 声枢

> 让智能家居替你操作电脑 —— 说一句「关机」「截屏」「打开浏览器」，电脑就照做。

`miiotpcapi` 是一个把 **Windows 电脑接入小米智能家居生态** 的 Python 库，附带一款基于 **PyQt6**
的图形控制软件 **VoxNode（声枢）**，双向打通电脑与米家：

| 方向 | 能力 |
|------|------|
| 电脑 → 米家 | 设备列表、开关、MIoT 属性读写、动作调用 |
| 米家 → 电脑 | 把米家设备属性当作「指令通道」，轮询到变化就执行电脑动作 |
| 音箱 → 电脑 | 轮询音箱对话，把语音指令映射为电脑操作并语音回执 |
| 本机控制 | 电源、截屏、进程、系统监控、Wake-on-LAN |

> 本项目为第三方开源工具，与小米公司无任何从属或合作关系，也不使用任何小米产品名称。
> 「小米」「小爱同学」「米家」等为小米科技有限责任公司的商标。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://pypi.org/project/PyQt6/)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6.svg)](#)

---

## 下载与安装

### 普通用户（推荐）

从 [Releases](https://github.com/Almmor/miiotpcapi/releases) 下载 `VoxNode-Setup-x.y.z.exe` 并双击安装：

- 按当前用户安装，**无需管理员权限**
- 安装向导为简体中文，可自选「桌面快捷方式」与「开机自动启动」
- 安装完成后勾选「立即启动」，**首次运行会自动进入引导式部署向导**
- 卸载入口在「设置 → 应用」或开始菜单中，卸载会保留你的账号配置

若不想安装，也可下载免安装版压缩包，解压后直接运行 `VoxNode.exe`。

### 从源码运行（开发者）

见下方「快速开始」。

---

## 功能特性

**账号登录**

- **扫码登录（推荐）**：米家 App 扫一扫即可，不在本机保存密码
- 账号密码登录，支持短信 / 邮箱 OTP 两步验证
- 密码使用 Windows DPAPI 加密后仅存本机，也可选择不保存
- 一次登录同时获得音箱与米家设备所需的全部令牌

**电脑 → 米家设备**

- 列出账号下全部米家设备（名称 / 房间 / 型号 / 在线状态）
- 一键开 / 关设备，MIoT 属性读写（`siid` / `piid`），动作调用（`siid` / `aiid`）
- 语音控制：对音箱说「米家打开客厅灯」「米家关闭加湿器」

**米家 → 电脑（米家遥控）**

- 绑定米家设备的某个属性作为「指令通道」
- 配置「属性取值 → 电脑动作」映射表，本机轮询到变化即执行
- 在米家 App 里做一个手动场景改动该属性，就实现了 **用米家 App 控制这台电脑**
- 动作涵盖关机 / 重启 / 锁屏 / 睡眠 / 截屏 / 语音播报 / 向其他电脑发送 Wake-on-LAN

**音箱语音控制**

- 自动发现账号下的音箱，轮询其对话记录，把语音指令映射为电脑操作
- 执行结果可通过音箱 TTS 语音播报
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

- **首次运行引导式部署向导**：环境自检 → 扫码/密码登录 → 选择音箱 → 指令预览 → 完成设置
- 系统托盘常驻，关闭窗口不退出，后台服务持续运行
- 开机自启（当前用户注册表 `Run` 键，无需管理员权限）
- 深色主题，科技橙配色
- 从旧版本升级时自动迁移配置目录与自启动项

---

## 首次部署（引导式）

安装依赖后启动程序，**首次运行会自动进入部署向导**：

1. **环境自检** —— 检查 Python 版本、PyQt6 / psutil / mss 是否就绪、操作系统是否为 Windows
2. **登录小米账号** —— 推荐用米家 App 扫码登录；也可切换到账号密码（支持短信 / 邮箱验证码）
3. **选择音箱** —— 自动拉取账号下的音箱设备列表
4. **查看语音指令** —— 预览默认支持的语音指令
5. **完成设置** —— 勾选开机自启 / 最小化启动 / 立即启动

向导可随时通过 `python -m voxnode --setup` 重新运行。配置保存在 `~/.voxnode/config.json`。

---

## 用米家控制这台电脑

小米**没有**面向个人的「虚拟设备」方案，无法让电脑直接出现在米家 App 的设备列表里。
本项目采用社区通行且实际可行的做法 —— **把米家设备的一个属性当作指令通道**：

1. 在「米家遥控」页选择一台可控的米家设备（智能插座、灯、开关等）
2. 指定它的某个属性（如插座的开关 `siid=2, piid=1`，或灯的亮度 `siid=2, piid=2`）
3. 配置「属性取值 → 电脑动作」映射，例如 `1 → 关机`、`0 → 锁屏`
4. 启动监听后，程序会按设定间隔轮询该属性，取值变化且命中映射时在本机执行动作

之后在米家 App 里创建一个手动场景（例如「睡觉」场景把插座设为开），
点一下场景就等于给这台电脑下了一条指令。

> **关于远程开机**：电脑关机后本程序无法运行，因此「从关机状态唤醒」需要硬件配合 ——
> 用 **米家智能插座** 控制主机供电并在主板 BIOS 开启「断电恢复后自动开机（AC Power Loss → Power On）」，
> 或使用第三方 **米家开机卡**。
> 电脑已开机（含睡眠唤醒后）时的一切操作，都由本软件负责；软件内的 WOL 模块用于唤醒 **其他** 局域网设备。

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
python -m voxnode

# 强制重新运行部署向导 / 最小化启动
python -m voxnode --setup
python -m voxnode --minimized
```

也可以安装为命令：

```powershell
pip install -e .
voxnode
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

### 扫码登录小米账号

```python
from miiotpcapi.xiaomi import qrlogin as qr
from miiotpcapi.xiaomi.account import SID_MIIO, SID_MINA, MiAccount

with open("qr.png", "wb") as f:
    session = qr.XiaomiQrLogin(sid="mijia")
    session.start()
    f.write(session.fetch_qr_image())     # 展示给用户扫码

while True:                                # 轮询等待扫码确认
    state = session.poll()
    if state == qr.CONFIRMED:
        break
    if state == qr.EXPIRED:
        session.start()                    # 过期则重新申请

# 用一次扫码拿到的 passToken 换取各业务 sid 的令牌
account = MiAccount(session.user_id, "", token_path="~/.voxnode/mi_token.json")
account.login_with_pass_token(SID_MINA, session.pass_token, session.user_id)
account.login_with_pass_token(SID_MIIO, session.pass_token, session.user_id)
```

### 控制米家设备

```python
from miiotpcapi.xiaomi.account import SID_MIIO, MiAccount
from miiotpcapi.xiaomi.miot import MiIO

account = MiAccount("账号", "密码", token_path="~/.voxnode/mi_token.json")
account.login(SID_MIIO)
miio = MiIO(account)

for d in miio.device_list_with_room():
    print(d["name"], d["room"], "在线" if d["online"] else "离线")

did = miio.device_list()[0]["did"]
miio.set_power(did, True)                 # 开机（自动适配 MIoT / 老版 RPC）
print(miio.get_power(did))                # 读取开关状态
print(miio.get_prop(did, 2, 2))           # 读取 siid=2 piid=2（如亮度）
miio.set_prop(did, 2, 2, 60)              # 写入属性
miio.action(did, 2, 1, [])                # 调用动作
```

### 接入小爱音箱（后台轮询）

```python
from miiotpcapi.config import Config
from miiotpcapi.xiaomi.bridge import XiaoaiBridge

bridge = XiaoaiBridge(
    Config(),
    on_query=lambda q: print("音箱说:", q),
    on_result=lambda q, reply, ok, detail: print("结果:", reply),
    on_log=print,
    on_state=lambda running: print("桥接运行中" if running else "桥接已停止"),
)
bridge.start()          # 后台线程轮询
# ...
bridge.stop()
```

### 米家指令通道（用米家控制本机）

```python
from miiotpcapi.config import Config
from miiotpcapi.tasks import TaskExecutor
from miiotpcapi.xiaomi.channel import MijiaChannel

channel = MijiaChannel(
    Config(),
    executor_factory=TaskExecutor,
    on_log=print,
    on_state=lambda running: print("监听中" if running else "已停止"),
    on_trigger=lambda value, reply, ok: print(f"属性值 {value} → {reply}"),
)
channel.start()
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

配置位于 `~/.voxnode/config.json`，可在软件「语音助手」页可视化编辑。

| 对音箱说 | 电脑执行 |
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
| 米家打开 XX（如「米家打开客厅灯」） | 打开对应的米家设备 |
| 米家关闭 XX（如「米家关闭加湿器」） | 关闭对应的米家设备 |

> 指令匹配基于正则表达式，支持命名捕获组，例如 `打开(?P<app>.+)` 会把「打开微信」中的
> 「微信」作为 `app` 参数传给 `open_app` 动作。可在「添加 / 编辑指令」中自定义。

---

## 项目结构

```
miiotpcapi/
├── miiotpcapi/                 # 核心库（不依赖 GUI）
│   ├── config.py               # 配置读写（~/.voxnode/config.json）
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
│       ├── account.py          #   账号登录 / 令牌管理 / 签名请求
│       ├── qrlogin.py          #   扫码登录（二维码 + 长轮询）
│       ├── mina.py             #   音箱 MiNA API（设备列表 / TTS / 对话）
│       ├── miot.py             #   米家设备控制（MIoT / MiIO 云 API）
│       ├── bridge.py           #   语音指令轮询桥接
│       └── channel.py          #   米家指令通道（用米家控制本机）
├── voxnode/                    # PyQt6 图形软件（VoxNode / 声枢）
│   ├── app.py                  #   应用入口（首启进向导）
│   ├── wizard.py               #   引导式部署向导
│   ├── login.py                #   登录对话框（扫码 / 账号密码）
│   ├── main_window.py          #   主窗口 + 系统托盘
│   ├── theme.py                #   深色主题
│   ├── bridge_signals.py       #   跨线程信号 / 验证码输入桥
│   ├── workers.py              #   后台线程工具
│   └── pages/                  #   10 个功能页
│       ├── dashboard_page.py   #     仪表盘
│       ├── power_page.py       #     电源控制
│       ├── screenshot_page.py  #     屏幕截取
│       ├── processes_page.py   #     进程管理
│       ├── apps_page.py        #     应用任务
│       ├── wol_page.py         #     网络唤醒
│       ├── mijia_page.py       #     米家设备
│       ├── mijia_channel_page.py  #  米家遥控
│       ├── assistant_page.py   #     语音助手
│       └── settings_page.py    #     设置
├── run_app.pyw                 # 双击启动（无控制台窗口）
├── packaging/                  # 打包与安装程序
│   ├── build.ps1               #   一键构建（图标 → exe → 自检 → 安装包）
│   ├── voxnode.spec            #   PyInstaller 配置
│   ├── installer.iss           #   Inno Setup 安装脚本
│   ├── make_icon.py            #   生成多尺寸 app.ico
│   ├── version_info.txt        #   exe 版本资源
│   └── languages/              #   安装器简体中文语言包
├── tests/                      # pytest 单元测试
├── requirements.txt
├── pyproject.toml
├── BUILD.md                    # 打包成 exe / 安装程序的完整说明
├── LICENSE
└── THIRD_PARTY_NOTICES.md
```

---

## 打包与分发

要把本项目打包成独立 exe 与 Windows 安装程序：

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

产物：

- `dist\VoxNode\` —— 免安装版目录（直接运行 `VoxNode.exe`）
- `dist\VoxNode-Setup-<版本>.exe` —— 安装程序

构建流程、安装程序行为、体积优化与常见问题详见 **[BUILD.md](BUILD.md)**。

---

## 安全与隐私

- **推荐扫码登录**：不经过本机输入密码，仅由米家 App 授权，本地只保存令牌。
- **密码不出本机**：若使用账号密码登录，密码经 Windows DPAPI（`CryptProtectData`）
  加密后写入本地配置，只能由当前 Windows 用户账户解密；也可选择不保存密码。
- **令牌本地保存**：登录换取的 `serviceToken` 保存在 `~/.voxnode/mi_token.json`。
- **配置与日志不含敏感信息**，`.gitignore` 已排除令牌与配置文件，不会误提交到仓库。
- **网络请求仅发往小米官方域名**：`account.xiaomi.com`、`api2.mina.mi.com`、`api.io.mi.com`。
- 本软件为本地工具，不对外暴露任何网络端口。

> 说明：小米账号登录、音箱与米家云接口均为未公开协议（第三方逆向实现），
> 可能随小米官方调整而变化，也存在账号风控的可能，请自行评估后使用。

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

请确认：①「语音助手」页已选中小爱音箱；② 对音箱说话后等待一个轮询周期（默认 2 秒）；
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
