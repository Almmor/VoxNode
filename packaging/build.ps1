<#
.SYNOPSIS
    MiPC Bridge 一键构建脚本：生成图标 -> PyInstaller 打包 -> exe 自检 -> 生成安装程序。

.DESCRIPTION
    在仓库根目录执行：
        powershell -ExecutionPolicy Bypass -File packaging\build.ps1

    参数：
        -Python <path>    指定 Python 解释器（默认自动探测 .venv / py -3.12）
        -SkipInstaller    只打包 exe，不生成安装程序
        -SkipTests        跳过打包后的 exe 自检

.NOTES
    依赖：Python 3.10+、pyinstaller、Inno Setup 6（仅生成安装程序时需要）
    注意：本文件必须保存为 UTF-8 with BOM，否则 Windows PowerShell 5 会把中文读成乱码。
#>
[CmdletBinding()]
param(
    [string]$Python = "",
    [switch]$SkipInstaller,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$PackagingDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $PackagingDir

function Write-Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Write-Ok([string]$Text) {
    Write-Host "    $Text" -ForegroundColor Green
}

function Resolve-Python {
    param([string]$Explicit)
    if ($Explicit -and (Test-Path $Explicit)) { return (Resolve-Path $Explicit).Path }
    $venv = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $venv) { return $venv }
    foreach ($cand in @("3.12", "3.11", "3.10")) {
        $out = & py "-$cand" -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return $out.Trim() }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "未找到 Python 解释器，请用 -Python 参数指定路径。"
}

function Find-ISCC {
    $candidates = @(
        (Join-Path ${env:LOCALAPPDATA} "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles} "Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:LOCALAPPDATA} "Programs\Inno Setup 7\ISCC.exe")
    )
    foreach ($c in $candidates) {
        if ($c -and (Test-Path $c)) { return $c }
    }
    return $null
}

# ---------------------------------------------------------------- 环境准备
Write-Step "检测 Python 环境"
$Py = Resolve-Python -Explicit $Python
Write-Ok "Python: $Py"
$ver = & $Py -c "import sys; print(sys.version.split()[0])"
Write-Ok "版本: $ver"

& $Py -c "import PyQt6, psutil, mss, requests" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "缺少运行时依赖，请先执行： `"$Py`" -m pip install -r requirements.txt"
}
Write-Ok "运行时依赖: PyQt6 / psutil / mss / requests 就绪"

& $Py -m PyInstaller --version 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "    正在安装 PyInstaller ..." -ForegroundColor Yellow
    & $Py -m pip install pyinstaller | Out-Null
}
$pyiVer = & $Py -m PyInstaller --version
Write-Ok "PyInstaller: $pyiVer"

# ---------------------------------------------------------------- 生成图标
Write-Step "生成应用图标"
& $Py (Join-Path $PackagingDir "make_icon.py")
if ($LASTEXITCODE -ne 0) { throw "图标生成失败" }

# ---------------------------------------------------------------- 打包 exe
Write-Step "PyInstaller 打包（onedir 模式）"
$distApp = Join-Path $Root "dist\MiPCBridge"
if (Test-Path $distApp) { Remove-Item $distApp -Recurse -Force }

Push-Location $Root
try {
    & $Py -m PyInstaller (Join-Path $PackagingDir "mipcb.spec") --noconfirm --distpath dist
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败" }
} finally {
    Pop-Location
}

$exePath = Join-Path $distApp "MiPCBridge.exe"
if (-not (Test-Path $exePath)) { throw "未找到产物 $exePath" }
$sizeMb = [math]::Round(((Get-ChildItem $distApp -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Ok "产物: $exePath （总计 $sizeMb MB）"

# ---------------------------------------------------------------- 自检
if (-not $SkipTests) {
    Write-Step "运行打包产物自检"
    $report = Join-Path $env:TEMP "mipcb_selftest.txt"
    if (Test-Path $report) { Remove-Item $report -Force }
    $proc = Start-Process -FilePath $exePath -ArgumentList "--selftest" -PassThru -Wait
    if (-not (Test-Path $report)) { throw "自检未生成报告，退出码 $($proc.ExitCode)" }
    $text = Get-Content $report -Raw -Encoding UTF8
    if ($text -notmatch "RESULT=PASS") {
        Write-Host $text -ForegroundColor Red
        throw "自检失败"
    }
    Write-Ok "自检通过（主界面 + 部署向导 + 核心功能均可用）"
}

# ---------------------------------------------------------------- 安装程序
if (-not $SkipInstaller) {
    Write-Step "生成安装程序（Inno Setup）"
    $iscc = Find-ISCC
    if (-not $iscc) {
        Write-Host "    未检测到 Inno Setup 6，已跳过安装程序。" -ForegroundColor Yellow
        Write-Host "    安装命令： winget install --id JRSoftware.InnoSetup -e" -ForegroundColor Yellow
    } else {
        Write-Ok "ISCC: $iscc"
        & $iscc (Join-Path $PackagingDir "installer.iss")
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup 编译失败" }
        $setup = Get-ChildItem (Join-Path $Root "dist") -Filter "MiPCBridge-Setup-*.exe" |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($setup) {
            $setupMb = [math]::Round($setup.Length / 1MB, 1)
            Write-Ok "安装程序: $($setup.FullName) （$setupMb MB）"
        }
    }
}

Write-Host ""
Write-Host "构建完成。" -ForegroundColor Green
