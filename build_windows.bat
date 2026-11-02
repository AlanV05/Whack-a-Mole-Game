@echo off
REM Build the Windows version by hand on a Windows laptop (the GitHub build does this for you).
REM Needs Python 3.12 from python.org. Optional: Inno Setup 6 for the installer.
python -m pip install pygame-ce python-osc pyinstaller || goto :error
pyinstaller --noconfirm WhackAMole.spec || goto :error
python -c "import json, game_settings; open('dist/WhackAMole/whack_settings.json','w').write(json.dumps(game_settings.DEFAULTS, indent=2))"
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
  echo Installer: installer_output\WhackAMole_Setup.exe
) else (
  echo Inno Setup not found - portable version only: dist\WhackAMole\WhackAMole.exe
)
goto :eof
:error
echo BUILD FAILED
exit /b 1
