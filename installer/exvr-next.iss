#define AppName "ExVR-Next"
#define AppVersion "0.8.2.5.2"
#define BinaryVersion "0.8.2.5"
#define AppPublisher "ExVR-Next contributors"
#define AppUrl "https://github.com/Herielmn/ExVR"
#define HostExe "ExVR-Next.exe"
#define CoreExe "ExVR.exe"
#define WebView2Guid "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
#define WebView2Url "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

#define SourceDir "..\dist\ExVR"
#if !DirExists(SourceDir)
  #error dist\ExVR is missing: run PyInstaller and copy host\target\release\ExVR-Next.exe into it first
#endif
#if !FileExists(SourceDir + "\" + HostExe)
  #error dist\ExVR\ExVR-Next.exe is missing: cargo build --release, then copy it next to ExVR.exe
#endif

#define StateDir SourceDir + "\_internal\settings"
#if FileExists(StateDir + "\pairing.json") || DirExists(StateDir + "\ssl") || DirExists(StateDir + "\logs")
  #error dist\ExVR\_internal\settings holds per-install state (pairing.json, ssl, logs) from a test run: delete those three before building the installer
#endif

#define ChineseIsl "compiler:Languages\ChineseSimplified.isl"
#if !FileExists(CompilerPath + "Languages\ChineseSimplified.isl")
  #undef ChineseIsl
  #define ChineseIsl "compiler:Default.isl"
#endif

[Setup]
AppId={{9B4F2C6E-3A57-4D18-9F2C-7E6D5A1B0C34}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppSupportURL={#AppUrl}
AppUpdatesURL={#AppUrl}
VersionInfoVersion={#BinaryVersion}
VersionInfoProductName={#AppName}

DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=no
LicenseFile=..\LICENSE
SetupIconFile=..\logo\logo.ico
UninstallDisplayIcon={app}\{#HostExe}
UninstallDisplayName={#AppName} {#AppVersion}

OutputDir=..\build\installer
OutputBaseFilename={#AppName}-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=4

WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "zh"; MessagesFile: "{#ChineseIsl}"

[LangOptions]
zh.LanguageName=<4E2D><6587><FF08><7B80><4F53><FF09>
zh.LanguageID=$0804

[CustomMessages]
en.DesktopIcon=Create a desktop shortcut
zh.DesktopIcon=创建桌面快捷方式
en.WebView2Missing=%1 needs the Microsoft Edge WebView2 runtime, which this computer does not have yet. Setup will download Microsoft's installer for it (about 2 MB).
zh.WebView2Missing=%1 需要 Microsoft Edge WebView2 运行时，这台电脑还没有装。安装程序会下载微软的安装器（约 2 MB）。
en.WebView2Installing=Installing the Microsoft Edge WebView2 runtime...
zh.WebView2Installing=正在安装 Microsoft Edge WebView2 运行时…
en.WebView2Failed=The WebView2 runtime could not be downloaded:%n%n%1%n%nSetup can continue, but %2 will not open its window until you install "Evergreen Bootstrapper" from Microsoft's WebView2 page yourself. Continue anyway?
zh.WebView2Failed=WebView2 运行时下载失败：%n%n%1%n%n安装可以继续，但在你自己从微软 WebView2 页面装上「Evergreen Bootstrapper」之前，%2 打不开界面。仍要继续吗？
en.RemoveDrivers=Remove the VMT and VRto3D drivers from SteamVR, and the VRCFaceTracking module, as well?%n%nChoose No if another application still uses them.
zh.RemoveDrivers=同时从 SteamVR 移除 VMT 与 VRto3D 驱动，以及 VRCFaceTracking 模块吗？%n%n如果还有别的程序在用它们，请选「否」。
en.RemovingDrivers=Removing the SteamVR drivers...
zh.RemovingDrivers=正在移除 SteamVR 驱动…
en.LaunchAfter=Start %1
zh.LaunchAfter=启动 %1

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; \
    Excludes: "_internal\settings\*"; \
    Flags: recursesubdirs createallsubdirs ignoreversion
Source: "{#SourceDir}\_internal\settings\*"; DestDir: "{app}\_internal\settings"; \
    Excludes: "pairing.json,*.pem,ssl\*,logs\*"; \
    Flags: recursesubdirs createallsubdirs onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#HostExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#HostExe}"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; \
    StatusMsg: "{cm:WebView2Installing}"; Check: WebView2Downloaded; \
    Flags: waituntilterminated
Filename: "{app}\{#HostExe}"; Description: "{cm:LaunchAfter,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal\settings"
Type: filesandordirs; Name: "{localappdata}\{#AppName}\WebView2"
Type: dirifempty; Name: "{localappdata}\{#AppName}"
Type: dirifempty; Name: "{app}"

[Code]
var
  DownloadPage: TDownloadWizardPage;
  DownloadedWebView2: Boolean;

function WebView2Present: Boolean;
var
  Version: String;
begin
  Result := False;
  if RegQueryStringValue(HKLM,
      'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{#WebView2Guid}',
      'pv', Version) then
    Result := (Version <> '') and (Version <> '0.0.0.0');
  if not Result then
    if RegQueryStringValue(HKLM,
        'SOFTWARE\Microsoft\EdgeUpdate\Clients\{#WebView2Guid}',
        'pv', Version) then
      Result := (Version <> '') and (Version <> '0.0.0.0');
  if not Result then
    if RegQueryStringValue(HKCU,
        'SOFTWARE\Microsoft\EdgeUpdate\Clients\{#WebView2Guid}',
        'pv', Version) then
      Result := (Version <> '') and (Version <> '0.0.0.0');
end;

function WebView2Downloaded: Boolean;
begin
  Result := DownloadedWebView2;
end;

function OnDownloadProgress(const Url, Filename: String;
  const Progress, ProgressMax: Int64): Boolean;
begin
  Result := True;
end;

procedure InitializeWizard;
begin
  DownloadedWebView2 := False;
  DownloadPage := CreateDownloadPage(SetupMessage(msgWizardPreparing),
                                     SetupMessage(msgPreparingDesc),
                                     @OnDownloadProgress);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Failure, Reason: String;
begin
  Result := True;
  if (CurPageID <> wpReady) or WebView2Present then
    exit;
  if MsgBox(FmtMessage(CustomMessage('WebView2Missing'), ['{#AppName}']),
            mbInformation, MB_OKCANCEL) = IDCANCEL then
  begin
    Result := False;
    exit;
  end;
  DownloadPage.Clear;
  DownloadPage.Add('{#WebView2Url}', 'MicrosoftEdgeWebview2Setup.exe', '');
  DownloadPage.Show;
  try
    try
      DownloadPage.Download;
      DownloadedWebView2 := True;
    except
      Reason := GetExceptionMessage;
      Failure := FmtMessage(CustomMessage('WebView2Failed'), [Reason, '{#AppName}']);
      Result := MsgBox(Failure, mbError, MB_YESNO) = IDYES;
    end;
  finally
    DownloadPage.Hide;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Core: String;
  ResultCode: Integer;
begin
  if CurUninstallStep <> usUninstall then
    exit;
  Core := ExpandConstant('{app}\{#CoreExe}');
  if not FileExists(Core) then
    exit;
  if SuppressibleMsgBox(CustomMessage('RemoveDrivers'), mbConfirmation,
                        MB_YESNO, IDNO) <> IDYES then
    exit;
  Exec(Core, '--drivers uninstall', ExpandConstant('{app}'), SW_HIDE,
       ewWaitUntilTerminated, ResultCode);
end;
