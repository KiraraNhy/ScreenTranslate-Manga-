@echo off
rem ASCII-only on purpose; Chinese messages are printed by Python.
cd /d "%~dp0"
python -m mangalens %*
if errorlevel 1 pause
