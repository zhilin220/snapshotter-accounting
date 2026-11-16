@echo off
title Install SnapShotter
cd /d "%~dp0"
echo Installing SnapShotter requirements...
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo Installation failed. Make sure Python 3.10 or newer is installed and added to PATH.
  pause
  exit /b 1
)
echo.
echo Installation complete. Double-click run.bat to start SnapShotter.
pause
