<#
.SYNOPSIS
    构建 VoxNode 手机遥控 App（Android APK）。

.DESCRIPTION
    在仓库根目录执行：
        powershell -ExecutionPolicy Bypass -File android\build-apk.ps1

    参数：
        -Python <path>   指定 Python（用于重新生成图标；省略则跳过）
        -DebugBuild      构建 debug 版（默认 release）
        -Offline         强制离线构建（只使用本地 Gradle 缓存）

.NOTES
    依赖：JDK 17+、Android SDK（compileSdk 34 + build-tools）。
    若本机已有 Gradle 发行版缓存，会直接使用，避免从 services.gradle.org 下载。
#>
[CmdletBinding()]
param(
    [string]$Python = "",
    [switch]$DebugBuild,
    [switch]$Offline
)

$ErrorActionPreference = "Stop"
$AndroidDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $AndroidDir

function Write-Step([string]$Text) { Write-Host ""; Write-Host "==> $Text" -ForegroundColor Cyan }
function Write-Ok([string]$Text) { Write-Host "    $Text" -ForegroundColor Green }

# ---------------------------------------------------------------- 找 JDK
function Find-Jdk {
    if ($env:JAVA_HOME -and (Test-Path (Join-Path $env:JAVA_HOME "bin\javac.exe"))) { return $env:JAVA_HOME }
    $roots = @(
        "D:\Program Files\Microsoft", "C:\Program Files\Microsoft",
        "C:\Program Files\Eclipse Adoptium", "C:\Program Files\Java",
        "C:\Program Files\Zulu", "C:\Program Files\Amazon Corretto",
        "C:\Program Files\Android\Android Studio\jbr"
    )
    foreach ($r in $roots) {
        if (-not (Test-Path $r)) { continue }
        $hit = Get-ChildItem $r -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path (Join-Path $_.FullName "bin\javac.exe") } |
            Sort-Object Name -Descending | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    $gradleJdks = Join-Path $env:USERPROFILE ".gradle\jdks"
    if (Test-Path $gradleJdks) {
        $hit = Get-ChildItem $gradleJdks -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path (Join-Path $_.FullName "bin\javac.exe") } | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    $javac = Get-Command javac -ErrorAction SilentlyContinue
    if ($javac) { return (Split-Path (Split-Path $javac.Source -Parent) -Parent) }
    return $null
}

# ---------------------------------------------------------------- 找 SDK
function Find-Sdk {
    foreach ($c in @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT,
                     (Join-Path $env:LOCALAPPDATA "Android\Sdk"))) {
        if ($c -and (Test-Path (Join-Path $c "platforms"))) { return $c }
    }
    return $null
}

# ---------------------------------------------------------------- 找 Gradle
function Get-Wanted-GradleVersion {
    $props = Join-Path $AndroidDir "gradle\wrapper\gradle-wrapper.properties"
    if (Test-Path $props) {
        $m = Select-String -Path $props -Pattern 'gradle-([0-9][0-9.]*)-(bin|all)\.zip' |
            Select-Object -First 1
        if ($m) { return $m.Matches[0].Groups[1].Value }
    }
    return ""
}

function Find-Gradle {
    # 缓存结构：dists/<发行版名>/<hash>/gradle-<版本>/bin/gradle.bat
    # 只在固定深度匹配通配路径，避免对整个 ~/.gradle 做深层递归（很慢）
    $dists = Join-Path $env:USERPROFILE ".gradle\wrapper\dists"
    $wanted = Get-Wanted-GradleVersion
    if (Test-Path $dists) {
        $pattern = Join-Path $dists "*\*\gradle-*\bin\gradle.bat"
        $hits = @(Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty FullName)

        # 1) 优先用 wrapper 声明的版本，保证与 AGP 兼容
        if ($wanted) {
            $exact = $hits | Where-Object { $_ -match "\\gradle-$([regex]::Escape($wanted))\\" } |
                Select-Object -First 1
            if ($exact) { return $exact }
        }
        # 2) 退而求其次：只接受 8.x（AGP 8.2 不支持 Gradle 9）
        $eightX = $hits | Where-Object { $_ -match "\\gradle-8\.[0-9.]+\\bin\\gradle\.bat$" } |
            Sort-Object -Descending
        if ($eightX) { return ($eightX | Select-Object -First 1) }
    }
    $cmd = Get-Command gradle -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

Write-Step "检测构建环境"

$jdk = Find-Jdk
if (-not $jdk) { throw "未找到 JDK（需要 javac）。请安装 JDK 17 或更高版本。" }
$env:JAVA_HOME = $jdk
Write-Ok "JAVA_HOME = $jdk"

$sdk = Find-Sdk
if (-not $sdk) { throw "未找到 Android SDK。请设置 ANDROID_HOME 或安装 Android SDK。" }
Write-Ok "Android SDK = $sdk"

$localProps = Join-Path $AndroidDir "local.properties"
$escaped = $sdk -replace '\\', '\\' -replace ':', '\:'
"sdk.dir=$escaped" | Set-Content -Path $localProps -Encoding ASCII
Write-Ok "已写入 local.properties"

# ---------------------------------------------------------------- 生成图标
if ($Python) {
    Write-Step "生成 Android 图标"
    & $Python (Join-Path $AndroidDir "tools\make_android_icons.py")
    if ($LASTEXITCODE -ne 0) { throw "图标生成失败" }
}

# ---------------------------------------------------------------- 构建
$variant = if ($DebugBuild) { "Debug" } else { "Release" }
$task = ":app:assemble$variant"
Write-Step "编译 $variant APK"

$gradleArgs = @("-p", $AndroidDir, $task)
if ($Offline) { $gradleArgs += "--offline" }

$localGradle = Find-Gradle
Push-Location $AndroidDir
try {
    if ($localGradle) {
        Write-Ok "使用本地 Gradle：$localGradle"
        & $localGradle @gradleArgs
    } else {
        Write-Ok "使用 Gradle Wrapper（首次会下载 Gradle 8.5）"
        $wrapperArgs = @($task)
        if ($Offline) { $wrapperArgs += "--offline" }
        & (Join-Path $AndroidDir "gradlew.bat") @wrapperArgs
    }
    if ($LASTEXITCODE -ne 0) { throw "Gradle 构建失败" }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------- 结果
$apk = Get-ChildItem (Join-Path $AndroidDir "app\build\outputs\apk") -Recurse -Filter "*.apk" |
    Where-Object { $_.Name -notlike "*-unsigned*" } |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $apk) { throw "未找到 APK 产物" }

Write-Step "产物"
$sizeMb = [math]::Round($apk.Length / 1MB, 2)
Write-Ok "$($apk.FullName) （$sizeMb MB）"

$buildTools = Get-ChildItem (Join-Path $sdk "build-tools") -Directory |
    Sort-Object Name -Descending | Select-Object -First 1
$aapt = Join-Path $buildTools.FullName "aapt2.exe"
if (Test-Path $aapt) {
    Write-Step "APK 信息"
    & $aapt dump badging $apk.FullName 2>$null |
        Select-String -Pattern "^package|^sdkVersion|^targetSdkVersion|^application-label:|^launchable-activity|^uses-permission" |
        ForEach-Object { Write-Host "    $($_.Line)" }
}
$apkSigner = Join-Path $buildTools.FullName "apksigner.bat"
if (Test-Path $apkSigner) {
    & $apkSigner verify --print-certs $apk.FullName 2>$null | Select-Object -First 3 |
        ForEach-Object { Write-Host "    $_" -ForegroundColor Green }
}

Write-Host ""
Write-Host "构建完成。" -ForegroundColor Green
