@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
    echo Python 3 was not found. Install it from https://www.python.org/downloads/windows/
    pause
    exit /b 1
)
py -3 -m pip install Pillow
start "" pyw -3 MT2ClassTool.pyw
