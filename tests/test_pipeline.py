"""M5 单元测试：两跳搜索合并 + pipeline 编排。"""

import asyncio
from pathlib import Path

from musicalbili.config import Config
from musicalbili.models import Lyric, SongMeta, VideoDetail, VideoPage, VideoVersion
from musicalbili.services.pipeline import download_song_pipeline
from musicalbili.services.search import search_versions


def _v(bvid: str, title: str, play: int) -> VideoVersion:
    return VideoVersion(
        bvid=bvid, title=title, author="UP", author_mid=1,
        pic="", duration=100, play=play, tid=0, typename="",
    )


class _FakeB:
    def __init__(self, results: dict) -> None:
        self.results = results

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def search_video(self, query: str, limit: int = 10) -> list:
        return self.results.get(query, [])


def test_search_versions_lyric_reverse(monkeypatch):
    direct = [_v("BV1", "消失的下雨天 我好想再淋一遍", 100)]
    lyric = [_v("BV2", "周杰伦 - 七里香", 1000)]
    b = _FakeB({"窗外的麻雀 在电线杆上多嘴": direct, "七里香": lyric})
    monkeypatch.setattr("musicalbili.services.search.BilibiliClient", lambda cfg: b)

    async def fake_titles(cfg, query, top=3):
        return ["七里香"]

    monkeypatch.setattr("musicalbili.services.search._lyric_to_titles", fake_titles)
    cfg = Config()
    hits = asyncio.run(search_versions(cfg, "窗外的麻雀 在电线杆上多嘴"))
    assert len(hits) == 2
    assert hits[0].version.bvid == "BV2" and hits[0].source == "lyric"
    assert hits[1].version.bvid == "BV1" and hits[1].source == "direct"


def test_search_versions_skip_when_title_in_query(monkeypatch):
    direct = [_v("BV1", "周杰伦 - 晴天", 500)]
    b = _FakeB({"周杰伦 晴天": direct})
    monkeypatch.setattr("musicalbili.services.search.BilibiliClient", lambda cfg: b)

    async def fake_titles(cfg, query, top=3):
        return ["晴天"]

    monkeypatch.setattr("musicalbili.services.search._lyric_to_titles", fake_titles)
    cfg = Config()
    hits = asyncio.run(search_versions(cfg, "周杰伦 晴天"))
    assert len(hits) == 1 and hits[0].source == "direct"


def test_search_versions_lookup_off(monkeypatch):
    direct = [_v("BV1", "周杰伦 - 晴天", 500)]
    b = _FakeB({"周杰伦 晴天": direct})
    monkeypatch.setattr("musicalbili.services.search.BilibiliClient", lambda cfg: b)

    async def fake_titles(cfg, query, top=3):
        raise AssertionError("不应触发歌词反查")

    monkeypatch.setattr("musicalbili.services.search._lyric_to_titles", fake_titles)
    cfg = Config()
    cfg.search_lyric_lookup = False
    hits = asyncio.run(search_versions(cfg, "周杰伦 晴天"))
    assert len(hits) == 1 and hits[0].source == "direct"


class _FakeDetail:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def get_detail(self, bvid: str) -> VideoDetail:
        return VideoDetail(bvid=bvid, title="晴天MV", author="UP", author_mid=1, pic="", cid=100, duration=200)

    async def get_pagelist(self, bvid: str) -> list:
        return [VideoPage(cid=100, page=1, part="晴天", duration=200)]


class _FakeDB:
    def __init__(self, path=None) -> None:
        self.added = None

    def already_downloaded(self, bvid, cid):
        return False

    def add(self, **kw) -> None:
        self.added = kw

    def close(self) -> None:
        pass


async def _fake_download(bvid, cid, *, cfg, title, artist, fmt, progress):
    if progress:
        await progress(50, 100)
        await progress(100, 100)
    return Path("downloads/test.m4a")


async def _fake_auto_tag(path, title, providers, cfg, fallback_artist=""):
    meta = SongMeta(source="migu", id=1, name="晴天", artists=["周杰伦"])
    return Path("downloads/周杰伦 - 晴天.m4a"), meta


async def _fake_lyric(cfg, path, meta, title, bvid, cid, force_align, emit):
    l = Lyric(source="lrclib", text="[00:01.00]a", calib_method="synced")
    await emit({"type": "lyric", "lyric": l})
    return l


def test_pipeline_flow(monkeypatch):
    import musicalbili.services.pipeline as pl

    monkeypatch.setattr(pl, "BilibiliClient", lambda cfg: _FakeDetail())
    monkeypatch.setattr(pl, "download_song", _fake_download)
    monkeypatch.setattr(pl, "auto_tag", _fake_auto_tag)
    monkeypatch.setattr(pl, "_attach_lyric", _fake_lyric)
    monkeypatch.setattr(pl, "DownloadDB", _FakeDB)
    cfg = Config()
    events: list[dict] = []

    async def cb(ev: dict) -> None:
        events.append(ev)

    result = asyncio.run(download_song_pipeline(cfg, "BV1", on_event=cb))
    assert result["meta"].name == "晴天"
    assert result["lyric"].calib_method == "synced"
    types = [e["type"] for e in events]
    assert {"info", "progress", "meta", "lyric"} <= set(types)


def test_pipeline_no_tag_no_lyric(monkeypatch):
    import musicalbili.services.pipeline as pl

    monkeypatch.setattr(pl, "BilibiliClient", lambda cfg: _FakeDetail())
    monkeypatch.setattr(pl, "download_song", _fake_download)
    monkeypatch.setattr(pl, "DownloadDB", _FakeDB)

    async def bad_tag(*a, **kw):
        raise AssertionError("不应打标签")

    async def bad_lyric(*a, **kw):
        raise AssertionError("不应配歌词")

    monkeypatch.setattr(pl, "auto_tag", bad_tag)
    monkeypatch.setattr(pl, "_attach_lyric", bad_lyric)
    result = asyncio.run(download_song_pipeline(Config(), "BV1", no_tag=True, no_lyric=True))
    assert result["meta"] is None and result["lyric"] is None
