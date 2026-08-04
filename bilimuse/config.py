"""全局配置。"""

from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "bilimuse"
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def project_root() -> Path:
    """项目根：含 bilimuse/ 包的上层目录。"""
    return Path(__file__).resolve().parents[1]


def is_portable() -> bool:
    """便携模式：项目根 .portable 标记文件 或环境变量 MUSICALBILI_PORTABLE=1。"""
    return os.environ.get("MUSICALBILI_PORTABLE") == "1" or (project_root() / ".portable").is_file()


def default_config_dir() -> Path:
    """配置目录（config/db/logs 的派生源头）。便携 → 项目 data/，否则平台目录。"""
    if base := os.environ.get("MUSICALBILI_CONFIG_DIR"):
        return Path(base)
    if is_portable():
        return project_root() / "data"
    if os.name == "nt":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / APP_NAME


class Config:
    """项目配置，支持从 JSON 配置文件加载。"""

    def __init__(self) -> None:
        self.download_dir: Path = Path("downloads")
        self.format: str = "m4a"
        self.sessdata: str = ""
        self.buvid3: str = ""
        self.proxy: str = ""
        self.ffmpeg_path: str = ""
        self.ua: str = DEFAULT_UA
        self.filename_template: str = "{artist} - {title}.{ext}"
        self.lyric_sources: list[str] = ["lrclib", "netease", "bilibili"]
        self.search_lyric_lookup: bool = True
        self.translation_enabled: bool = True
        self.align_enabled: bool = True
        self.whisper_model: str = "small"
        self.whisper_language: str = "zh"
        self.vocal_separate: bool = False
        self.log_level: str = "INFO"
        self.hf_mirror: str = "https://hf-mirror.com"

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        cfg = cls()
        path = path or default_config_dir() / "config.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            for key, value in data.items():
                if hasattr(cfg, key):
                    setattr(cfg, key, value)
        cfg.download_dir = Path(cfg.download_dir)
        return cfg

    def save(self, path: Path | None = None) -> None:
        path = path or default_config_dir() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = dict(vars(self))
        data["download_dir"] = str(data["download_dir"])
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
