@echo off
rem Builds dist\Gem.exe
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --icon=gem.ico --name Gem ^
  --additional-hooks-dir hooks --hidden-import pystray._win32 ^
  --collect-data speech_recognition --collect-all piper --collect-data tzdata --collect-submodules gem gem2.py
