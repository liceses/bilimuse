"""M4 单元测试：LRC 解析/渲染/清理/翻译合并 + 快速校准。"""

import asyncio

import musicalbili.services.lyric as lym
from musicalbili.config import Config
from musicalbili.models import Lyric, SongMeta
from musicalbili.services.aligner import _apply_alignment, _linear_fit, _robust_fit, calibrate_quick
from musicalbili.services.lyric import (
    clean_netease,
    detect_lyric_language,
    merge_translation,
    pair_translation,
    parse_lrc,
    plain_lines,
    reattach_translation,
    render_lrc,
)


def test_parse_lrc_basic():
    text = "[00:01.50]第一句\n[00:03.00]第二句\n"
    assert parse_lrc(text) == [(1.5, "第一句"), (3.0, "第二句")]


def test_parse_lrc_offset_and_multi():
    text = "[offset:+500]\n[00:01.00][00:05.00]副歌\n"
    lines = parse_lrc(text)
    assert lines == [(1.5, "副歌"), (5.5, "副歌")]


def test_render_roundtrip():
    lines = [(1.5, "第一句"), (61.05, "第二句")]
    out = render_lrc(lines)
    assert parse_lrc(out) == lines
    assert "[01:01.05]第二句" in out


def test_clean_netease_header():
    text = "[00:00.00]作词 : 周杰伦\n[00:01.00]作曲 : 周杰伦\n[00:15.54]如果那两个字没有颤抖\n"
    cleaned = clean_netease(text)
    assert "作词" not in cleaned
    assert "如果那两个字" in cleaned


def test_clean_netease_by_line():
    text = "[by:我喜欢去尸体超市]\n[00:20.54]第一次去卢浮宫时\n[offset:+500]\n"
    cleaned = clean_netease(text)
    assert "by:" not in cleaned
    assert "第一次去卢浮宫时" in cleaned
    assert "offset" in cleaned


def test_merge_translation():
    orig = "[00:01.00]Hello\n"
    trans = "[00:01.00]你好\n"
    merged = merge_translation(orig, trans)
    assert "Hello" in merged and "你好" in merged
    assert merged.index("你好") > merged.index("Hello")
    assert merge_translation(orig, "") == orig


def test_plain_lines():
    assert plain_lines("[00:01.00]a\n[00:02.00]b\n") == "a\nb"


def test_calibrate_quick_synced():
    text = "[00:01.00]a\n[00:04.00]b\n"
    out, method, synced = calibrate_quick(text, 4.5)
    assert synced and method == "synced" and out == text


def test_calibrate_quick_scale():
    text = "[00:01.00]a\n[00:10.00]b\n"
    out, method, synced = calibrate_quick(text, 20.0)
    assert not synced and method == "scale"
    lines = parse_lrc(out)
    assert round(lines[-1][0], 1) == 20.0


def test_detect_language():
    assert detect_lyric_language("[00:01.00]初めてのルーブルは") == "ja"
    assert detect_lyric_language("[00:01.00]窗外的麻雀 在電線桿上多嘴") == "zh"
    assert detect_lyric_language("[00:01.00]안녕하세요 반가워요") == "ko"
    assert detect_lyric_language("[00:01.00]Привет как дела") == "ru"
    assert detect_lyric_language("[00:01.00]Can you give me one last kiss oh oh") == "en"
    assert detect_lyric_language("[00:01.00]纯音乐，请欣赏") == "zh"


def test_linear_fit_offset():
    a, b = _linear_fit([(10, 18), (20, 28), (30, 38), (40, 48)])
    assert abs(a - 1.0) < 1e-6 and abs(b - 8.0) < 1e-6


def test_linear_fit_scale():
    a, b = _linear_fit([(10, 20), (20, 40), (30, 60)])
    assert abs(a - 2.0) < 1e-6 and abs(b - 0.0) < 1e-6


def test_linear_fit_degenerate():
    a, b = _linear_fit([(10, 13), (10, 15)])
    assert a == 1.0 and abs(b - 4.0) < 1e-6


def test_robust_fit_pure_shift_with_outlier():
    points = [(10, 18), (20, 28), (30, 38), (40, 48), (50, 90)]
    a, b = _robust_fit(points)
    assert abs(a - 1.0) < 1e-6 and abs(b - 8.0) < 1e-6


def test_pair_translation_skip_english():
    orig = (
        "[00:20.54]初めてのルーブルは\n"
        "[00:22.55]なんてことは無かったわ\n"
        "[00:24.00](Can you give me one last kiss?)\n"
        "[00:26.00]忘れたくないこと\n"
        "[00:28.00]Oh oh oh oh oh…\n"
    )
    trans = "[00:20.54]第一次去卢浮宫时\n[00:22.55]并没有什么特别的感觉\n[00:26.00]不想遗忘之事\n"
    pairs = pair_translation(orig, trans)
    assert pairs[0][2] == "第一次去卢浮宫时"
    assert pairs[1][2] == "并没有什么特别的感觉"
    assert pairs[2][2] is None  # 英文行无译文
    assert pairs[3][2] == "不想遗忘之事"
    assert pairs[4][2] is None  # 拟声行无译文


def test_pair_translation_repeated_lines():
    orig = "[00:26.00]忘れたくないこと\n[00:30.00]忘れたくないこと\n"
    trans = "[00:26.00]不想遗忘之事\n[00:30.00]不愿遗忘之事\n"
    pairs = pair_translation(orig, trans)
    assert [p[2] for p in pairs] == ["不想遗忘之事", "不愿遗忘之事"]


def test_reattach_translation():
    orig = "[00:01.00]Hello\n[00:02.00](World)\n[00:03.00]Extra\n"
    trans = "[00:01.00]你好\n"
    pairs = pair_translation(orig, trans)
    # 模拟校准：时间戳整体 +5s
    calib = render_lrc([(t + 5.0, tx) for t, tx in parse_lrc(orig)])
    merged = reattach_translation(calib, pairs)
    lines = parse_lrc(merged)
    texts = [tx for _, tx in lines]
    assert texts == ["Hello", "你好", "(World)", "Extra"]
    assert abs(lines[1][0] - 6.0) < 1e-6  # 译文沿用校准后时间戳
    assert reattach_translation(calib, pair_translation(orig, "")) == calib


def _mk_json(matched_lines):
    return [{"line": ln, "start": t, "matched": True} for t, ln in matched_lines]


def test_apply_alignment_high_match():
    src = Lyric(text="[00:10.00]a\n[00:20.00]b\n[00:30.00]c\n")
    data = _mk_json([(11, "a"), (21, "b"), (31, "c")]) + [{"line": "z", "start": 25, "matched": False}]
    method, text, warning = _apply_alignment(src, data)
    assert method == "align" and text and not warning
    assert len(parse_lrc(text)) == 4


def test_apply_alignment_medium_offset():
    src = Lyric(text="\n".join(f"[00:{10+i:02d}.00]行{i}" for i in range(8)))
    data = _mk_json([(18, "行0"), (28, "行1"), (38, "行2")])
    method, text, _ = _apply_alignment(src, data)
    assert method == "align_offset"
    lines = parse_lrc(text)
    assert len(lines) == 8
    assert abs(lines[0][0] - 18.0) < 0.1


def test_apply_alignment_low_match():
    src = Lyric(text="[00:10.00]a\n[00:20.00]b\n[00:30.00]c\n")
    data = _mk_json([(11, "a")])
    method, text, warning = _apply_alignment(src, data)
    assert method == "" and text is None and "匹配率低" in warning


_LRC = "[00:20.54]初めてのルーブルは\n[00:22.55]なんてことは無かったわ\n"
_TLY = "[00:20.54]第一次去卢浮宫时\n[00:22.55]并没有什么特别的感觉\n"


class _FakeNetease:
    def __init__(self, cfg):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def search(self, query, limit=10):
        return [SongMeta(source="netease", id=1, name="One Last Kiss", artists=["宇多田ヒカル"])]

    async def get_lyric(self, song_id):
        return _LRC, _TLY


def test_from_netease_bilingual(monkeypatch):
    monkeypatch.setattr("musicalbili.providers.meta.NeteaseMeta", _FakeNetease)
    lyric = asyncio.run(lym._from_netease_bilingual(Config(), None, "One Last Kiss"))
    assert lyric is not None and lyric.source == "netease"
    texts = [tx for _, tx in parse_lrc(lyric.text)]
    assert any(any("\u3040" <= c <= "\u30ff" for c in tx) for tx in texts)
    ttexts = [tx for _, tx in parse_lrc(lyric.tlyric)]
    assert any(any("\u4e00" <= c <= "\u9fff" for c in tx) for tx in ttexts)
    merged = merge_translation(lyric.text, lyric.tlyric)
    mtexts = [tx for _, tx in parse_lrc(merged)]
    assert any(any("\u4e00" <= c <= "\u9fff" for c in tx) for tx in mtexts)


def test_fetch_lyrics_enrichment(monkeypatch):
    async def fake_lrclib(cfg, meta, query):
        return Lyric(source="lrclib", text="[00:01.00]初めてのルーブルは\n")

    async def fake_bilingual(cfg, meta, query):
        return Lyric(source="netease", text="[00:01.00]初めてのルーブルは\n[00:01.00]第一次去卢浮宫时\n")

    monkeypatch.setattr(lym, "_from_lrclib", fake_lrclib)
    monkeypatch.setattr(lym, "_from_netease_bilingual", fake_bilingual)
    cfg = Config()
    cfg.lyric_sources = ["lrclib"]
    lyric = asyncio.run(lym.fetch_lyrics(cfg, None, "x", "BV", 0))
    assert lyric is not None and lyric.source == "netease" and "第一次去卢浮宫时" in lyric.text


def test_fetch_lyrics_no_enrich_chinese(monkeypatch):
    async def fake_lrclib(cfg, meta, query):
        return Lyric(source="lrclib", text="[00:01.00]窗外的麻雀\n")

    async def fake_bilingual(cfg, meta, query):
        raise AssertionError("中文歌不应触发译文增强")

    monkeypatch.setattr(lym, "_from_lrclib", fake_lrclib)
    monkeypatch.setattr(lym, "_from_netease_bilingual", fake_bilingual)
    cfg = Config()
    cfg.lyric_sources = ["lrclib"]
    lyric = asyncio.run(lym.fetch_lyrics(cfg, None, "x", "BV", 0))
    assert lyric is not None and lyric.source == "lrclib"
