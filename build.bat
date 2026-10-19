@echo off
rem Builds dist\Gem.exe
python -m PyInstaller --noconfirm --onefile --windowed --icon=gem.ico --name Gem ^
  --additional-hooks-dir hooks --hidden-import pystray._win32 ^
  --collect-data speech_recognition --collect-submodules gem gem2.py
