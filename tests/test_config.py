"""M5 补充测试：config 保存往返 + 交互配置向导。"""

import json
from pathlib import Path

from musicalbili.config import Config


def test_config_save_load_roundtrip(tmp_path):
    cfg = Config()
    cfg.download_dir = tmp_path / "music"
    cfg.format = "mp3"
    cfg.whisper_model = "base"
    p = tmp_path / "config.json"
    cfg.save(p)
    loaded = Config.load(p)
    assert loaded.download_dir == tmp_path / "music"
    assert loaded.format == "mp3"
    assert loaded.whisper_model == "base"


def test_config_wizard(monkeypatch, tmp_path):
    from musicalbili.cli import config as config_cmd

    cfg_path = tmp_path / "config.json"
    answers = iter(["D:/Music", "mp3", "netease,lrclib", "n", "base", "n", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    config_cmd(config=cfg_path)
    saved = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert Path(saved["download_dir"]) == Path("D:/Music")
    assert saved["format"] == "mp3"
    assert saved["lyric_sources"] == ["netease", "lrclib"]
    assert saved["align_enabled"] is False
    assert saved["whisper_model"] == "base"
    assert saved["sessdata"] == ""
