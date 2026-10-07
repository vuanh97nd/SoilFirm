@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Chay_thu.ps1"
if errorlevel 1 pause
endlocal
