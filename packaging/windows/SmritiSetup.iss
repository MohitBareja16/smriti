; Inno Setup Script for Smriti AI single-click Windows Installer
; Note: Uses DiskSpanning because bundled PYQs (1.7 GB) + Syllabus (359 MB) + Qwen2.5 model (~1 GB)
; exceed standard 2 GB single PE executable limits. Outputs Smriti-Setup.exe + .bin data slices.

#define MyAppName "Smriti AI"
#define MyAppVersion "0.2.0"
#define MyAppPublisher "Smriti Contributors"
#define MyAppExeName "Start-Smriti.exe"

[Setup]
AppId={{8E74A2B1-52B4-4F0D-9E8C-3E92A1F0A020}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\SmritiAI
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\..\dist\installer
OutputBaseFilename=Smriti-Setup
Compression=lzma2/fast
SolidCompression=no
DiskSpanning=yes
SlicesPerDisk=1
DiskSliceSize=1900000000
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\Start-Smriti\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
