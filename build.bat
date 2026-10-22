@echo off
rem Builds dist\Gem\ (Gem.exe plus its _internal folder). A folder build starts in a couple of seconds;
rem a single-file exe has to unpack ~160 MB to a temp folder every time it starts.
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onedir --windowed --icon=gem.ico --name Gem --version-file version_info.txt ^
  --additional-hooks-dir hooks --hidden-import pystray._win32 ^
  --collect-data speech_recognition --collect-all piper --collect-all vosk --collect-data tzdata ^
  --collect-submodules gem gem2.py
