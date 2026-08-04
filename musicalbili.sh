#!/usr/bin/env bash
# MusicalBILI 命令包装（Unix：./musicalbili.sh tui；激活 venv 后直接 musicalbili）
set -e
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.venv/bin/python" -m musicalbili "$@"
