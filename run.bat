@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
    echo Usage: run.bat "YouTube URL" [--mode video^|audio] [--config PATH]
    exit /b 2
)

if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0run.py" %*
) else (
    python "%~dp0run.py" %*
)
exit /b %errorlevel%
