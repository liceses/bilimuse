"""模型检测/解析单元测试。"""

from bilimuse.config import Config
from bilimuse.services.aligner import resolve_model


def test_resolve_model_local(tmp_path):
    d = tmp_path / "m"
    d.mkdir()
    (d / "model.bin").write_bytes(b"x")
    cfg = Config()
    cfg.whisper_model = str(d)
    assert resolve_model(cfg)["kind"] == "local"


def test_resolve_model_missing():
    cfg = Config()
    cfg.whisper_model = "nonexistent-size"
    assert resolve_model(cfg)["kind"] == "missing"


def test_resolve_model_none():
    cfg = Config()
    cfg.whisper_model = ""
    assert resolve_model(cfg)["kind"] == "none"
