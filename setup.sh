#!/usr/bin/env bash
# MusicalBILI 一键部署（Linux/macOS）
# 用法:  ./setup.sh                   # 轻量模式（仅 m4a，无 ffmpeg）
#        ./setup.sh --with-ffmpeg     # 完整模式（含 imageio-ffmpeg，支持 mp3/flac）
#        MIRROR= ./setup.sh           # 使用官方 PyPI（默认清华镜像）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WITH_FFMPEG="${1:-}"
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

PKG=".[dev]"
[ "$WITH_FFMPEG" = "--with-ffmpeg" ] && PKG=".[ffmpeg,dev]"
echo "安装依赖: $PKG"
cd "$ROOT"
"$PY" -m pip install -e "$PKG" "${PIP_ARGS[@]}"

echo "完成。运行: $PY -m musicalbili --help"
[ "$WITH_FFMPEG" != "--with-ffmpeg" ] && echo "提示: 需要 mp3/flac 时用 ./setup.sh --with-ffmpeg 重装"
