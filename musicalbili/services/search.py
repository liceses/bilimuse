"""搜索服务：两路合并（B站直接搜 + 网易云歌词反查→B站）。"""

from __future__ import annotations

from pydantic import BaseModel

from ..config import Config
from ..models import VideoVersion
from ..providers.bilibili import BilibiliClient


class SearchHit(BaseModel):
    version: VideoVersion
    source: str = "direct"  # direct=直接搜索 / lyric=歌词反查


async def _lyric_to_titles(cfg: Config, query: str, top: int = 3) -> list[str]:
    """网易云按歌词正文反查歌名（实测支持歌词片段），返回去重保序的歌名列表。"""
    from ..providers.meta import NeteaseMeta

    async with NeteaseMeta(cfg) as netease:
        songs = await netease.search(query, limit=top)
    titles: list[str] = []
    seen: set[str] = set()
    for s in songs:
        if s.name and s.name not in seen:
            seen.add(s.name)
            titles.append(s.name)
    return titles


async def search_versions(cfg: Config, query: str, limit: int = 10) -> list[SearchHit]:
    """两路搜索合并去重，按播放量排序。

    路 A：B站 直接搜 query（歌名/歌手/标题含歌词）。
    路 B：网易云按歌词正文反查歌名 → 前 3 个歌名各搜一次 B站（标注 lyric）。
    """
    hits: list[SearchHit] = []
    seen: set[str] = set()
    async with BilibiliClient(cfg) as b:
        for v in await b.search_video(query, limit=limit):
            seen.add(v.bvid)
            hits.append(SearchHit(version=v, source="direct"))
        if cfg.search_lyric_lookup:
            for title in await _lyric_to_titles(cfg, query):
                if title and title.lower() in query.lower():
                    continue  # 歌名已含在 query 中，B站直接搜已覆盖
                for v in await b.search_video(title, limit=limit):
                    if v.bvid not in seen:
                        seen.add(v.bvid)
                        hits.append(SearchHit(version=v, source="lyric"))
    hits.sort(key=lambda h: h.version.play, reverse=True)
    return hits
