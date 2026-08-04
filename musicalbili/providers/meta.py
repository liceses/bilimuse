"""音乐元数据反查（多源：咪咕优先 → 网易云兜底）。

背景：周杰伦等歌手版权已离开网易云，其搜索只剩关键词堆砌的翻唱；咪咕为正规曲库（含周杰伦），故优先。
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import secrets
from typing import ClassVar, Self

import httpx

from ..config import Config
from ..models import SongMeta
from ..services.download import find_ffmpeg
from .bilibili import _strip_html

NETEASE_API = "https://music.163.com"
MIGU_API = "https://pd.musicapp.migu.cn/MIGUM2.0/v1.0"

# weapi 常量（公开的固定参数，来自社区逆向资料）
_W_NONCE = "0CoJUm6Qyw8W8jud"
_W_PUBKEY = "010001"
_W_MODULUS = (
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725152b3ab17a876aea8a5aa76d2e4"
    "17629ec4ee341f56135fccf695280104e0312ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575"
    "cce10b424d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7"
)
_W_IV = b"0102030405060708"
_W_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _aes_encrypt(text: str, key: str) -> str:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    pad = 16 - len(text) % 16
    text += chr(pad) * pad
    enc = Cipher(algorithms.AES(key.encode()), modes.CBC(_W_IV)).encryptor()
    return base64.b64encode(enc.update(text.encode("utf-8")) + enc.finalize()).decode()


def _rsa_encrypt(text: str) -> str:
    rev = text[::-1]
    num = int(binascii.hexlify(rev.encode("utf-8")), 16)
    return format(pow(num, int(_W_PUBKEY, 16), int(_W_MODULUS, 16)), "x").zfill(256)


def _weapi_params(payload: dict) -> dict:
    """生成网易云 weapi 请求参数（params + encSecKey）。"""
    sec_key = "".join(secrets.choice(_W_CHARS) for _ in range(16))
    body = json.dumps(payload, separators=(",", ":"))
    params = _aes_encrypt(_aes_encrypt(body, _W_NONCE), sec_key)
    return {"params": params, "encSecKey": _rsa_encrypt(sec_key)}


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
    """网易云：明文旧版快速路径 + weapi 官方主链路兜底。

    weapi 为网页端正在用的接口，长期稳定；明文旧版随时可能下线，故作主备切换。
    """

    name = "netease"

    async def search(self, query: str, limit: int = 10) -> list[SongMeta]:
        try:
            songs = await self._search_legacy(query, limit)
            if songs:
                return songs
        except Exception:  # noqa: BLE001, S110 - 旧版失效自动降级 weapi
            pass
        return await self._search_weapi(query, limit)

    async def _search_legacy(self, query: str, limit: int) -> list[SongMeta]:
        r = await self.client.get(
            f"{NETEASE_API}/api/search/get",
            params={"s": query, "type": 1, "offset": 0, "limit": limit},
        )
        r.raise_for_status()
        return self._parse_songs(r.json())

    async def _search_weapi(self, query: str, limit: int) -> list[SongMeta]:
        payload = {"s": query, "type": 1, "limit": limit, "offset": 0, "csrf_token": ""}
        r = await self.client.post(
            f"{NETEASE_API}/weapi/search/get/web", data=_weapi_params(payload)
        )
        r.raise_for_status()
        return self._parse_songs(r.json())

    def _parse_songs(self, data: dict) -> list[SongMeta]:
        songs: list[SongMeta] = []
        for s in (data.get("result") or {}).get("songs") or []:
            album = s.get("album") or s.get("al") or {}
            songs.append(
                SongMeta(
                    source=self.name,
                    id=s.get("id") or 0,
                    name=_strip_html(s.get("name") or ""),
                    artists=[a.get("name", "") for a in (s.get("artists") or s.get("ar") or []) if a.get("name")],
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

    async def get_lyric(self, song_id: int) -> tuple[str, str]:
        """weapi 取歌词，返回 (lrc, tlyric)。"""
        payload = {"id": song_id, "lv": -1, "kv": -1, "tv": -1, "csrf_token": ""}
        r = await self.client.post(f"{NETEASE_API}/weapi/song/lyric", data=_weapi_params(payload))
        r.raise_for_status()
        j = r.json()
        return (j.get("lrc") or {}).get("lyric") or "", (j.get("tlyric") or {}).get("lyric") or ""

    async def get_cover_url(self, song_id: int) -> str:
        try:
            url = await self._cover_legacy(song_id)
            if url:
                return url
        except Exception:  # noqa: BLE001, S110 - 旧版失效自动降级 weapi
            pass
        return await self._cover_weapi(song_id)

    async def _cover_legacy(self, song_id: int) -> str:
        r = await self.client.get(
            f"{NETEASE_API}/api/song/detail", params={"id": song_id, "ids": f"[{song_id}]"}
        )
        r.raise_for_status()
        return self._pic_from_songs(r.json())

    async def _cover_weapi(self, song_id: int) -> str:
        payload = {"c": f'[{{"id": {song_id}}}]', "csrf_token": ""}
        r = await self.client.post(f"{NETEASE_API}/weapi/v3/song/detail", data=_weapi_params(payload))
        r.raise_for_status()
        return self._pic_from_songs(r.json())

    @staticmethod
    def _pic_from_songs(data: dict) -> str:
        """weapi v3 用 al/ar 键，旧接口用 album/artists 键，兼容两者。"""
        for s in (data.get("songs") or []):
            al = s.get("album") or s.get("al") or {}
            if al.get("picUrl"):
                return al["picUrl"]
        return ""


_LANG_TAGS = {"日语": "ja", "国语": "zh", "英语": "en", "韩语": "ko", "粤语": "yue", "泰语": "th"}


def _lang_from_tags(tags: list) -> str:
    for tag in tags or []:
        if tag in _LANG_TAGS:
            return _LANG_TAGS[tag]
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
                    language=_lang_from_tags(s.get("tags")),
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
        try:
            out, _ = await proc.communicate(data)
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
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
