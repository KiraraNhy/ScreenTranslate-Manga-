@echo off
rem This file is intentionally ASCII-only. cmd.exe parses .bat files using the
rem system code page, so all Chinese messages are printed by tools\setup.py.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto no_python

python "%~dp0tools\setup.py"
pause
exit /b 0

:no_python
echo.
echo  [ERROR] Python not found.
echo.
echo  Please install Python 3.10 or newer first.
echo  During setup, tick "Add Python to PATH".
echo  Download: https://www.python.org/downloads/
echo.
pause
exit /b 1
