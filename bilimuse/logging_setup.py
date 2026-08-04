"""日志初始化：文件滚动 + console WARNING。幂等配置 bilimuse 命名空间。"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import default_config_dir

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
_NAMESPACE = "bilimuse"


def log_dir() -> Path:
    return default_config_dir() / "logs"


def setup_logging(level: str | None = None, console_warning: bool = True) -> None:
    """配置根日志（幂等：总是重建 handler，支持改目录/级别）。level: 参数 → MUSICALBILI_LOG_LEVEL → 默认 INFO。"""
    level = (level or os.environ.get("MUSICALBILI_LOG_LEVEL") or "INFO").upper()
    root = logging.getLogger(_NAMESPACE)
    root.setLevel(level)
    root.propagate = False
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()
    d = log_dir()
    d.mkdir(parents=True, exist_ok=True)
    fh = RotatingFileHandler(d / "bilimuse.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(fh)
    if console_warning:
        ch = logging.StreamHandler()
        ch.setLevel(logging.WARNING)
        ch.addFilter(lambda r: not r.name.startswith(f"{_NAMESPACE}.status"))
        ch.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"{_NAMESPACE}.{name}")
