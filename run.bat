@echo off
setlocal DisableDelayedExpansion

cd /d "%~dp0"

if "%~1"=="" (
    echo Usage: run.bat "YouTube URL" [--mode video^|audio] [--config PATH]
    exit /b 2
)

rem Keep the URL out of the command line after capture. This avoids a second
rem interpretation of ampersands by cmd.exe when forwarding arguments.
set "YTB_DOWNLOADER_URL=%~1"
shift

if exist "%~dp0.venv\Scripts\python.exe" goto use_venv

where py >nul 2>nul
if not errorlevel 1 goto use_py

where python >nul 2>nul
if not errorlevel 1 goto use_python

echo Python 3.13 was not found.
echo Create .venv or install Python 3.13.
pause
exit /b 1

:use_venv
"%~dp0.venv\Scripts\python.exe" "%~dp0main.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %errorlevel%

:use_py
py -3.13 "%~dp0main.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %errorlevel%

:use_python
python "%~dp0main.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %errorlevel%
