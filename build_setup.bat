@echo off
setlocal
cd /d "%~dp0"
call build_exe.bat --no-pause
if errorlevel 1 goto failed
set "SOILFIRM_SETUP_COMPILER="
for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined SOILFIRM_SETUP_COMPILER set "SOILFIRM_SETUP_COMPILER=%%I"
if not defined SOILFIRM_SETUP_COMPILER if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "SOILFIRM_SETUP_COMPILER=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined SOILFIRM_SETUP_COMPILER if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "SOILFIRM_SETUP_COMPILER=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined SOILFIRM_SETUP_COMPILER goto no_inno
"%SOILFIRM_SETUP_COMPILER%" "SoilFirm_Professional.iss" > build_setup.log 2>&1
set "SOILFIRM_SETUP_RESULT=%ERRORLEVEL%"
type build_setup.log
if not "%SOILFIRM_SETUP_RESULT%"=="0" goto failed
echo Setup build passed. See the output path in build_setup.log.
pause
exit /b 0
:no_inno
echo EXE passed but Inno Setup 6 was not found.
echo Install Inno Setup 6 or open SoilFirm_Professional.iss and click Compile.
pause
exit /b 1
:failed
echo Build failed. Read build_exe.log or build_setup.log.
pause
exit /b 1
