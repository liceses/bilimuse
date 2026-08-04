"""登录与 API 加固 单元测试。"""

import asyncio
import base64

from bilimuse.config import Config
from bilimuse.providers.bilibili import BilibiliClient
from bilimuse.providers.meta import _weapi_params
from bilimuse.services.auth import _extract_cookie


def test_weapi_params():
    p = _weapi_params({"s": "晴天", "type": 1})
    assert set(p) == {"params", "encSecKey"}
    assert len(p["encSecKey"]) == 256
    assert all(ch in "0123456789abcdef" for ch in p["encSecKey"])
    raw = base64.b64decode(p["params"])
    assert len(raw) % 16 == 0


def test_extract_cookie():
    h = "SESSDATA=abc%2B123; Path=/; HttpOnly; bili_jct=xyz; Path=/"
    assert _extract_cookie(h, "SESSDATA") == "abc%2B123"
    assert _extract_cookie(h, "bili_jct") == "xyz"
    assert _extract_cookie(h, "DedeUserID") == ""


def _client(cfg: Config, responses: dict) -> BilibiliClient:
    async def fake_get(path: str, params: dict, wbi: bool = False) -> dict:
        return responses[path]

    async def noop() -> None:
        return None

    async def sign(params: dict) -> dict:
        return params

    c = BilibiliClient(cfg)
    c._get = fake_get
    c._ensure_session = noop
    c._wbi_sign = sign
    return c


def test_search_fallback_to_legacy():
    cfg = Config()
    cfg.sessdata = "x"
    legacy = {
        "result": [
            {"bvid": "BV1", "title": "晴天", "author": "周", "mid": 1,
             "pic": "", "duration": "3:37", "play": 10, "tid": 3, "typename": "MV"}
        ]
    }
    responses = {
        "x/web-interface/wbi/search/type": {"v_voucher": "voucher"},
        "x/web-interface/search/type": legacy,
    }
    c = _client(cfg, responses)
    v = asyncio.run(c.search_video("晴天"))
    assert len(v) == 1 and v[0].bvid == "BV1" and v[0].duration == 217


def test_search_uses_wbi_when_results():
    cfg = Config()
    cfg.sessdata = "x"
    responses = {
        "x/web-interface/wbi/search/type": {
            "result": [{"bvid": "BV9", "title": "t", "author": "a", "mid": 0,
                        "pic": "", "duration": "1:00", "play": 0, "tid": 0, "typename": ""}]
        }
    }
    c = _client(cfg, responses)
    v = asyncio.run(c.search_video("t"))
    assert len(v) == 1 and v[0].bvid == "BV9"
