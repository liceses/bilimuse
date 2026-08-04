"""M7 日志 + 统一状态通道测试。"""

import logging

import pytest

from musicalbili.logging_setup import get_logger, setup_logging
from musicalbili.status import emit, register_display


def _reset():
    root = logging.getLogger("musicalbili")
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()


@pytest.fixture(autouse=True)
def _clean():
    _reset()
    yield
    _reset()


def _log_path(tmp_path):
    return tmp_path / "logs" / "musicalbili.log"


def test_setup_logging_creates_file(monkeypatch, tmp_path):
    monkeypatch.setattr("musicalbili.logging_setup.default_config_dir", lambda: tmp_path)
    setup_logging("INFO", console_warning=False)
    get_logger("test").info("hello log")
    content = _log_path(tmp_path).read_text(encoding="utf-8")
    assert "INFO" in content and "hello log" in content


def test_emit_double_write(monkeypatch, tmp_path):
    monkeypatch.setattr("musicalbili.logging_setup.default_config_dir", lambda: tmp_path)
    setup_logging("INFO", console_warning=False)
    received: list[dict] = []
    register_display(received.append)
    emit("INFO", "正在解析元数据: 咪咕")
    assert received and received[0]["text"] == "正在解析元数据: 咪咕"
    assert "正在解析元数据: 咪咕" in _log_path(tmp_path).read_text(encoding="utf-8")


def test_level_filter(monkeypatch, tmp_path):
    monkeypatch.setattr("musicalbili.logging_setup.default_config_dir", lambda: tmp_path)
    setup_logging("DEBUG", console_warning=False)
    received: list[dict] = []
    register_display(received.append)
    emit("DEBUG", "内部细节")
    emit("WARNING", "重要警告")
    assert [e["level"] for e in received] == ["WARNING"]  # DEBUG 不显示
    content = _log_path(tmp_path).read_text(encoding="utf-8")
    assert "内部细节" in content  # DEBUG 进日志（level=DEBUG）
    assert "重要警告" in content
