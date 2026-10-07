; ============================================================================
;  VoxNode 声枢 —— Inno Setup 安装脚本
;
;  编译方式（在仓库根目录执行）：
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
;  或使用一键脚本： powershell -ExecutionPolicy Bypass -File packaging\build.ps1
;
;  先决条件：已用 PyInstaller 生成 dist\VoxNode\（见 packaging\voxnode.spec）
; ============================================================================

#define MyAppName "VoxNode"
#define MyAppNameZh "声枢"
#define MyAppVersion "0.6.0"
#define MyAppPublisher "VoxNode contributors"
#define MyAppURL "https://github.com/Almmor/miiotpcapi"
#define MyAppExeName "VoxNode.exe"
; 与软件内「开机自启」使用同一个注册表项，保证两处设置一致
#define RunValueName "VoxNode"

[Setup]
; 每个应用唯一的 AppId，升级时保持不变
AppId={{7C4E1A92-3B6D-4F58-9E21-A8D53C7B6E40}
AppName={#MyAppName} {#MyAppNameZh}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppNameZh} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}

; 默认按当前用户安装，无需管理员权限（{autopf} 会解析为
; %LOCALAPPDATA%\Programs，不会触发 UAC）
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
AllowNoIcons=yes

; 产物输出
OutputDir=..\dist
OutputBaseFilename=VoxNode-Setup-{#MyAppVersion}
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppNameZh}

; 压缩
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4

WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimp"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "autostart"; Description: "开机时自动启动（登录后最小化运行）"; GroupDescription: "启动选项："; Flags: unchecked

[Files]
; 打包 PyInstaller 的全部产物
Source: "..\dist\VoxNode\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\VoxNode\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName} {#MyAppNameZh}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} 首次部署向导"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--setup"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName} {#MyAppNameZh}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; 开机自启（与软件内设置共用同一个注册表值）
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "{#RunValueName}"; \
    ValueData: """{app}\{#MyAppExeName}"" --minimized"; \
    Flags: uninsdeletevalue; Tasks: autostart
; 清理旧品牌名（MiPC Bridge）可能残留的自启动项
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
    ValueType: string; ValueName: "MiPCBridge"; Flags: deletevalue

[Run]
Description: "立即启动 {#MyAppName} {#MyAppNameZh}"; Filename: "{app}\{#MyAppExeName}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 仅清理安装目录下可能产生的运行时文件，不动用户配置目录（%USERPROFILE%\.voxnode）
Type: filesandordirs; Name: "{app}\_internal"

[Code]
{ 安装 / 卸载前结束正在运行的实例，避免文件占用导致失败 }
procedure KillRunningApp();
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/f /im {#MyAppExeName}', '', SW_HIDE,
       ewWaitUntilTerminated, ResultCode);
end;

function InitializeSetup(): Boolean;
begin
  KillRunningApp();
  Result := True;
end;

function InitializeUninstall(): Boolean;
begin
  KillRunningApp();
  Result := True;
end;
