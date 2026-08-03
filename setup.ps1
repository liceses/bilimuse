# MusicalBILI 一键部署（Windows）
# 用法:  .\setup.ps1                # 轻量模式（仅 m4a，无 ffmpeg）
#        .\setup.ps1 -WithFfmpeg    # 完整模式（含 imageio-ffmpeg，支持 mp3/flac）
#        .\setup.ps1 -Mirror ""     # 使用官方 PyPI（默认清华镜像）

param(
    [switch]$WithFfmpeg,
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

$pkg = if ($WithFfmpeg) { ".[ffmpeg,dev]" } else { ".[dev]" }
Write-Host "安装依赖: $pkg"
Push-Location $root
try {
    & $py -m pip install -e $pkg @pipArgs
} finally {
    Pop-Location
}

Write-Host "完成。运行: .\.venv\Scripts\python.exe -m musicalbili --help"
if (-not $WithFfmpeg) {
    Write-Host "提示: 需要 mp3/flac 时用 .\setup.ps1 -WithFfmpeg 重装"
}
