@echo off
setlocal
cd /d "%~dp0"
title SoilFirm Pro
set "SOILFIRM_PYTHON=python"
python -c "import sys" >nul 2>&1
if not errorlevel 1 goto check_main
py -3 -c "import sys" >nul 2>&1
if errorlevel 1 goto no_python
set "SOILFIRM_PYTHON=py -3"
:check_main
if not exist "%~dp0main.py" goto no_main
%SOILFIRM_PYTHON% -c "import tkinter, requests, PIL, reportlab, openpyxl, pypdf" >nul 2>&1
if not errorlevel 1 goto check_player
echo Installing missing runtime libraries...
%SOILFIRM_PYTHON% -m pip install "Pillow>=10" "requests>=2.31" "reportlab>=4" "openpyxl>=3.1" "pypdf>=5"
if errorlevel 1 goto failed
:check_player
%SOILFIRM_PYTHON% -c "import webview" >nul 2>&1
if not errorlevel 1 goto launch
echo Installing embedded player...
%SOILFIRM_PYTHON% -m pip install "pywebview>=5,<7"
if errorlevel 1 echo Player installation failed. SoilFirm Pro will still start.
:launch
echo Starting SoilFirm Pro...
%SOILFIRM_PYTHON% "%~dp0main.py"
if errorlevel 1 goto failed
exit /b 0
:no_python
echo ERROR: Python was not found. Install Python and add it to PATH.
pause
exit /b 1
:no_main
echo ERROR: main.py was not found in this folder.
pause
exit /b 1
:failed
echo ERROR: SoilFirm Pro could not start. Read the message above.
echo Startup log: %LOCALAPPDATA%\SoilFirm\logs\startup_error.log
pause
exit /b 1
