@echo off
chcp 65001 >nul
rem Launch N-body gravity simulation. Uses the "py" launcher which has pygame.

cd /d "%~dp0"

py main.py

if errorlevel 1 (
    echo.
    echo [!] Program exited with error code %errorlevel%
    pause
)
