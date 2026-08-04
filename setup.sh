#!/usr/bin/env bash
# BiliMuse 一键部署（Linux/macOS）
# 用法:  ./setup.sh                # 全量安装（ffmpeg + align + tui + web + dev，推荐）
#        ./setup.sh --lite         # 轻量模式（仅 m4a + dev 工具链）
#        ./setup.sh --portable     # 便携模式（运行时文件放项目 data/）
#        MIRROR= ./setup.sh        # 使用官方 PyPI（默认清华镜像）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LITE=0
PORTABLE=0
for arg in "$@"; do
  case "$arg" in
    --lite) LITE=1 ;;
    --portable) PORTABLE=1 ;;
  esac
done
VENV="$ROOT/.venv"
PY="$VENV/bin/python"

if [ ! -f "$PY" ]; then
  echo "创建虚拟环境 .venv ..."
  python3 -m venv "$VENV"
fi

PIP_ARGS=()
MIRROR="${MIRROR:-https://pypi.tuna.tsinghua.edu.cn/simple}"
PIP_ARGS+=("-i" "$MIRROR")

echo "升级 pip ..."
"$PY" -m pip install --upgrade pip "${PIP_ARGS[@]}"

PKG=".[ffmpeg,align,tui,web,dev]"
[ "$LITE" = 1 ] && PKG=".[dev]"
echo "安装依赖: $PKG"
cd "$ROOT"
"$PY" -m pip install -e "$PKG" "${PIP_ARGS[@]}"

echo ""
if [ "$PORTABLE" = 1 ]; then
  if [ ! -f "$ROOT/.portable" ]; then
    touch "$ROOT/.portable"
    echo "已创建 .portable，开启便携模式（config/logs/db 将放 data/）"
  fi
fi
echo "完成。使用方式:"
echo "  统一入口(推荐):   ./bilimuse-start（安装/配置/TUI/Web 一个入口）"
echo "  项目目录:         ./bilimuse.sh tui / ./bilimuse.sh get 歌名"
echo "  激活后任意目录:   source .venv/bin/activate 然后 bilimuse"
echo "  一键配置向导:     ./bilimuse-config"
echo "  一键启动 TUI:     ./bilimuse-tui"
[ "$LITE" = 1 ] && echo "提示: 轻量模式仅 m4a。需要 mp3/flac/TUI/Web/align 时重跑 ./setup.sh（全量）"
