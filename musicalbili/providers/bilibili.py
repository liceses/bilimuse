"""B 站 API 客户端：Wbi 签名 / 搜索 / view / 分 P / playurl。

风控要点：
- 搜索与播放接口需 Wbi 签名，且要求 cookie 含 buvid3、UA 无敏感子串、Referer 在 .bilibili.com 下。
- 首次调用先 GET 导航接口拿 buvid3 cookie 与 wbi keys。
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
import urllib.parse
from typing import Self

import httpx

from ..config import Config
from ..models import AudioStream, PlayInfo, VideoDetail, VideoPage, VideoVersion

API = "https://api.bilibili.com"
_KEYS_RE = re.compile(r"^[\w]+$")


class BilibiliError(RuntimeError):
    pass


class BilibiliClient:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config.load()
        cookies: dict[str, str] = {}
        if self.config.sessdata:
            cookies["SESSDATA"] = self.config.sessdata
        if self.config.buvid3:
            cookies["buvid3"] = self.config.buvid3
        self.client = httpx.AsyncClient(
            headers={"User-Agent": self.config.ua, "Referer": "https://www.bilibili.com/"},
            cookies=cookies,
            follow_redirects=True,
            timeout=httpx.Timeout(15.0, connect=10.0),
            trust_env=False,
            proxy=self.config.proxy or None,
        )
        self._mixin_key: str | None = None
        self._session_ready = False

    async def _request(self, url: str, **kwargs: object) -> httpx.Response:
        """带网络抖动重试的 GET（本机 DNS 偶发 getaddrinfo 失败）。"""
        for attempt in range(3):
            try:
                return await self.client.get(url, **kwargs)
            except httpx.ConnectError:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))
        raise BilibiliError("unreachable")

    async def _ensure_session(self) -> None:
        """先访问首页拿 buvid3 cookie，否则接口被 412 拦截。"""
        if self._session_ready:
            return
        r = await self._request("https://www.bilibili.com/")
        r.raise_for_status()
        self._session_ready = True

    async def _wbi_mixin_key(self) -> str:
        """从导航接口拿 img_key + sub_key 并取前 32 位。"""
        if self._mixin_key:
            return self._mixin_key
        await self._ensure_session()
        r = await self._request(f"{API}/x/web-interface/nav")
        r.raise_for_status()
        data = r.json()
        wbi_img = data.get("data", {}).get("wbi_img") or {}
        img = (wbi_img.get("img_url") or "").rsplit("/", 1)[-1].split(".")[0]
        sub = (wbi_img.get("sub_url") or "").rsplit("/", 1)[-1].split(".")[0]
        if not img or not sub:
            raise BilibiliError("获取 wbi keys 失败，可能被风控")
        self._mixin_key = (img + sub)[:32]
        return self._mixin_key

    async def _wbi_sign(self, params: dict) -> dict:
        """按 Wbi 规范签名：过滤非法键、排序、加 wts、md5。"""
        params = {k: str(v) for k, v in params.items() if _KEYS_RE.match(k)}
        params["wts"] = str(int(time.time()))
        query = urllib.parse.urlencode(sorted(params.items()), quote_via=urllib.parse.quote_plus)
        mixin_key = await self._wbi_mixin_key()
        params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
        return params

    async def _get(self, path: str, params: dict, wbi: bool = False) -> dict:
        url = f"{API}/{path.lstrip('/')}"
        if wbi:
            params = await self._wbi_sign(params)
        for attempt in (0, 1):
            r = await self._request(url, params=params)
            data = r.json()
            if data.get("code") == -412 and attempt == 0:
                self._mixin_key = None
                if wbi:
                    params = await self._wbi_sign(params)
                continue
            if data.get("code") != 0:
                raise BilibiliError(f"{path} 返回 code={data.get('code')}: {data.get('message')}")
            return data.get("data") or {}
        raise BilibiliError(f"{path} 持续被风控(-412)")

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def search_video(self, keyword: str, order: str = "click", limit: int = 20) -> list[VideoVersion]:
        """搜索视频。order 支持 totalrank/click/pubdate/dm。

        用旧版搜索接口（wbi 版在本环境被风控，仅返回 v_voucher）。
        """
        await self._ensure_session()
        data = await self._get(
            "x/web-interface/search/type",
            {"search_type": "video", "keyword": keyword, "order": order, "page_size": limit},
        )
        versions: list[VideoVersion] = []
        for item in data.get("result") or []:
            bvid = item.get("bvid")
            if not bvid:
                continue
            versions.append(
                VideoVersion(
                    bvid=bvid,
                    title=_strip_html(item.get("title", "")),
                    author=item.get("author", ""),
                    author_mid=item.get("mid") or 0,
                    pic=item.get("pic", ""),
                    duration=_parse_duration(item.get("duration", "")),
                    play=item.get("play") or 0,
                    tid=item.get("tid") or 0,
                    typename=item.get("typename", ""),
                )
            )
        return versions

    async def get_detail(self, bvid: str) -> VideoDetail:
        data = await self._get("x/web-interface/view", {"bvid": bvid})
        owner = data.get("owner") or {}
        pages = [VideoPage(**p) for p in (data.get("pages") or [])]
        return VideoDetail(
            bvid=bvid,
            title=data.get("title", ""),
            author=owner.get("name", ""),
            author_mid=owner.get("mid") or 0,
            pic=data.get("pic", ""),
            cid=data.get("cid") or 0,
            duration=data.get("duration") or 0,
            pages=pages,
        )

    async def get_pagelist(self, bvid: str) -> list[VideoPage]:
        data = await self._get("x/player/pagelist", {"bvid": bvid})
        return [VideoPage(**p) for p in (data or [])]

    async def get_play_info(self, bvid: str, cid: int) -> PlayInfo:
        data = await self._get(
            "x/player/wbi/playurl",
            {"fnval": 4048, "fourk": 1, "bvid": bvid, "cid": cid},
            wbi=True,
        )
        dash = data.get("dash") or {}
        audio = [
            AudioStream(
                id=item.get("id") or 0,
                base_url=_abs(item.get("baseUrl") or item.get("base_url") or ""),
                bandwidth=item.get("bandwidth") or 0,
                codecs=item.get("codecs", ""),
                mime_type=item.get("mimeType") or item.get("mime_type", ""),
            )
            for item in dash.get("audio") or []
        ]
        flac = dash.get("flac")
        dolby = dash.get("dolby") or {}
        return PlayInfo(
            dash_audio=audio,
            flac=AudioStream(id=30251, base_url=_abs(flac["audio"]["baseUrl"])) if flac and flac.get("audio") else None,
            dolby=AudioStream(id=30250, base_url=_abs(dolby["audio"]["baseUrl"])) if dolby.get("audio") else None,
            video_title=data.get("title", ""),
        )

    def pick_audio(self, play: PlayInfo, prefer_flac: bool = False) -> AudioStream:
        """按优先级选音轨：FLAC → Dolby → bandwidth 最高 AAC。"""
        if prefer_flac and play.flac:
            return play.flac
        if play.dolby:
            return play.dolby
        if play.dash_audio:
            return max(play.dash_audio, key=lambda s: s.bandwidth)
        raise BilibiliError("无可用的音频流")


def _abs(url: str) -> str:
    return f"https:{url}" if url.startswith("//") else url


def _strip_html(s: str) -> str:
    """剥离搜索标题里的 <em class="keyword"> 高亮标签。"""
    return re.sub(r"<[^>]+>", "", s)


def _parse_duration(s: str) -> int:
    """'3:37' / '1:02:33' → 秒。"""
    parts = [int(x) for x in str(s).split(":")]
    total = 0
    for p in parts:
        total = total * 60 + p
    return total
