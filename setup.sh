#!/usr/bin/env bash
# BiliMuse 一键部署（Linux/macOS）
# 用法:  ./setup.sh                # 全量安装，默认便携模式（运行时文件放项目 data/，推荐）
#        ./setup.sh --lite         # 轻量模式（仅 m4a + dev 工具链）
#        ./setup.sh --standard     # 标准模式（config/logs/db 放系统目录 ~/.config/bilimuse）
#        MIRROR= ./setup.sh        # 使用官方 PyPI（默认清华镜像）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LITE=0
PORTABLE=1
for arg in "$@"; do
  case "$arg" in
    --lite) LITE=1 ;;
    --standard) PORTABLE=0 ;;
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
  fi
  echo "便携模式（默认）：已开启，config/logs/db 放项目 data/（用 --standard 可改用系统目录）"
else
  if [ -f "$ROOT/.portable" ]; then
    echo "标准模式：系统目录配置，但检测到 .portable 存在（可用 bilimuse portable off 关闭便携）"
  else
    echo "标准模式：config/logs/db 放系统目录（~/.config/bilimuse）"
  fi
fi
echo "完成。使用方式:"
echo "  统一入口(推荐):   ./bilimuse-start（安装/配置/TUI/Web 一个入口）"
echo "  项目目录:         ./bilimuse.sh tui / ./bilimuse.sh get 歌名"
echo "  激活后任意目录:   source .venv/bin/activate 然后 bilimuse"
echo "  一键配置向导:     ./bilimuse-config"
echo "  一键启动 TUI:     ./bilimuse-tui"
[ "$LITE" = 1 ] && echo "提示: 轻量模式仅 m4a。需要 mp3/flac/TUI/Web/align 时重跑 ./setup.sh（全量）"
