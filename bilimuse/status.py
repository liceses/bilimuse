"""统一状态通道：emit 一次，日志 + UI 显示双写。

- emit(level, text): 写日志文件；INFO/WARNING/ERROR 再转发给已注册的显示回调。
- register_display(cb): CLI/TUI/Web 注册同步显示回调（收 {"type":"status",...}）。
- DEBUG 仅写日志（不显示）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable

_handlers: list[Callable[[dict], None]] = []


def register_display(cb: Callable[[dict], None]) -> None:
    _handlers.append(cb)


def emit(level: str, text: str, data: dict | None = None) -> None:
    logger = logging.getLogger("bilimuse.status")
    lvl = getattr(logging, level.upper(), logging.INFO)
    logger.log(lvl, text)
    if lvl < logging.INFO:
        return
    event = {"type": "status", "level": level.upper(), "text": text, "data": data}
    for cb in _handlers:
        try:
            cb(event)
        except Exception:
            logger.exception("状态显示回调失败")
