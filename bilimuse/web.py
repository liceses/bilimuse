"""FastAPI Web 界面（可选 extra [web]）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import Config, default_config_dir
from .services.aligner import (
    WHISPER_SIZES,
    align_available,
    detect_models,
    faster_whisper_installed,
    resolve_model,
)
from .services.pipeline import download_song_pipeline
from .services.search import search_versions

STATIC = Path(__file__).parent / "web" / "static"

app = FastAPI(title="BiliMuse")


def _serialize(obj):
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    if isinstance(obj, Path):
        return str(obj)
    return obj


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/search")
async def api_search(q: str, limit: int = 10) -> JSONResponse:
    hits = await search_versions(Config.load(), q, limit=limit)
    return JSONResponse([_serialize(h) for h in hits])


@app.get("/api/doctor")
async def api_doctor() -> JSONResponse:
    cfg = Config.load()
    return JSONResponse(
        {
            "python": sys.version.split()[0],
            "config_dir": str(default_config_dir()),
            "logged_in": bool(cfg.sessdata),
            "lyric_align": align_available(),
            "faster_whisper": faster_whisper_installed(),
            "whisper": resolve_model(cfg),
            "models": detect_models(),
            "sizes": WHISPER_SIZES,
        }
    )


@app.get("/api/model")
async def api_model() -> JSONResponse:
    return JSONResponse(
        {"resolve": resolve_model(Config.load()), "models": detect_models(), "sizes": WHISPER_SIZES}
    )


@app.websocket("/ws/download")
async def ws_download(ws: WebSocket) -> None:
    await ws.accept()
    try:
        msg = await ws.receive_json()
    except WebSocketDisconnect:
        return
    cfg = Config.load()
    if msg.get("format"):
        cfg.format = msg["format"]

    async def send(ev: dict) -> None:
        await ws.send_text(json.dumps(_serialize(ev), ensure_ascii=False))

    try:
        result = await download_song_pipeline(
            cfg,
            msg.get("bvid", ""),
            msg.get("page", 1),
            on_event=send,
            no_tag=bool(msg.get("no_tag")),
            no_lyric=bool(msg.get("no_lyric")),
            force_align=bool(msg.get("align")),
        )
        await send({"type": "result", "result": _serialize(result)})
    except Exception as e:  # noqa: BLE001
        await send({"type": "error", "message": str(e)})


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
