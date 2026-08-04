# BiliMuse 一键部署（Windows）
# 用法:  .\setup.ps1                # 全量安装，默认便携模式（运行时文件放项目 data/，推荐）
#        .\setup.ps1 -Lite          # 轻量模式（仅 m4a + dev 工具链）
#        .\setup.ps1 -Standard      # 标准模式（config/logs/db 放系统目录 %APPDATA%\bilimuse）
#        .\setup.ps1 -Mirror ""     # 使用官方 PyPI（默认清华镜像）

param(
    [switch]$Lite,
    [switch]$Standard,
    [string]$Mirror = "https://pypi.tuna.tsinghua.edu.cn/simple"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

$venv = Join-Path $root ".venv"
$py = Join-Path $venv "Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "创建虚拟环境 .venv ..."
    python -m venv $venv
}

$pipArgs = @()
if ($Mirror) { $pipArgs += @("-i", $Mirror) }

Write-Host "升级 pip ..."
& $py -m pip install --upgrade pip @pipArgs

$pkg = if ($Lite) { ".[dev]" } else { ".[ffmpeg,align,tui,web,dev]" }
Write-Host "安装依赖: $pkg"
Push-Location $root
try {
    & $py -m pip install -e $pkg @pipArgs
} finally {
    Pop-Location
}

Write-Host ""
if ($Standard) {
    $marker = Join-Path $root ".portable"
    if (Test-Path $marker) {
        Write-Host "标准模式：系统目录配置，但检测到 .portable 存在（可用 bilimuse portable off 关闭便携）"
    } else {
        Write-Host "标准模式：config/logs/db 放系统目录（%APPDATA%\bilimuse）"
    }
} else {
    $marker = Join-Path $root ".portable"
    if (-not (Test-Path $marker)) {
        New-Item -ItemType File -Path $marker | Out-Null
    }
    Write-Host "便携模式（默认）：已开启，config/logs/db 放项目 data/（用 -Standard 可改用系统目录）"
}
Write-Host "完成。使用方式:"
Write-Host "  统一入口(推荐):     双击 bilimuse-start.cmd（安装/配置/TUI/Web 一个入口）"
Write-Host "  cmd 项目目录直接:   bilimuse tui / bilimuse get 歌名"
Write-Host "  PowerShell 项目目录: .\bilimuse tui"
Write-Host "  激活后任意目录:      .\.venv\Scripts\Activate.ps1 然后 bilimuse"
Write-Host "  一键配置向导:        双击 bilimuse-config.cmd"
Write-Host "  一键启动 TUI:        双击 bilimuse-tui.cmd"
if ($Lite) {
    Write-Host "提示: 轻量模式仅 m4a。需要 mp3/flac/TUI/Web/歌词校准(align) 时，重跑 .\setup.ps1（全量）"
}
