@echo off
cd /d "%~dp0"
title Desktop Lyrics

set "PYEXE="

rem 0) 项目虚拟环境（已装好全部依赖，最高优先级）
if exist "%~dp0.build-venv\Scripts\python.exe" (
    set "PYEXE=%~dp0.build-venv\Scripts\python.exe"
    goto :found
)

rem 1) D:\python\<version>\python.exe (installed per version)
if exist "D:\python\3.13.12\python.exe" (
    set "PYEXE=D:\python\3.13.12\python.exe"
    goto :found
)

rem 2) Any version folder under D:\python (wildcard)
for /d %%D in ("D:\python\*") do (
    if exist "%%D\python.exe" (
        set "PYEXE=%%D\python.exe"
        goto :found
    )
)

rem 3) WorkBuddy portable Python
for /d %%D in ("%USERPROFILE%\.workbuddy\binaries\python\versions\*") do (
    if exist "%%D\python.exe" (
        set "PYEXE=%%D\python.exe"
        goto :found
    )
)

rem 4) System python on PATH
where python >nul 2>&1
if %errorlevel%==0 (
    set "PYEXE=python"
    goto :found
)

rem 5) Python Launcher
where py >nul 2>&1
if %errorlevel%==0 (
    set "PYEXE=py -3"
    goto :found
)

echo [ERROR] Python not found. Install Python 3.10+ and add to PATH.
pause
exit /b 1

:found
echo Using Python: %PYEXE%
%PYEXE% main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Program exited unexpectedly.
    echo Please install dependencies:
    echo   "%PYEXE%" -m pip install -r requirements.txt
    pause
)
