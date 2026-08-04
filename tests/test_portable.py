"""M8 便携模式测试。"""

from bilimuse.config import default_config_dir, is_portable


def _use_tmp_root(monkeypatch, tmp_path):
    monkeypatch.setattr("bilimuse.config.project_root", lambda: tmp_path)


def test_standard_mode(monkeypatch, tmp_path):
    _use_tmp_root(monkeypatch, tmp_path)
    monkeypatch.delenv("MUSICALBILI_PORTABLE", raising=False)
    assert not is_portable()


def test_portable_marker(monkeypatch, tmp_path):
    _use_tmp_root(monkeypatch, tmp_path)
    (tmp_path / ".portable").touch()
    monkeypatch.delenv("MUSICALBILI_CONFIG_DIR", raising=False)
    assert is_portable()
    assert default_config_dir() == tmp_path / "data"


def test_portable_env(monkeypatch, tmp_path):
    _use_tmp_root(monkeypatch, tmp_path)
    monkeypatch.setenv("MUSICALBILI_PORTABLE", "1")
    monkeypatch.delenv("MUSICALBILI_CONFIG_DIR", raising=False)
    assert is_portable()
    assert default_config_dir() == tmp_path / "data"


def test_config_dir_override_priority(monkeypatch, tmp_path):
    _use_tmp_root(monkeypatch, tmp_path)
    (tmp_path / ".portable").touch()
    override = tmp_path / "elsewhere"
    monkeypatch.setenv("MUSICALBILI_CONFIG_DIR", str(override))
    assert default_config_dir() == override  # 显式覆盖优先于便携
