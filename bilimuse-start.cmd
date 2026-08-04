@echo off
rem BiliMuse unified launcher (Windows): install -> config -> use
rem Double-click to run; or pass an action: bilimuse-start.cmd [config|tui|web]
setlocal
title BiliMuse
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"

rem Direct action mode
if not "%~1"=="" goto :dispatch

if not exist "%PY%" goto :install

rem Auto-open config wizard on first run (detect config.json)
"%PY%" -c "import sys; from pathlib import Path; from bilimuse.config import default_config_dir; sys.exit(0 if (default_config_dir()/'config.json').is_file() else 1)" >nul 2>&1
if errorlevel 1 (
    echo [BiliMuse] First run, opening config wizard...
    "%PY%" -m bilimuse config
)

:menu
cls
echo ================= BiliMuse =================
echo  1  Config wizard (login/download dir/format/model)
echo  2  Launch TUI
echo  3  Launch Web (http://127.0.0.1:8000)
echo  4  Command line
echo  5  Repair / reinstall dependencies
echo  0  Exit
echo ============================================
set /p "ch=Choice [0-5]: "
if "%ch%"=="" exit /b 0
if "%ch%"=="1" goto :config
if "%ch%"=="2" goto :tui
if "%ch%"=="3" goto :web
if "%ch%"=="4" goto :cli
if "%ch%"=="5" goto :setup
if "%ch%"=="0" exit /b 0
goto :menu

:dispatch
if not exist "%PY%" (
    echo [BiliMuse] Not installed yet. Run bilimuse-start.cmd with no args first.
    pause
    exit /b 1
)
if /i "%~1"=="config" goto :config_direct
if /i "%~1"=="tui"    goto :tui_direct
if /i "%~1"=="web"    goto :web_direct
echo Unknown arg: %~1 (supported: config / tui / web)
exit /b 1

:config_direct
"%PY%" -m bilimuse config
pause
exit /b 0

:tui_direct
"%PY%" -m bilimuse tui
exit /b 0

:web_direct
"%PY%" -m bilimuse web
exit /b 0

:install
echo [BiliMuse] No venv found, starting first-time install...
echo Creating virtual env .venv ...
python -m venv "%ROOT%.venv"
if errorlevel 1 goto :fail
echo Installing deps (full: ffmpeg + align + tui + web)...
"%PY%" -m pip install -e ".[ffmpeg,align,tui,web,dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto :fail
echo Install done.
if not exist "%ROOT%.portable" type nul > "%ROOT%.portable"
echo Portable mode enabled by default: config/logs/db go to project data/.
goto :menu

:config
"%PY%" -m bilimuse config
pause
goto :menu

:tui
"%PY%" -m bilimuse tui
goto :menu

:web
echo Starting web server. Press Ctrl+C to stop and return here.
"%PY%" -m bilimuse web
echo Web server stopped.
pause
goto :menu

:cli
set /p "cmdline=bilimuse> "
if "%cmdline%"=="" goto :menu
"%PY%" -m bilimuse %cmdline%
pause
goto :menu

:setup
"%PY%" -m pip install -e ".[ffmpeg,align,tui,web,dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto :fail
if not exist "%ROOT%.portable" type nul > "%ROOT%.portable"
echo Dependencies updated. Portable mode enabled by default (project data/).
pause
goto :menu

:fail
echo.
echo Install failed. Check: Python 3.11+ installed and on PATH
pause
exit /b 1
