"""M6 Web 测试（需 [web] extra；未装则跳过）。"""

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from musicalbili.models import VideoVersion
from musicalbili.services.search import SearchHit


def _hit(bvid: str, title: str) -> SearchHit:
    return SearchHit(
        version=VideoVersion(
            bvid=bvid, title=title, author="UP", author_mid=1,
            pic="", duration=100, play=1, tid=0, typename="",
        ),
        source="direct",
    )


def test_index():
    from musicalbili import web

    client = TestClient(web.app)
    r = client.get("/")
    assert r.status_code == 200 and "MusicalBILI" in r.text


def test_api_search(monkeypatch):
    from musicalbili import web

    async def fake_search(cfg, q, limit=10):
        return [_hit("BV1", "晴天")]

    monkeypatch.setattr(web, "search_versions", fake_search)
    client = TestClient(web.app)
    r = client.get("/api/search", params={"q": "晴天"})
    assert r.status_code == 200
    data = r.json()
    assert data[0]["version"]["bvid"] == "BV1"
    assert data[0]["source"] == "direct"


def test_api_doctor():
    from musicalbili import web

    client = TestClient(web.app)
    r = client.get("/api/doctor")
    assert r.status_code == 200
    body = r.json()
    assert "whisper" in body and "models" in body


def test_ws_download(monkeypatch):
    from musicalbili import web

    async def fake_pipeline(cfg, bvid, page=1, on_event=None, **kw):
        await on_event({"type": "stage", "stage": "download", "text": "下载中"})
        return {"path": "x.m4a", "meta": None, "lyric": None, "title": "t", "artist": "a"}

    monkeypatch.setattr(web, "download_song_pipeline", fake_pipeline)
    client = TestClient(web.app)
    with client.websocket_connect("/ws/download") as ws:
        ws.send_json({"bvid": "BV1"})
        ev = ws.receive_json()
        assert ev["type"] == "stage"
        ev2 = ws.receive_json()
        assert ev2["type"] == "result"
        assert ev2["result"]["path"] == "x.m4a"


def test_ws_download_error(monkeypatch):
    from musicalbili import web

    async def bad_pipeline(cfg, bvid, page=1, on_event=None, **kw):
        raise RuntimeError("去重跳过")

    monkeypatch.setattr(web, "download_song_pipeline", bad_pipeline)
    client = TestClient(web.app)
    with client.websocket_connect("/ws/download") as ws:
        ws.send_json({"bvid": "BV1"})
        ev = ws.receive_json()
        assert ev["type"] == "error"
        assert "去重" in ev["message"]
