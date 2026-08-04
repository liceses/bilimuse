"""e2e pytest 隔离：优先用 tests/e2e/.runconfig（含 sessdata，gitignore），否则默认配置。

可用 `python tests/e2e/run_testset.py --config-dir tests/e2e/.runconfig --seed-from <你的config.json>`
一键生成带登录态的 .runconfig。会话开始会重置去重库，保证 WS 下载不触发去重。
"""

import json
import os
from pathlib import Path

import pytest

HERE = Path(__file__).parent
RUNCFG = HERE / ".runconfig"
DL = HERE / "dl"

_SEEK = ["sessdata", "whisper_model", "lyric_sources", "translation_enabled",
         "align_enabled", "search_lyric_lookup", "whisper_language", "hf_mirror"]


@pytest.fixture(scope="session")
def e2e_config():
    if not (RUNCFG / "config.json").is_file():
        RUNCFG.mkdir(parents=True, exist_ok=True)
        from bilimuse.config import Config

        donor = vars(Config.load())
        data = {k: donor[k] for k in _SEEK if k in donor}
        data["download_dir"] = str(DL)
        (RUNCFG / "config.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    DL.mkdir(parents=True, exist_ok=True)
    (RUNCFG / "downloads.db").unlink(missing_ok=True)  # 重置去重库
    os.environ["MUSICALBILI_CONFIG_DIR"] = str(RUNCFG)
    return RUNCFG
