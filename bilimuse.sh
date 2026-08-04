#!/usr/bin/env bash
# BiliMuse 命令包装（Unix：./bilimuse.sh tui；激活 venv 后直接 bilimuse）
set -e
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.venv/bin/python" -m bilimuse "$@"
