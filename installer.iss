; 업무 도우미 설치 파일 (Inno Setup)
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppId={{6C1E2F4B-8A3D-4B7E-9F21-5D0C3A7E1B92}
AppName=업무 도우미
AppVersion={#MyAppVersion}
AppVerName=업무 도우미 {#MyAppVersion}
AppPublisher=kakario777
DefaultDirName={autopf}\WorkHelper
DisableProgramGroupPage=yes
DisableDirPage=yes
UninstallDisplayIcon={app}\WorkHelper.exe
UninstallDisplayName=업무 도우미
OutputDir=installer_out
OutputBaseFilename=WorkHelper_Setup
Compression=lzma2/max
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no
WizardStyle=modern
SetupIconFile=icon.ico
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany=kakario777
VersionInfoDescription=업무 도우미 설치
VersionInfoProductName=WorkHelper

[Languages]
#if FileExists(CompilerPath + "Languages\Korean.isl")
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
#else
Name: "english"; MessagesFile: "compiler:Default.isl"
#endif

[Files]
Source: "dist\WorkHelper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\업무 도우미"; Filename: "{app}\WorkHelper.exe"
Name: "{autodesktop}\업무 도우미"; Filename: "{app}\WorkHelper.exe"; Check: IsFirstInstall

[Run]
Filename: "{app}\WorkHelper.exe"; Description: "업무 도우미 실행"; Flags: nowait postinstall skipifsilent
Filename: "{app}\WorkHelper.exe"; Parameters: "--updated"; Flags: nowait runasoriginaluser; Check: ShouldRestart

[Code]
const
  UninstKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{6C1E2F4B-8A3D-4B7E-9F21-5D0C3A7E1B92}_is1';
var
  FirstInstall: Boolean;

{ 처음 설치일 때만 바탕화면 바로가기를 만듦 (업데이트 때는 건드리지 않음) }
function InitializeSetup(): Boolean;
begin
  FirstInstall := not (RegKeyExists(HKLM, UninstKey) or RegKeyExists(HKCU, UninstKey));
  Result := True;
end;

function IsFirstInstall(): Boolean;
begin
  Result := FirstInstall;
end;

function ShouldRestart(): Boolean;
begin
  Result := ExpandConstant('{param:restart|0}') = '1';
end;
