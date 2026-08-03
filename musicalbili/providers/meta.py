"""音乐元数据反查（多源：咪咕优先 → 网易云兜底）。

背景：周杰伦等歌手版权已离开网易云，其搜索只剩关键词堆砌的翻唱；咪咕为正规曲库（含周杰伦），故优先。
"""

from __future__ import annotations

import asyncio
from typing import ClassVar, Self

import httpx

from ..config import Config
from ..models import SongMeta
from ..services.download import find_ffmpeg
from .bilibili import _strip_html

NETEASE_API = "https://music.163.com"
MIGU_API = "https://pd.musicapp.migu.cn/MIGUM2.0/v1.0"


class _BaseMeta:
    name = "base"

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.load()
        self.client = httpx.AsyncClient(
            headers={"User-Agent": self.config.ua, "Referer": self.referer},
            follow_redirects=True,
            timeout=httpx.Timeout(20.0, connect=10.0),
            trust_env=False,
            proxy=self.config.proxy or None,
        )

    referer = "https://music.163.com/"

    async def search(self, query: str, limit: int = 10) -> list[SongMeta]:
        raise NotImplementedError

    async def fetch_cover_bytes(self, song: SongMeta) -> bytes | None:
        raise NotImplementedError

    async def _download_image(self, url: str) -> bytes | None:
        if not url:
            return None
        r = await self.client.get(url)
        return r.content if r.status_code == 200 else None

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class NeteaseMeta(_BaseMeta):
    """网易云（明文旧版接口，免逆向签名）。版权有限，用作兜底。"""

    name = "netease"

    async def search(self, query: str, limit: int = 10) -> list[SongMeta]:
        r = await self.client.get(
            f"{NETEASE_API}/api/search/get",
            params={"s": query, "type": 1, "offset": 0, "limit": limit},
        )
        r.raise_for_status()
        return self._parse_songs(r.json())

    def _parse_songs(self, data: dict) -> list[SongMeta]:
        songs: list[SongMeta] = []
        for s in (data.get("result") or {}).get("songs") or []:
            album = s.get("album") or {}
            songs.append(
                SongMeta(
                    source=self.name,
                    id=s.get("id") or 0,
                    name=_strip_html(s.get("name") or ""),
                    artists=[a.get("name", "") for a in (s.get("artists") or []) if a.get("name")],
                    album=album.get("name") or "",
                    duration_ms=s.get("duration") or 0,
                    cover=album.get("picUrl") or "",
                )
            )
        return songs

    async def fetch_cover_bytes(self, song: SongMeta) -> bytes | None:
        url = song.cover
        if not url:
            url = await self.get_cover_url(song.id)
        return await self._download_image(url)

    async def get_cover_url(self, song_id: int) -> str:
        r = await self.client.get(
            f"{NETEASE_API}/api/song/detail", params={"id": song_id, "ids": f"[{song_id}]"}
        )
        r.raise_for_status()
        for s in r.json().get("songs") or []:
            al = s.get("album") or {}
            if al.get("picUrl"):
                return al["picUrl"]
        return ""


class MiguMeta(_BaseMeta):
    """咪咕音乐（MIGUM2.0 明文接口，曲库含周杰伦）。"""

    name = "migu"
    referer = "https://music.migu.cn/"
    _search_params: ClassVar[dict[str, str]] = {
        "ua": "Android_migu",
        "version": "5.0.1",
        "searchSwitch": "{song:1,songlist:0,album:0,singer:0,lyricSong:0,radioSong:0,user:0,mv:0,quality:0}",
    }

    async def search(self, query: str, limit: int = 10) -> list[SongMeta]:
        params = {**self._search_params, "text": query, "pageNo": 1, "pageSize": limit}
        r = await self.client.get(f"{MIGU_API}/content/search_all.do", params=params)
        r.raise_for_status()
        data = r.json()
        if data.get("code") != "000000":
            return []
        songs: list[SongMeta] = []
        for s in (data.get("songResultData") or {}).get("result") or []:
            if not s.get("name"):
                continue
            songs.append(
                SongMeta(
                    source=self.name,
                    id=str(s.get("contentId") or s.get("id") or ""),
                    name=s.get("name") or "",
                    artists=[x.get("name", "") for x in (s.get("singers") or []) if x.get("name")],
                    album=(s.get("albums") or [{}])[0].get("name", "") or "",
                    cover=_cover_url(s),
                )
            )
        return songs

    async def fetch_cover_bytes(self, song: SongMeta) -> bytes | None:
        """封面是 webp，用内置 ffmpeg 转 jpeg；无 ffmpeg 则跳过封面。"""
        data = await self._download_image(song.cover)
        if not data:
            return None
        ffmpeg = find_ffmpeg(self.config)
        if not ffmpeg:
            return None
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-y", "-loglevel", "error", "-i", "-", "-frames:v", "1",
            "-f", "image2pipe", "-vcodec", "mjpeg", "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate(data)
        return out if proc.returncode == 0 and out else None


def _cover_url(song: dict) -> str:
    """选 imgItems 里尺寸最大的一张（03 > 02 > 01）。"""
    imgs = song.get("imgItems") or []
    best = ""
    for item in imgs:
        url = item.get("img") or ""
        size = item.get("imgSizeType") or "00"
        if size >= "03" or not best:
            best = url
    return best
