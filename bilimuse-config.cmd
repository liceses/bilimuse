@echo off
rem BiliMuse one-click config wizard launcher
setlocal
if not exist "%~dp0\.venv\Scripts\python.exe" (
    echo [BiliMuse] venv not found, run setup.ps1 first
    pause
    exit /b 1
)
"%~dp0\.venv\Scripts\python.exe" -m bilimuse config %*
echo.
pause
