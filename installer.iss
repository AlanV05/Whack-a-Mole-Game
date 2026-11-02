; Inno Setup script - turns dist\WhackAMole\ into one WhackAMole_Setup.exe installer.
; Built automatically by .github/workflows/build-windows.yml, or by hand:
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
;
; Installs per user (no admin password needed) into %LOCALAPPDATA%\WhackAMole,
; which is writable, so whack_settings.json and whack_log.txt can live next to the game.

#define AppName "Whack-a-Mole (ENGG3000 Group 4)"
#define AppExe  "WhackAMole.exe"
#ifndef AppVersion
  #define AppVersion "3.0"
#endif

[Setup]
AppId={{F9E969A4-CD46-4EF5-93E9-9260D156574F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=ENGG3000 Group 4
DefaultDirName={localappdata}\WhackAMole
DefaultGroupName=Whack-a-Mole
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=WhackAMole_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppExe}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\WhackAMole\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Whack-a-Mole"; Filename: "{app}\{#AppExe}"
Name: "{group}\Whack-a-Mole (on the TV / screen 2)"; Filename: "{app}\{#AppExe}"; Parameters: "--display 1"
Name: "{group}\Whack-a-Mole settings file"; Filename: "{app}\whack_settings.json"
Name: "{group}\Uninstall Whack-a-Mole"; Filename: "{uninstallexe}"
Name: "{userdesktop}\Whack-a-Mole"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Play Whack-a-Mole now"; Flags: nowait postinstall skipifsilent
