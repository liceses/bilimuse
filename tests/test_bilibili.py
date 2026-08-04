"""B 站客户端纯函数测试（不联网）。"""

from bilimuse.providers.bilibili import _parse_duration, _strip_html


def test_parse_duration():
    assert _parse_duration("317") == 317
    assert _parse_duration("3:37") == 217
    assert _parse_duration("1:02:33") == 3753
    assert _parse_duration("845:22") == 50722


def test_strip_html():
    assert _strip_html("【4K】<em class=\"keyword\">周杰伦</em> - 晴天") == "【4K】周杰伦 - 晴天"
    assert _strip_html("无标签") == "无标签"
