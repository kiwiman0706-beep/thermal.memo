; Inno Setup スクリプト（Windows インストーラ）
;
;   iscc /DAppVersion=0.1.0 packaging\installer.iss
;
; PyInstaller の --onedir 出力（dist\thermal-memo\）を丸ごと入れる。
; PrivilegesRequired=lowest にしているので管理者権限は不要。院内 PC で
; 管理者アカウントを借りずに導入・自動更新できる。

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "thermal.memo"
#define AppExe "thermal-memo.exe"
#define AppPublisher "thermal.memo"
#define AppUrl "https://github.com/kiwiman0706-beep/thermal.memo"

[Setup]
; AppId は更新時に同じ製品と認識させるため固定する（変更しないこと）
AppId={{7C1F3B4A-2D6E-4A17-9C58-3E0B5A9D41F2}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
VersionInfoVersion={#AppVersion}

DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible

OutputDir=..\dist_installer
OutputBaseFilename=thermal-memo-{#AppVersion}-windows-setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

; 起動中に更新をかけたときにファイルを差し替えられるようにする
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作る"; GroupDescription: "追加のアイコン:"

[Files]
Source: "..\dist\thermal-memo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{#AppName} をアンインストール"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{#AppName} を起動する"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 設定と履歴（%APPDATA%\thermal.memo）はアンインストールしても残す。
; 消したい場合は手動で削除してもらう（誤操作で印刷履歴を失わないため）。
