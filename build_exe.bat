@echo off
setlocal
cd /d "%~dp0"
set "SOILFIRM_BUILD_PYTHON=python"
python -c "import sys" >nul 2>&1
if not errorlevel 1 goto build
py -3 -c "import sys" >nul 2>&1
if errorlevel 1 goto no_python
set "SOILFIRM_BUILD_PYTHON=py -3"
:build
echo Building SoilFirm EXE. Log: %CD%\build_exe.log
%SOILFIRM_BUILD_PYTHON% -u build_for_setup.py > build_exe.log 2>&1
set "SOILFIRM_BUILD_RESULT=%ERRORLEVEL%"
type build_exe.log
if not "%SOILFIRM_BUILD_RESULT%"=="0" goto failed
echo EXE build passed. Keep the entire dist\SoilFirm_Professional folder.
goto finish
:no_python
echo ERROR: Python was not found. Install Python 64-bit first.
set "SOILFIRM_BUILD_RESULT=1"
goto finish
:failed
echo ERROR: EXE build failed. Read build_exe.log. Do not compile Setup yet.
:finish
if /I not "%~1"=="--no-pause" pause
exit /b %SOILFIRM_BUILD_RESULT%
