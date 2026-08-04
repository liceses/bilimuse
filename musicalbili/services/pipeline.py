"""一键闭环编排：搜索→选版本→下载→打标签→配歌词→校准→入库。

通过 on_event 回调向 UI（CLI/Textual/Web）推送结构化事件：
- {"type":"info","title","author"}
- {"type":"progress","pct","done","total"}
- {"type":"message","text"}
- {"type":"meta","meta": SongMeta}
- {"type":"lyric","lyric": Lyric}
- {"type":"warning","text"}
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from ..config import Config
from ..db import DownloadDB
from ..models import Lyric, SongMeta
from ..providers.bilibili import BilibiliClient
from ..providers.meta import MiguMeta, NeteaseMeta
from .aligner import align_available, calibrate
from .download import download_song
from .lyric import fetch_lyrics, pair_translation, placeholder_lyric, reattach_translation
from .tagger import auto_tag, tag_file

EventCb = Callable[[dict], Awaitable[None]] | None


async def _attach_lyric(
    cfg: Config,
    path: Path,
    meta: SongMeta | None,
    title: str,
    bvid: str,
    cid: int,
    force_align: bool,
    emit: Callable[[dict], Awaitable[None]],
) -> Lyric:
    if force_align and not align_available():
        await emit({"type": "warning", "text": "--align 需要 lyric-align，请装 `pip install -e '.[align]'`"})
    await emit({"type": "message", "text": "获取歌词..."})
    lyric = await fetch_lyrics(cfg, meta, title, bvid, cid)
    sidecar = path.with_suffix(".lrc")
    if lyric is None:
        lyric = placeholder_lyric()
        sidecar.write_text(lyric.text, encoding="utf-8")
        await emit({"type": "warning", "text": "未找到歌词，已生成纯音乐占位 .lrc"})
        return lyric
    pairs = pair_translation(lyric.text, lyric.tlyric)
    async def status(text: str) -> None:
        await emit({"type": "message", "text": text})

    lyric = await calibrate(
        path, lyric, cfg, force_align,
        meta_language=meta.language if meta else "",
        on_status=status,
    )
    final_text = reattach_translation(lyric.text, pairs) if lyric.source != "placeholder" else lyric.text
    sidecar.write_text(final_text, encoding="utf-8")
    await emit({"type": "lyric", "lyric": lyric})
    if meta:
        tag_file(path, meta, lyrics=final_text)
    if lyric.warning:
        await emit({"type": "warning", "text": lyric.warning})
    return lyric


async def download_song_pipeline(
    cfg: Config,
    bvid: str,
    page: int = 1,
    *,
    on_event: EventCb = None,
    no_tag: bool = False,
    no_lyric: bool = False,
    force_align: bool = False,
) -> dict:
    """完整闭环：详情→去重→下载→打标签→配歌词→校准→入库。返回 {path, meta, lyric, title, artist}。"""
    async def emit(ev: dict) -> None:
        if on_event:
            await on_event(ev)

    db = DownloadDB()
    try:
        async with BilibiliClient(cfg) as client:
            detail = await client.get_detail(bvid)
            pages = detail.pages or await client.get_pagelist(bvid)
            if pages:
                selected = pages[page - 1]
                cid = selected.cid
                title = selected.part if len(pages) > 1 else detail.title
                video_dur = float(selected.duration) if selected.duration else None
            else:
                cid = detail.cid
                title = detail.title
                video_dur = float(detail.duration) if detail.duration else None

        if db.already_downloaded(bvid, cid):
            raise RuntimeError(f"{bvid} 的 P{page}(cid={cid}) 已下载过，跳过（去重）")

        await emit({"type": "info", "title": title, "author": detail.author})
        await emit({"type": "stage", "stage": "download", "text": "下载中..."})
        state = {"last": -1}

        async def progress(done: int, total: int) -> None:
            if total <= 0:
                return
            pct = done * 100 // total
            if pct != state["last"]:
                state["last"] = pct
                await emit({"type": "progress", "pct": pct, "done": done, "total": total})

        path = await download_song(
            bvid, cid, cfg=cfg, title=title, artist=detail.author, fmt=cfg.format, progress=progress
        )

        meta: SongMeta | None = None
        if not no_tag:
            await emit({"type": "stage", "stage": "tag", "text": "反查元数据并打标签..."})
            async with MiguMeta(cfg) as migu, NeteaseMeta(cfg) as netease:
                new_path, meta = await auto_tag(
                    path, title, [migu, netease], cfg, fallback_artist=detail.author, duration=video_dur
                )
            if meta:
                path = new_path
                await emit({"type": "meta", "meta": meta})
            else:
                await emit({"type": "message", "text": "未匹配到曲目，保留原始命名"})

        lyric: Lyric | None = None
        if not no_lyric:
            await emit({"type": "stage", "stage": "lyric", "text": "获取歌词..."})
            lyric = await _attach_lyric(cfg, path, meta, title, bvid, cid, force_align, emit)

        await emit({"type": "stage", "stage": "done", "text": "完成"})
        db.add(
            bvid=bvid,
            cid=cid,
            title=meta.name if meta else title,
            artist=meta.artist_str if meta else detail.author,
            format=path.suffix.lstrip("."),
            file_path=str(path),
        )
        return {"path": path, "meta": meta, "lyric": lyric, "title": title, "artist": detail.author}
    finally:
        db.close()
