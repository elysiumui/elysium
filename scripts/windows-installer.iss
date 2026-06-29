; Inno Setup script for Elysium Designer.
;
; Packages the PyInstaller *onefile* build (dist\ElysiumDesigner.exe, produced
; by scripts/build-designer.spec) into a Windows installer. Invoked by
; .github/workflows/release-designer.yml:
;
;   iscc.exe scripts\windows-installer.iss /F"Elysium-Designer-Windows-x64-Setup"
;
; The app version is read from the ELYSIUM_VERSION environment variable that the
; workflow's "Pick version" step exports. Paths are resolved relative to this
; script's own directory ({#SourcePath} == scripts\) so the compile works no
; matter what the current working directory is.

#define MyAppName "Elysium Designer"
#define MyAppPublisher "Elysium UI"
#define MyAppURL "https://github.com/klamaute/Elysium"
#define MyAppExeName "ElysiumDesigner.exe"
#define MyAppVersion GetEnv("ELYSIUM_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "0.0.0"
#endif

[Setup]
AppId={{A1B2C3D4-E5F6-4789-ABCD-EF0123456789}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\Elysium Designer
DefaultGroupName=Elysium Designer
DisableProgramGroupPage=yes
OutputDir={#SourcePath}\..\dist
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#SourcePath}\..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Elysium Designer"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall Elysium Designer"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Elysium Designer"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Elysium Designer"; Flags: nowait postinstall skipifsilent
