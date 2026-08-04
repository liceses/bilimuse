"""校准基准：whisper 对齐 vs gold 人工标注时间戳。

gold JSON 结构:
    {
      "id": "G01",
      "name": "周杰伦-晴天",
      "bvid": "BV...", "cid": 123, "format": "m4a",
      "language": "zh",
      "lyrics": [[12.3, "窗外的麻雀"], [16.1, "在电线杆上多嘴"], ...]
    }

判定: 中位误差 ≤1.5s 优 / ≤3.0s 过 / >3.0s 败。

用法:
    python tests/e2e/align_bench.py [--gold-dir tests/e2e/gold] [--config-dir <dir>] [--download-dir tests/e2e/dl]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bilimuse.config import Config
from bilimuse.models import Lyric
from bilimuse.services.aligner import calibrate_align
from bilimuse.services.download import download_song
from bilimuse.services.lyric import parse_lrc, render_lrc

HERE = Path(__file__).parent
DEFAULT_GOLD = HERE / "gold"


def _load_cfg(args: argparse.Namespace) -> Config:
    if args.config_dir:
        cdir = Path(args.config_dir).resolve()
        os.environ["MUSICALBILI_CONFIG_DIR"] = str(cdir)
        cfg = Config.load(cdir / "config.json")
    else:
        cfg = Config.load()
    cfg.download_dir = Path(args.download_dir).resolve()
    cfg.download_dir.mkdir(parents=True, exist_ok=True)
    return cfg


async def _run_one(cfg: Config, gold: dict) -> dict:
    bvid, cid = gold["bvid"], gold["cid"]
    fmt = gold.get("format", "m4a")
    name = gold.get("name", "")
    try:
        path = await download_song(bvid, cid, cfg=cfg, title=name, artist=gold.get("artist", ""), fmt=fmt)
    except Exception as e:  # noqa: BLE001
        return {"id": gold["id"], "name": name, "grade": "FAIL", "detail": f"下载失败: {e}"}

    gold_lines = [(float(t), str(tx)) for t, tx in gold["lyrics"]]
    text = render_lrc([(0.0, tx) for _, tx in gold_lines])
    lyric = Lyric(source="gold", text=text)
    aligned = await calibrate_align(
        path, lyric, cfg, language_hint=gold.get("language", ""), on_status=None
    )
    if aligned is None:
        return {"id": gold["id"], "name": name, "grade": "FAIL", "detail": lyric.warning}

    out = parse_lrc(aligned.text)
    matched: list[tuple[float, float]] = []
    for gt, gtx in gold_lines:
        cands = [t for t, tx in out if tx.strip() == gtx.strip()]
        if cands:
            matched.append((gt, min(cands, key=lambda t: abs(t - gt))))
    if not matched:
        return {"id": gold["id"], "name": name, "grade": "FAIL", "detail": "无匹配歌词行", "warn": lyric.warning}

    errors = sorted(abs(g - a) for g, a in matched)
    n = len(errors)
    median = errors[n // 2]
    p90 = errors[min(n - 1, int(n * 0.9))]
    grade = "优" if median <= 1.5 else ("过" if median <= 3.0 else "败")
    return {
        "id": gold["id"], "name": name, "grade": grade,
        "median_s": round(median, 2), "p90_s": round(p90, 2),
        "coverage": f"{len(matched)}/{len(gold_lines)}",
        "method": aligned.calib_method, "warn": aligned.warning,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="校准基准（gold 时间戳对比）")
    ap.add_argument("--gold-dir", default=str(DEFAULT_GOLD))
    ap.add_argument("--config-dir", default="")
    ap.add_argument("--download-dir", default=str(HERE / "dl"))
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    gold_dir = Path(args.gold_dir)
    golds = sorted(gold_dir.glob("*.json"))
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        golds = [g for g in golds if g.stem in wanted]
    if not golds:
        print("无 gold 标注文件（gold/*.json）")
        return 1

    cfg = _load_cfg(args)
    rows = [asyncio.run(_run_one(cfg, json.loads(g.read_text(encoding="utf-8")))) for g in golds]
    for r in rows:
        print(f"[{r['id']}] {r['name']}: {r['grade']}  median={r.get('median_s','-')}s p90={r.get('p90_s','-')}s cov={r.get('coverage','-')} method={r.get('method','-')} {r.get('detail','')}")
    n_优 = sum(1 for r in rows if r["grade"] == "优")
    n_过 = sum(1 for r in rows if r["grade"] == "过")
    n_败 = sum(1 for r in rows if r["grade"] == "FAIL" or r["grade"] == "败")
    print(f"\n汇总: 优 {n_优} / 过 {n_过} / 败 {n_败}")
    return 0 if n_败 == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
