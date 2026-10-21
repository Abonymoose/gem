@echo off
rem Installs the build from dist\Gem into %LOCALAPPDATA%\Programs\Gem, where the Start Menu shortcut and
rem Start with Windows point, then starts it. Your data in %USERPROFILE%\.gem is not touched.
cd /d "%~dp0"
if not exist dist\Gem\Gem.exe (
  echo Build Gem first with build.bat
  exit /b 1
)
taskkill /im Gem.exe >nul 2>&1
timeout /t 2 /nobreak >nul
taskkill /im Gem.exe /f >nul 2>&1
robocopy dist\Gem "%LOCALAPPDATA%\Programs\Gem" /MIR /R:3 /W:1 /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
  echo Copying failed. Is Gem still running?
  exit /b 1
)
start "" "%LOCALAPPDATA%\Programs\Gem\Gem.exe"
echo Gem installed.
