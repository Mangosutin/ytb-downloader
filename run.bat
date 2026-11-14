@echo off
setlocal

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3.13 main.py %*
    exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel%==0 (
    python main.py %*
    exit /b %errorlevel%
)

echo Python 3.13 was not found.
echo Please install Python 3.13.
pause
exit /b 1
