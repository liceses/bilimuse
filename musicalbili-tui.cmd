@echo off
rem MusicalBILI one-click TUI launcher
setlocal
if not exist "%~dp0\.venv\Scripts\python.exe" (
    echo [MusicalBILI] venv not found, run setup.ps1 first
    pause
    exit /b 1
)
"%~dp0\.venv\Scripts\python.exe" -m musicalbili tui %*
echo.
pause
