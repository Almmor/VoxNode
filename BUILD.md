# 构建与打包指南

本文档说明如何把 `miiotpcapi` / VoxNode 打包成 **独立 exe** 与 **Windows 安装程序**。

---

## 1. 前置条件

| 组件 | 要求 | 安装方式 |
|------|------|----------|
| Python | 3.10 ~ 3.13（**推荐 3.12**） | `winget install --id Python.Python.3.12 -e` |
| 运行时依赖 | PyQt6 / psutil / mss / requests | `pip install -r requirements.txt` |
| PyInstaller | 6.x | `pip install pyinstaller` |
| Inno Setup | 6.0+（仅生成安装程序时需要） | `winget install --id JRSoftware.InnoSetup -e` |

> **Python 版本提示**：不要使用过新的 Python（如 3.15）。PyQt6 的 `PyQt6-sip` 尚无对应预编译包，
> 会尝试从源码编译并失败，报错 `Failed building wheel for PyQt6-sip`。

---

## 2. 一键构建（推荐）

```powershell
# 在仓库根目录执行
powershell -ExecutionPolicy Bypass -File packaging\build.ps1
```

脚本依次完成：

1. 探测 Python 解释器（优先 `.venv\Scripts\python.exe`，其次 `py -3.12`）
2. 校验运行时依赖与 PyInstaller（缺失时自动安装）
3. 生成应用图标 `packaging/app.ico`（7 种尺寸，含 256×256）
4. PyInstaller 打包为 `dist\VoxNode\`
5. 运行打包产物的**自检**（离屏构建全部界面并校验核心功能）
6. 调用 Inno Setup 生成 `dist\VoxNode-Setup-<版本>.exe`

可选参数：

```powershell
# 指定解释器
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -Python C:\Python312\python.exe

# 只打包 exe，不生成安装程序
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipInstaller

# 跳过 exe 自检（不推荐）
powershell -ExecutionPolicy Bypass -File packaging\build.ps1 -SkipTests
```

---

## 3. 手动分步构建

```powershell
# 1) 生成图标
python packaging\make_icon.py

# 2) 打包 exe（onedir 模式）
pyinstaller packaging\voxnode.spec --noconfirm --distpath dist

# 3) 验证产物（--selftest 会在 %TEMP%\voxnode_selftest.txt 写入报告）
dist\VoxNode\VoxNode.exe --selftest

# 4) 生成安装程序
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" packaging\installer.iss
```

---

## 4. 产物说明

| 产物 | 路径 | 说明 |
|------|------|------|
| 免安装版 | `dist\VoxNode\` | 整个目录可拷贝到任意位置运行，入口 `VoxNode.exe` |
| 安装程序 | `dist\VoxNode-Setup-<版本>.exe` | 单文件安装包 |

关于打包形态：采用 **onedir**（目录模式）而非 onefile。onedir 启动更快、不产生临时解压开销，
且对 PyQt6 的插件加载更稳定，是桌面应用的推荐做法。

---

## 5. 安装程序行为

`packaging/installer.iss` 定义的安装行为：

- **按用户安装**：默认装到 `%LOCALAPPDATA%\Programs\VoxNode`，`PrivilegesRequired=lowest`，**不需要管理员权限**
- **界面语言**：简体中文（`packaging\languages\ChineseSimplified.isl`）、英文双语言可选
- **快捷方式**：
  - 开始菜单：主程序、首次部署向导（`--setup`）、卸载入口
  - 桌面：可选（默认勾选）
- **开机自启**：可选（默认不勾选）。勾选后写入
  `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\VoxNode`，
  与软件「设置」页的「开机自动启动」是**同一个注册表项**，两处设置保持一致；
  同时会清理旧品牌名（MiPC Bridge）遗留的自启动项
- **安装前先结束运行中的实例**（`taskkill`），避免文件占用导致升级失败
- **卸载**：删除安装目录、快捷方式、自启动项与卸载注册表项；
  **保留用户配置** `%USERPROFILE%\.voxnode`（含登录令牌、指令规则），避免误删

静默安装 / 卸载（便于批量部署）：

```powershell
# 静默安装（不建桌面图标、不开机自启）
.\VoxNode-Setup-0.4.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOICONS /MERGETASKS=!desktopicon,!autostart

# 静默卸载
& "$env:LOCALAPPDATA\Programs\VoxNode\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
```

> 注意 `/MERGETASKS` 的值前后不要加引号，否则某些版本的 Setup 会初始化失败（退出码 1）。

---

## 6. 从旧版本升级（改名迁移）

早期版本的软件名与包名不同（`MiPC Bridge` / `mipcb`）。升级到 VoxNode 后会自动兼容：

| 项目 | 旧 | 新 | 迁移方式 |
|------|----|----|----------|
| 配置目录 | `%USERPROFILE%\.miiotpcapi` | `%USERPROFILE%\.voxnode` | 首次启动自动重命名 |
| 自启动项 | `Run\MiPCBridge` | `Run\VoxNode` | 启用自启时自动清理旧项；安装程序也会清理 |
| 密码密文 | entropy `MiPCBridge-v1` | entropy `VoxNode-v1` | 解密时自动回退旧 entropy，历史密文仍可读 |
| exe / 安装包 | `MiPCBridge.exe` | `VoxNode.exe` | 直接安装新版本即可 |

`AppId` 保持不变，因此新版本安装程序会**覆盖升级**旧版本，不会产生两份。

---

## 7. 体积优化

默认已排除大量未使用的 Qt 模块（详见 `packaging/voxnode.spec` 的 `excludes`），
如需进一步瘦身：

- 删除 `dist\VoxNode\_internal\PyQt6\Qt6\translations\` 下用不到的 `qt_*.qm` 语言包
  （保留 `qt_zh_CN.qm` 与 `qt_en.qm` 即可）
- 参考体积：exe 目录约 **98 MB**，安装包约 **27 MB**（lzma2/max 压缩）

---

## 8. 常见问题

**Q：PyInstaller 打包后运行时提示缺少 Qt 平台插件？**

确认 `dist\VoxNode\_internal\PyQt6\Qt6\plugins\platforms\qwindows.dll` 存在。
`packaging\voxnode.spec` 已依赖 PyInstaller 的 PyQt6 hook 自动收集插件，一般无需手动处理。

**Q：`build.ps1` 报「Unexpected token」或中文乱码？**

`build.ps1` 与 `installer.iss` 必须保存为 **UTF-8 with BOM**。Windows PowerShell 5
在读取无 BOM 的 UTF-8 文件时会按 ANSI（GBK）解码，导致中文变成乱码并破坏语法解析。

**Q：杀毒软件误报 exe？**

PyInstaller 单文件/目录产物被启发式误报较常见，属行业普遍现象。可通过代码签名
（`signtool`）降低误报，或在杀软中添加信任。本项目未做代码签名。

**Q：自检报告在哪里？**

`%TEMP%\voxnode_selftest.txt`，内容包含 PyQt6 加载、系统信息、指令匹配、界面构建页数等，
末行 `RESULT=PASS` 表示通过。

---

## 9. 构建 Android 手机 App

手机 App 是一份标准的 Gradle 工程，位于 `android/`。

### 前置条件

| 组件 | 要求 | 说明 |
|------|------|------|
| JDK | 17 或更高（需含 `javac`） | 注意：只有 JRE 不够 |
| Android SDK | 含 `platforms/android-34` 与 `build-tools` | 通过 Android Studio 安装，或设置 `ANDROID_HOME` |
| Gradle | 无需单独安装 | 优先用本机 `~/.gradle/wrapper/dists` 里已缓存的发行版；否则用 wrapper 下载 8.5 |

### 一键构建

```powershell
# 在仓库根目录执行
powershell -ExecutionPolicy Bypass -File android\build-apk.ps1

# 可选参数
-Python <path>    # 顺带重新生成各密度启动图标
-Debug            # 构建 debug 版
-Offline          # 强制离线（只用本地 Gradle 缓存）
```

脚本会依次：探测 JDK 与 Android SDK → 写 `local.properties` → 编译 `assembleRelease`
→ 打印包名 / 版本 / 权限 / 签名信息。产物在
`android/app/build/outputs/apk/release/app-release.apk`。

### 手动构建

```powershell
$env:JAVA_HOME = "<你的 JDK 路径>"
cd android
.\gradlew.bat :app:assembleRelease
```

### 网络受限环境

本工程的仓库已优先配置**阿里云镜像**（`maven.aliyun.com` 的 google / public / gradle-plugin），
在 Maven Central、Google Maven 或 `services.gradle.org` 不可达时依然可以构建：

- 依赖解析：走阿里云镜像
- Gradle 发行版：优先使用本地已缓存的 `~/.gradle/wrapper/dists`；
  若需下载，可把 `android/gradle/wrapper/gradle-wrapper.properties` 的 `distributionUrl`
  换成 `https://mirrors.cloud.tencent.com/gradle/gradle-8.5-bin.zip`

### 签名说明

`android/keystore/voxnode.jks` 是**随仓库公开的测试用签名**（口令 `voxnode`），
目的是让任何人都能复现签名一致的 APK、便于覆盖升级。**请勿用于正式上架**；
若要正式发布，请自行生成密钥并替换 `android/app/build.gradle.kts` 中的 `signingConfigs`。

### App 的接口契约

App 只调用电脑端遥控台的四个接口：`/api/status`、`/api/config`、`/api/screenshot`、`/api/action`。
两端的动作名与参数由 `tests/test_core.py` 中的
`ANDROID_APP_CALLS` 契约测试守护，改动任意一端都会被测到。

---

## 10. 相关文件

```
packaging/
├── build.ps1                    # 一键构建脚本
├── voxnode.spec                 # PyInstaller 配置（隐藏导入、排除项、图标、版本信息）
├── installer.iss                # Inno Setup 安装脚本
├── make_icon.py                 # 生成多尺寸 app.ico
├── version_info.txt             # exe 版本资源（产品名、版权等）
├── app.ico                      # 应用图标（由 make_icon.py 生成，已提交便于直接构建）
└── languages/
    └── ChineseSimplified.isl    # Inno Setup 简体中文语言包（取自 jrsoftware/issrc）
```

Android 手机 App：

```
android/
├── build-apk.ps1                # 一键构建 APK（自动探测 JDK / SDK / Gradle）
├── settings.gradle.kts          # 仓库配置（优先阿里云镜像）
├── build.gradle.kts             # AGP 8.2.2 + Kotlin 1.9.20
├── gradle/wrapper/              # Gradle Wrapper（8.5）
├── keystore/voxnode.jks         # 公开的测试签名（口令 voxnode）
├── tools/make_android_icons.py  # 生成各密度启动图标
└── app/
    ├── build.gradle.kts         # compileSdk 34 / minSdk 24 / 签名配置
    └── src/main/
        ├── AndroidManifest.xml
        ├── java/com/voxnode/remote/{MainActivity,Api,Prefs}.kt
        └── res/                 # 布局、深色主题、图标
```
