"""M5 TUI 回归测试（需 [tui] extra；未装则跳过）。"""

import asyncio

import pytest

textual = pytest.importorskip("textual")

from musicalbili.models import VideoVersion
from musicalbili.services.search import SearchHit
from musicalbili.tui import MusicalbiliApp


def _hit(bvid: str, title: str) -> SearchHit:
    return SearchHit(
        version=VideoVersion(
            bvid=bvid, title=title, author="UP", author_mid=1,
            pic="", duration=100, play=1, tid=0, typename="",
        ),
        source="direct",
    )


def test_tui_mount():
    app = MusicalbiliApp()
    asyncio.run(_mount(app))


async def _mount(app):
    async with app.run_test():
        assert app.query_one("Input") is not None
        assert app.query_one("DataTable") is not None
        assert app.query_one("#log") is not None


def test_tui_search_and_select(monkeypatch):
    from musicalbili import tui

    calls: list[str] = []

    async def fake_search(cfg, query):
        return [_hit("BV1", "晴天"), _hit("BV2", "晴天MV")]

    async def fake_pipeline(cfg, bvid, page=1, **kw):
        calls.append(bvid)
        return {"path": "x", "meta": None, "lyric": None, "title": "t", "artist": "a"}

    monkeypatch.setattr(tui, "search_versions", fake_search)
    monkeypatch.setattr(tui, "download_song_pipeline", fake_pipeline)
    asyncio.run(_search_and_select(calls))


async def _search_and_select(calls):
    app = MusicalbiliApp()
    async with app.run_test() as pilot:
        inp = app.query_one("Input")
        inp.value = "晴天"
        await inp.action_submit()
        for _ in range(20):
            await pilot.pause(0.2)
            if app.query_one("DataTable").row_count >= 2:
                break
        table = app.query_one("DataTable")
        table.focus()
        await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause(0.5)
    assert calls == ["BV2"]
