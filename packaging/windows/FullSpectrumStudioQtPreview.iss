#define MyAppName "FullSpectrum Studio Qt Preview"
#ifndef MyAppVersion
  #define MyAppVersion "0.5.1-qt.1"
#endif
#define MyAppPublisher "FullSpectrum Studio contributors"
#define MyAppExeName "FullSpectrumStudioQt.exe"

[Setup]
; Deliberately distinct from the original FullSpectrum Studio Windows installer.
AppId={{B40E87FE-ED24-40E2-90A6-8D6A72FA85E8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\FullSpectrum Studio Qt Preview
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\release
OutputBaseFilename=FullSpectrum-Studio-Windows-Qt-Preview-Setup-v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\..\dist\FullSpectrumStudioQt\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
