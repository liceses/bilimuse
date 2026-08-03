"""M2 单元测试：文件名渲染 + 下载库去重 + ffmpeg 查找。"""

from musicalbili.config import Config
from musicalbili.db import DownloadDB
from musicalbili.services.download import find_ffmpeg, render_filename, sanitize_filename


def test_sanitize_filename():
    assert sanitize_filename('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"
    assert sanitize_filename("  晴天  ") == "晴天"
    assert sanitize_filename("") == "untitled"
    assert sanitize_filename("///") == "___"


def test_render_filename():
    assert render_filename("{artist} - {title}.{ext}", "周杰伦", "晴天", "m4a") == "周杰伦 - 晴天.m4a"
    assert render_filename("{artist} - {title}.{ext}", "周/杰伦", "晴天", "m4a") == "周_杰伦 - 晴天.m4a"


def test_db_dedup(tmp_path):
    db = DownloadDB(tmp_path / "t.db")
    assert not db.already_downloaded("BV1", 1)
    db.add("BV1", 1, "晴天", "周杰伦", format="m4a", file_path="a.m4a")
    assert db.already_downloaded("BV1", 1)
    assert not db.already_downloaded("BV1", 2)
    rows = db.list()
    assert len(rows) == 1
    assert rows[0]["title"] == "晴天"
    db.close()


def test_find_ffmpeg_config_path_first(monkeypatch):
    cfg = Config()
    cfg.ffmpeg_path = "C:/custom/ffmpeg.exe"
    assert find_ffmpeg(cfg) == "C:/custom/ffmpeg.exe"


def test_find_ffmpeg_system_path(monkeypatch):
    cfg = Config()
    monkeypatch.setattr("musicalbili.services.download.shutil.which", lambda name: "ffmpeg")
    assert find_ffmpeg(cfg) == "ffmpeg"


def test_find_ffmpeg_bundled_fallback(monkeypatch):
    cfg = Config()
    monkeypatch.setattr("musicalbili.services.download.shutil.which", lambda name: None)
    monkeypatch.setitem(__import__("sys").modules, "imageio_ffmpeg", type("_m", (), {"get_ffmpeg_exe": lambda: "/bundle/ffmpeg"}))
    assert find_ffmpeg(cfg) == "/bundle/ffmpeg"


def test_find_ffmpeg_none(monkeypatch):
    cfg = Config()
    monkeypatch.setattr("musicalbili.services.download.shutil.which", lambda name: None)
    monkeypatch.setitem(__import__("sys").modules, "imageio_ffmpeg", None)
    assert find_ffmpeg(cfg) is None
