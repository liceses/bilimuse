"""三端覆盖：Web 真实搜索 + WS 下载事件流（需网络，-m e2e 运行）。

用法:
    python -m pytest tests/e2e/test_web_e2e.py -m e2e
"""

import pytest

pytest.importorskip("fastapi")

pytestmark = [pytest.mark.e2e]

from fastapi.testclient import TestClient

from bilimuse import web

# 与 run_testset 相同的下载目标：C01 晴天
_BVID = "BV1d4411N7zD"


def test_web_real_search(e2e_config):
    client = TestClient(web.app)
    r = client.get("/api/search", params={"q": "周杰伦 晴天", "limit": 3})
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 1
    assert data[0]["version"]["bvid"].startswith("BV")


def test_web_doctor_live(e2e_config):
    client = TestClient(web.app)
    body = client.get("/api/doctor").json()
    assert body["python"].startswith("3.")


def test_web_ws_download_live(e2e_config):
    client = TestClient(web.app)
    with client.websocket_connect("/ws/download") as ws:
        ws.send_json({"bvid": _BVID, "page": 1, "format": "m4a", "no_tag": True, "no_lyric": True})
        types: set[str] = set()
        got_result = False
        while True:
            ev = ws.receive_json()
            types.add(ev["type"])
            if ev["type"] == "result":
                got_result = True
                break
            if ev["type"] == "error":
                break
        assert got_result
        assert "progress" in types or "stage" in types
