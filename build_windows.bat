@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
    echo Python 3 was not found.
    echo Install 64-bit Python from https://www.python.org/downloads/windows/
    echo Enable "Add Python to PATH", then run this file again.
    pause
    exit /b 1
)

echo Installing build dependencies...
py -3 -m pip install --upgrade Pillow PyInstaller
if errorlevel 1 goto :failed

echo Building standalone Windows executable...
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name MT2ClassTool ^
  --collect-all PIL ^
  --hidden-import tkinter ^
  --add-data "mt2_core.py;." ^
  MT2ClassTool.pyw
if errorlevel 1 goto :failed

echo.
echo Build complete:
echo %CD%\dist\MT2ClassTool.exe
pause
exit /b 0

:failed
echo.
echo Build failed. Review the error above.
pause
exit /b 1
