# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：VoxNode 声枢。

用法（在仓库根目录执行）：
    pyinstaller packaging/voxnode.spec --noconfirm

产物：dist/VoxNode/VoxNode.exe（onedir 模式，启动更快、兼容性更好）
"""
from pathlib import Path

# SPECPATH 由 PyInstaller 注入，指向本文件所在目录（packaging/）
PKG_DIR = Path(SPECPATH).resolve()
ROOT = PKG_DIR.parent

APP_NAME = "VoxNode"

# mss 按平台动态导入后端，需显式声明
hiddenimports = [
    "mss.windows",
    "winreg",
]

# 裁剪用不到的重型依赖，显著减小体积
excludes = [
    # 未使用的 Qt 模块
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineQuick",
    "PyQt6.QtQuick", "PyQt6.QtQml", "PyQt6.QtQuickWidgets", "PyQt6.QtQuick3D",
    "PyQt6.Qt3DCore", "PyQt6.Qt3DRender", "PyQt6.Qt3DInput", "PyQt6.Qt3DAnimation",
    "PyQt6.Qt3DExtras", "PyQt6.Qt3DLogic",
    "PyQt6.QtCharts", "PyQt6.QtDataVisualization", "PyQt6.QtGraphs",
    "PyQt6.QtMultimedia", "PyQt6.QtMultimediaWidgets", "PyQt6.QtSpatialAudio",
    "PyQt6.QtPdf", "PyQt6.QtPdfWidgets",
    "PyQt6.QtDesigner", "PyQt6.QtHelp", "PyQt6.QtTest", "PyQt6.QtUiTools",
    "PyQt6.QtBluetooth", "PyQt6.QtNfc", "PyQt6.QtPositioning", "PyQt6.QtSerialPort",
    "PyQt6.QtWebSockets", "PyQt6.QtWebChannel", "PyQt6.QtRemoteObjects",
    "PyQt6.QtSql", "PyQt6.QtSensors", "PyQt6.QtTextToSpeech", "PyQt6.QtOpenGL",
    "PyQt6.QtOpenGLWidgets", "PyQt6.QtSvg", "PyQt6.QtSvgWidgets",
    "PyQt6.QtPrintSupport", "PyQt6.QtNetworkAuth", "PyQt6.QtXml", "PyQt6.QtStateMachine",
    # 其它无关的第三方 / 标准库
    "tkinter", "matplotlib", "numpy", "pandas", "PIL", "scipy", "IPython",
    "pytest", "setuptools", "pip", "wheel", "distutils",
]

a = Analysis(
    [str(ROOT / "run_app.pyw")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                       # 窗口程序，不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PKG_DIR / "app.ico"),
    version=str(PKG_DIR / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
