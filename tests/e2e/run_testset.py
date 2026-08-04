"""BiliMuse E2E 测试集运行器（真实网络）。

用法:
    python tests/e2e/run_testset.py                     # 全套
    python tests/e2e/run_testset.py --only C01,C05      # 指定用例
    python tests/e2e/run_testset.py --probe             # 探测模式：搜+下，打印观测值，不断言
    python tests/e2e/run_testset.py --no-align          # 关 whisper 校准（快速冒烟）
    python tests/e2e/run_testset.py --config-dir <dir>  # 隔离配置目录（无则自举：从真实配置复制敏感项）
    python tests/e2e/run_testset.py --download-dir tests/e2e/dl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from bilimuse.config import Config
from bilimuse.models import Lyric, SongMeta
from bilimuse.services.aligner import probe_duration
from bilimuse.services.lyric import detect_lyric_language
from bilimuse.services.pipeline import download_song_pipeline
from bilimuse.services.search import search_versions

HERE = Path(__file__).parent
DEFAULT_CASES = HERE / "cases.yaml"
DEFAULT_DL = HERE / "dl"
DEFAULT_OUT = HERE / "report"
SEED_FIELDS = ["sessdata", "whisper_model", "lyric_sources", "translation_enabled",
               "align_enabled", "search_lyric_lookup", "whisper_language", "hf_mirror"]
CACHE_FILE = DEFAULT_OUT / "download_cache.json"


def _load_cache() -> dict:
    if CACHE_FILE.is_file():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _cache_key(bvid: str, fmt: str, align: bool = True) -> str:
    return f"{bvid}:{fmt}:align{1 if align else 0}"


def _record_cache(cache: dict, bvid: str, fmt: str, result: dict, align: bool = True) -> None:
    """写入持久化缓存文件（不动进程内 Result 缓存）。"""
    meta, lyric = result.get("meta"), result.get("lyric")
    persistent = _load_cache()
    persistent[_cache_key(bvid, fmt, align)] = {
        "path": str(result["path"]),
        "artist": meta.artist_str if meta else "",
        "title": meta.name if meta else "",
        "album": meta.album if meta else "",
        "lyric_source": lyric.source if lyric else "",
        "calib_method": lyric.calib_method if lyric else "",
        "lyric_text": lyric.text if lyric else "",
    }
    _save_cache(persistent)


def _from_cache(entry: dict) -> dict:
    artist = entry.get("artist", "")
    return {
        "path": Path(entry["path"]),
        "meta": SongMeta(source="cache", id=0, name=entry.get("title", ""),
                         artists=[artist] if artist else [], album=entry.get("album", "")),
        "lyric": Lyric(source=entry.get("lyric_source", ""), text=entry.get("lyric_text", ""),
                       calib_method=entry.get("calib_method", "")),
    }


class Result:
    def __init__(self, case: dict) -> None:
        self.case = case
        self.status = "RUN"
        self.checks: list[dict] = []
        self.review = [r.get("item", r) for r in case.get("review", [])]
        self.elapsed = 0.0
        self.hits: list = []
        self.path: Path | None = None
        self.meta = None
        self.lyric = None

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "ok": bool(ok), "detail": detail})

    def all_ok(self) -> bool:
        return bool(self.checks) and all(c["ok"] for c in self.checks)


def bootstrap_config(args: argparse.Namespace) -> Config:
    """加载配置；--config-dir 无 config.json 时自举（从真实配置/--seed-from 复制敏感项 + 强制下载目录）。"""
    if args.config_dir:
        cdir = Path(args.config_dir).resolve()
        cdir.mkdir(parents=True, exist_ok=True)
        cfg_path = cdir / "config.json"
        if not cfg_path.is_file():
            if args.seed_from and Path(args.seed_from).is_file():
                donor = json.loads(Path(args.seed_from).read_text(encoding="utf-8"))
            else:
                donor = vars(Config.load())
            data = {k: donor[k] for k in SEED_FIELDS if k in donor}
            data["download_dir"] = str(Path(args.download_dir).resolve())
            cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.environ["MUSICALBILI_CONFIG_DIR"] = str(cdir)
        cfg = Config.load(cfg_path)
    else:
        cfg = Config.load()
    cfg.download_dir = Path(args.download_dir).resolve()
    cfg.download_dir.mkdir(parents=True, exist_ok=True)
    if args.format:
        cfg.format = args.format
    if args.no_align:
        cfg.align_enabled = False
    return cfg


def _select_bvid(case: dict, hits: list) -> str | None:
    if case.get("bvid"):
        return case["bvid"]
    if hits:
        idx = case.get("index", 0)
        return hits[idx].version.bvid if idx < len(hits) else hits[0].version.bvid
    return None


def _copy_to_case(cfg: Config, path: Path) -> None:
    """复用缓存时把音频+侧车 .lrc 拷进本用例目录，保证每例目录自足（评审可听）。"""
    if path is None or not path.is_file():
        return
    dst = cfg.download_dir / path.name
    if dst != path and not dst.is_file():
        shutil.copy2(path, dst)
        lrc = path.with_suffix(".lrc")
        if lrc.is_file():
            shutil.copy2(lrc, cfg.download_dir / lrc.name)


async def _check_expect(r: Result, cfg: Config, duration: float | None) -> None:
    exp = r.case.get("expect") or {}
    path, meta, lyric = r.path, r.meta, r.lyric

    r.check("文件存在", path is not None and path.is_file(), str(path) if path else "无路径")
    if path and exp.get("format"):
        want = exp["format"]
        want = [want] if isinstance(want, str) else want
        r.check("格式", path.suffix.lstrip(".") in want, f"got={path.suffix} want∈{want}")
    if path and r.case.get("name_sanitized"):
        illegal = [c for c in path.name if c in '\\/:*?"<>|']
        r.check("文件名净化", not illegal, f"非法字符={illegal}")

    if exp.get("no_meta") is True:
        r.check("无标签(反查失败)", meta is None, f"got={meta.artist_str if meta else None}")
    elif "artist" in exp or "title" in exp:
        if meta is None:
            r.check("标签(反查)", False, "meta 为 None")
        else:
            ok = True
            if exp.get("artist"):
                ok &= exp["artist"].lower() in (meta.artist_str or "").lower()
            if exp.get("title"):
                ok &= exp["title"].lower() in (meta.name or "").lower()
            r.check("标签(反查)", ok, f"{meta.artist_str} - {meta.name}")
            if exp.get("album"):
                r.check("专辑", exp["album"] in (meta.album or ""), f"got={meta.album!r}")

    if exp.get("duration_range"):
        lo, hi = exp["duration_range"]
        ok = duration is not None and lo <= duration <= hi
        r.check("时长", ok, f"{duration if duration is not None else 'None'}s ∈ [{lo},{hi}]")

    if exp.get("language"):
        lang = detect_lyric_language(lyric.text) if lyric else ""
        meta_lang = (meta.language if meta else "") or ""
        if exp["language"] == "yue":
            ok = lang == "zh"  # 粤语汉字检测为 zh
        else:
            ok = lang == exp["language"] or meta_lang == exp["language"]
        r.check("语言", ok, f"detect={lang!r} meta={meta_lang!r}")

    has_lyric_exp = any(k in exp for k in ("lyric_keywords", "lyric_source_in", "calib_method_in"))
    if exp.get("lyric_source") == "placeholder":
        r.check("占位歌词", lyric is not None and lyric.source == "placeholder",
                f"got={lyric.source if lyric else None}")
    elif has_lyric_exp:
        if lyric is None:
            r.check("歌词", False, "无歌词")
        else:
            if exp.get("lyric_source_in"):
                r.check("歌词来源", lyric.source in exp["lyric_source_in"], f"got={lyric.source}")
            if exp.get("lyric_keywords"):
                missing = [k for k in exp["lyric_keywords"] if k not in (lyric.text or "")]
                r.check("歌词关键词", not missing, f"缺失={missing}")
            if exp.get("calib_method_in"):
                r.check("校准方法", lyric.calib_method in exp["calib_method_in"], f"got={lyric.calib_method}")


async def _download(cfg: Config, case: dict, bvid: str) -> dict:
    return await download_song_pipeline(
        cfg, bvid, case.get("page", 1), on_event=None,
        no_tag=case.get("no_tag", False),
        no_lyric=case.get("no_lyric", False),
        force_align=case.get("force_align", False),
    )


async def run_case(cfg: Config, case: dict, cache: dict, args: argparse.Namespace) -> Result:
    r = Result(case)
    t0 = time.time()
    cfg.format = case.get("format", cfg.format)
    cfg.download_dir = (Path(args.download_dir) / case["id"]).resolve()
    cfg.download_dir.mkdir(parents=True, exist_ok=True)
    try:
        if case.get("mode") == "download":
            hits = []
        else:
            cfg.search_lyric_lookup = case.get("search_lyric_lookup", cfg.search_lyric_lookup)
            hits = await search_versions(cfg, case["query"])
        r.hits = hits
        se = case.get("search_expect") or {}

        if case.get("mode") == "search_only":
            if se.get("no_results"):
                r.check("搜索无结果", len(hits) == 0, f"命中 {len(hits)}")
            r.status = "PASS" if r.all_ok() else "FAIL"
            return r

        if se.get("min_hits"):
            r.check("搜索min_hits", len(hits) >= se["min_hits"], f"命中 {len(hits)}")
        if se.get("lyric_hit") is True:
            r.check("歌词反查命中", any(h.source == "lyric" for h in hits),
                    f"lyric={sum(1 for h in hits if h.source == 'lyric')} direct={sum(1 for h in hits if h.source == 'direct')}")
        if se.get("bvids"):
            got = {h.version.bvid for h in hits}
            ok = bool(got & set(se["bvids"]))
            r.check("搜索成员", ok, f"期望∈{se['bvids']} 命中={sorted(got)[:8]}")

        bvid = _select_bvid(case, hits)
        if not bvid:
            r.check("可选版本", False, "搜索为空且未指定 bvid")
            r.status = "FAIL"
            return r

        if case.get("dedup"):
            try:
                await _download(cfg, case, bvid)
                r.check("首次下载", True, bvid)
            except RuntimeError as e:
                if "去重" not in str(e):
                    raise
                r.check("首次下载(已在库)", True, str(e)[:90])
            try:
                await _download(cfg, case, bvid)
                r.check("去重跳过", False, "二次下载未报去重")
            except RuntimeError as e:
                r.check("去重跳过", "去重" in str(e), str(e))
            r.status = "PASS" if r.all_ok() else "FAIL"
            return r

        key = _cache_key(bvid, cfg.format, cfg.align_enabled)
        if key in cache:
            prev = cache[key]
            r.path, r.meta, r.lyric = prev.path, prev.meta, prev.lyric
            _copy_to_case(cfg, r.path)
            await _check_expect(r, cfg, await probe_duration(r.path, cfg) if r.path else None)
            r.status = "PASS" if r.all_ok() else "FAIL"
            r.check("复用缓存", True, f"key={key} 已由 {prev.case['id']} 下载")
            return r

        entry = _load_cache().get(key)
        if entry and Path(entry["path"]).is_file():
            result = _from_cache(entry)
            _copy_to_case(cfg, result["path"])
            r.check("复用缓存文件", True, f"key={key}")
        else:
            result = await _download(cfg, case, bvid)
        r.path = Path(result["path"])
        r.meta = result["meta"]
        r.lyric = result["lyric"]
        cache[key] = r  # 进程内引用复用
        _record_cache(cache, bvid, cfg.format, result, cfg.align_enabled)
        duration = await probe_duration(r.path, cfg)
        await _check_expect(r, cfg, duration)
        r.status = "PASS" if r.all_ok() else "FAIL"
    except Exception as e:  # noqa: BLE001
        if case.get("expect_error"):
            r.check("异常匹配", case["expect_error"] in str(e), str(e))
        else:
            r.check("无异常", False, f"{type(e).__name__}: {e}")
        r.status = "PASS" if r.all_ok() else "FAIL"
    r.elapsed = time.time() - t0
    return r


def _fmt_checks(r: Result) -> str:
    return "; ".join(f"{'✓' if c['ok'] else '✗'} {c['name']} {c['detail']}".strip() for c in r.checks)


def render_md(results: list[Result], args: argparse.Namespace) -> str:
    n_pass = sum(1 for r in results if r.status == "PASS")
    n_fail = sum(1 for r in results if r.status == "FAIL")
    n_other = len(results) - n_pass - n_fail
    lines = [
        "# BiliMuse E2E 测试集报告", "",
        f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 结果: 共 {len(results)}  通过 {n_pass}  失败 {n_fail}  其他 {n_other}",
        "",
        "| id | 名称 | 状态 | 耗时 | 校验明细 |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r.case['id']} | {r.case['name']} | {r.status} | {r.elapsed:.0f}s | {_fmt_checks(r)} |")
    lines.append("")
    lines.append("## 人工评审表（对齐质量 A/B/C，对照 .lrc 听前几行）")
    lines.append("| id | 评审项 | 结论(A/B/C) | 备注 |")
    lines.append("|---|---|---|---|")
    for r in results:
        for it in r.review:
            lines.append(f"| {r.case['id']} | {it} |  |  |")
    lines.append("")
    return "\n".join(lines)


async def main_async(args: argparse.Namespace) -> int:
    cfg = bootstrap_config(args)
    from bilimuse.config import default_config_dir

    (default_config_dir() / "downloads.db").unlink(missing_ok=True)  # 每轮重置去重库
    data = yaml.safe_load(Path(args.cases).read_text(encoding="utf-8"))
    cases = data.get("cases", [])
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        cases = [c for c in cases if c["id"] in wanted]

    cache: dict = {}
    results: list[Result] = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['id']} {case['name']} ...", flush=True)
        if args.probe:
            res = await _probe_case(cfg, case, args.download_dir)
        else:
            res = await run_case(cfg, case, cache, args)
        results.append(res)
        if args.probe:
            print("  " + _probe_text(res))
        else:
            print(f"  -> {res.status} ({res.elapsed:.0f}s) " + _fmt_checks(res)[:160])

    if args.probe:
        _dump_probe(results, args)
    else:
        md = render_md(results, args)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(md, encoding="utf-8")
        (out / "report.json").write_text(
            json.dumps([_serialize(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(md)
    return 0 if all(r.status == "PASS" for r in results) else 1


async def _probe_case(cfg: Config, case: dict, dl_base: str) -> Result:
    """探测：只搜+下，打印观测值，不做 expect 断言。"""
    r = Result(case)
    cfg.format = case.get("format", cfg.format)
    cfg.download_dir = (Path(dl_base) / case["id"]).resolve()
    cfg.download_dir.mkdir(parents=True, exist_ok=True)
    try:
        hits = await search_versions(cfg, case["query"])
        r.hits = hits
        r.review = ["观测: " + "; ".join(f"{h.version.bvid}({h.source}) {h.version.title}" for h in hits[:3])]
        bvid = _select_bvid(case, hits)
        if not bvid:
            r.status = "EMPTY"
            return r
        key = _cache_key(bvid, cfg.format, cfg.align_enabled)
        entry = _load_cache().get(key)
        if entry and Path(entry["path"]).is_file():
            result = _from_cache(entry)
            _copy_to_case(cfg, result["path"])
            r.check("复用缓存", True, f"key={key}")
        else:
            result = await _download(cfg, case, bvid)
        r.path = Path(result["path"])
        r.meta = result["meta"]
        r.lyric = result["lyric"]
        _record_cache(_load_cache(), bvid, cfg.format, result, cfg.align_enabled)
        r.status = "DONE"
    except Exception as e:  # noqa: BLE001
        r.check("probe", False, f"{type(e).__name__}: {e}")
        r.status = "ERROR"
    return r


def _probe_text(r: Result) -> str:
    m = r.meta
    meta = f"artist={m.artist_str!r} title={m.name!r} album={m.album!r} lang={m.language!r}" if m else "meta=None"
    lyr = f"src={r.lyric.source} calib={r.lyric.calib_method} warn={r.lyric.warning!r}" if r.lyric else "lyric=None"
    hit_info = ""
    if r.hits:
        h = r.hits[0].version
        hit_info = f"bvid={h.bvid} {h.title} {h.author} {h.duration}s"
    return f"{hit_info} | {meta} | {lyr}"


def _dump_probe(results: list[Result], args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    print("\n==== 观测汇总（用于固化 cases.yaml expect）====")
    for r in results:
        if r.review and r.review[0].startswith("观测: "):
            print(f"# {r.case['id']} {r.case['name']}")
            print("  " + _probe_text(r))
            print("  " + r.review[0])
        rows.append({
            "id": r.case["id"], "name": r.case["name"], "status": r.status,
            "hits": [{"bvid": h.version.bvid, "source": h.source, "title": h.version.title,
                      "author": h.version.author, "duration": h.version.duration,
                      "play": h.version.play} for h in r.hits],
            "selected": _probe_text(r),
        })
    (out / "probe.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n观测已写入: {out / 'probe.json'}")


def _serialize(r: Result) -> dict:
    return {
        "id": r.case["id"], "name": r.case["name"], "status": r.status,
        "elapsed_s": round(r.elapsed, 1), "checks": r.checks, "review": r.review,
        "hits": [{"bvid": h.version.bvid, "source": h.source, "title": h.version.title} for h in r.hits],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="BiliMuse E2E 测试集")
    ap.add_argument("--cases", default=str(DEFAULT_CASES))
    ap.add_argument("--only", default="")
    ap.add_argument("--config-dir", default="")
    ap.add_argument("--seed-from", default="", help="自举配置时从该 config.json 复制 sessdata/模型等")
    ap.add_argument("--download-dir", default=str(DEFAULT_DL))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--format", default="")
    ap.add_argument("--no-align", action="store_true")
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n中断")
        return 130


if __name__ == "__main__":
    sys.exit(main())
