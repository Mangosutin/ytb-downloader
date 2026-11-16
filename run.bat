@echo off
setlocal

cd /d "%~dp0"

rem Use the project virtual environment when it exists.
if exist "%~dp0.venv\Scripts\python.exe" goto use_venv

rem Fall back to the Python 3.13 launcher, then python on PATH.
where py >nul 2>nul
if not errorlevel 1 goto use_py

where python >nul 2>nul
if not errorlevel 1 goto use_python

echo Python 3.13 was not found.
echo Create .venv or install Python 3.13.
pause
exit /b 1

:use_venv
"%~dp0.venv\Scripts\python.exe" "%~dp0main.py" "%~1" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %errorlevel%

:use_py
py -3.13 "%~dp0main.py" "%~1" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %errorlevel%

:use_python
python "%~dp0main.py" "%~1" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %errorlevel%
