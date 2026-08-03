"""M3 单元测试：标题清洗、匹配、多源排序、mutagen 打标签回读。"""

import asyncio

from mutagen.id3 import ID3
from mutagen.mp4 import MP4

from musicalbili.models import SongMeta
from musicalbili.services.tagger import (
    clean_title,
    pick_best,
    search_metadata,
    split_query,
    tag_file,
)


def test_clean_title():
    assert clean_title("【4K修复】周杰伦 - 晴天MV 2160P修复版") == "周杰伦 - 晴天"
    assert clean_title("晴天 (MV)") == "晴天"
    assert clean_title("“消失的下雨天，我好想再淋一遍”") == "“消失的下雨天，我好想再淋一遍”"


def test_pick_best():
    songs = [
        SongMeta(id=1, name="晴天", artists=["周杰伦"], duration_ms=269000),
        SongMeta(id=2, name="晴天 - 伴奏", artists=["周杰伦"]),
        SongMeta(id=3, name="一路向北", artists=["周杰伦"]),
    ]
    assert pick_best(songs, "周杰伦 晴天").id == 1
    assert pick_best(songs, "一路向北").id == 3
    assert pick_best(songs, "完全无关的歌名啊") is None


def test_split_query():
    assert split_query("周杰伦 - 晴天") == ("周杰伦", "晴天")
    assert split_query("晴天") == ("", "晴天")
    assert split_query("【4K修复】周杰伦 - 晴天MV 2160P修复版") == ("周杰伦", "晴天")


def test_pick_best_artist_penalty():
    netease_fakes = [SongMeta(source="netease", id=1, name="晴天", artists=["周杰伦-", "A-LNK"])]
    migu_real = [SongMeta(source="migu", id="x", name="晴天", artists=["周杰伦"])]
    assert pick_best(netease_fakes, "周杰伦 - 晴天").id == 1
    assert pick_best(migu_real, "周杰伦 - 晴天").id == "x"


class _FakeProv:
    name = "fake"

    def __init__(self, name: str, songs: list) -> None:
        self.name = name
        self.songs = songs

    async def search(self, query: str) -> list:
        return self.songs


def test_search_metadata_order():
    migu = _FakeProv("migu", [SongMeta(source="migu", id="m1", name="晴天", artists=["周杰伦"])])
    netease = _FakeProv("netease", [SongMeta(source="netease", id=1, name="晴天", artists=["周杰伦-", "A-LNK"])])
    prov, song = asyncio.run(search_metadata("周杰伦 - 晴天", [migu, netease]))
    assert prov is migu and song.id == "m1"


def test_search_metadata_fallback():
    migu = _FakeProv("migu", [SongMeta(source="migu", id="m1", name="随便", artists=["某人"])])
    netease = _FakeProv("netease", [SongMeta(source="netease", id=2, name="晴天", artists=["周杰伦"])])
    prov, song = asyncio.run(search_metadata("周杰伦 - 晴天", [migu, netease]))
    assert prov.name == "netease" and song.id == 2


def test_tag_m4a_roundtrip(tmp_path):
    p = tmp_path / "t.m4a"
    ftyp = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41"
    moov = b"\x00\x00\x00\x08moov"
    p.write_bytes(ftyp + moov)
    meta = SongMeta(id=1, name="晴天", artists=["周杰伦"], album="叶惠美")
    tag_file(p, meta)
    a2 = MP4(p)
    assert a2["\xa9nam"] == ["晴天"]
    assert a2["\xa9ART"] == ["周杰伦"]
    assert a2["\xa9alb"] == ["叶惠美"]


def test_tag_mp3_roundtrip(tmp_path):
    p = tmp_path / "t.mp3"
    p.write_bytes(b"")
    meta = SongMeta(id=1, name="晴天", artists=["周杰伦"], album="叶惠美")
    tag_file(p, meta)
    tags = ID3(p)
    assert str(tags["TIT2"]) == "晴天"
    assert str(tags["TPE1"]) == "周杰伦"
    assert str(tags["TALB"]) == "叶惠美"
