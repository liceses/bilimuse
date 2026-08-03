"""M4 单元测试：LRC 解析/渲染/清理/翻译合并 + 快速校准。"""

from musicalbili.models import Lyric
from musicalbili.services.aligner import _apply_alignment, _linear_fit, calibrate_quick
from musicalbili.services.lyric import (
    clean_netease,
    detect_lyric_language,
    merge_translation,
    parse_lrc,
    plain_lines,
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
