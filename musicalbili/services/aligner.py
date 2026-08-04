"""音频时长探测 + 歌词时间轴校准（快速偏移/缩放 + lyric-align 强制对齐）。"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from ..config import Config
from ..models import Lyric
from .download import find_ffmpeg
from .lyric import detect_lyric_language, parse_lrc, plain_lines, render_lrc

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
WHISPER_SIZES = ["tiny", "base", "small", "medium", "large-v3-turbo"]
_MODEL_FILES = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]


def _hf_cache_dir() -> Path:
    return Path.home() / ".cache" / "huggingface" / "hub"


def faster_whisper_installed() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def detect_models() -> list[dict]:
    """检测可用的 whisper 模型：本地 models/ + HF 缓存。"""
    models: list[dict] = []
    local = Path("models")
    if local.is_dir():
        for d in sorted(local.iterdir()):
            if d.is_dir() and (d / "model.bin").is_file():
                size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
                models.append({"kind": "local", "name": d.name, "path": str(d), "size_mb": round(size / 1e6)})
    hf = _hf_cache_dir()
    if hf.is_dir():
        for d in hf.glob("models--Systran--faster-whisper-*"):
            if not any(d.rglob("model.bin")):
                continue
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            name = d.name.replace("models--Systran--", "")
            models.append({"kind": "cached", "name": name, "path": str(d), "size_mb": round(size / 1e6)})
    return models


def resolve_model(cfg: Config) -> dict:
    """解析配置的 whisper_model → 实际使用与状态（本地/缓存/缺失）。"""
    m = (cfg.whisper_model or "").strip()
    if not m:
        return {"used": "", "kind": "none", "note": "未配置 whisper_model"}
    p = Path(m)
    if p.is_dir() and (p / "model.bin").is_file():
        return {"used": m, "kind": "local", "note": "本地模型"}
    cached = _hf_cache_dir() / f"models--Systran--faster-whisper-{m}"
    if cached.is_dir() and any(cached.rglob("model.bin")):
        return {"used": m, "kind": "cached", "note": "HF 缓存"}
    return {"used": m, "kind": "missing", "note": "未找到，可 `musicalbili model download` 下载"}


async def download_model(
    size: str,
    dest: Path,
    source: str = "modelscope",
    hf_mirror: str = "",
    on_status: Callable[[str], Awaitable[None]] | None = None,
) -> Path:
    """从 ModelScope(默认)/HF 下载 faster-whisper 模型到 dest。"""
    size = size.strip().lstrip(".")
    repo = f"Systran/faster-whisper-{size}"
    if source == "modelscope":
        base = f"https://www.modelscope.cn/models/{repo}/resolve/master"
    else:
        base = f"{hf_mirror or 'https://huggingface.co'}/{repo}/resolve/main"
    dest.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(
        trust_env=False, timeout=httpx.Timeout(180.0, connect=15.0), follow_redirects=True
    ) as client:
        for fname in _MODEL_FILES:
            url = f"{base}/{fname}"
            if on_status:
                await on_status(f"下载 {repo}/{fname} ...")
            r = await client.get(url)
            if r.status_code != 200:
                continue
            tmp = dest / f"{fname}.part"
            tmp.write_bytes(r.content)
            tmp.replace(dest / fname)
    if not (dest / "model.bin").is_file():
        raise RuntimeError(f"下载失败：未取得 model.bin（{repo}）")
    return dest


def _align_exe() -> str | None:
    """找 lyric-align：PATH → venv Scripts（python -c 时 venv 不在 PATH）。"""
    if exe := shutil.which("lyric-align"):
        return exe
    venv_bin = Path(sys.executable).parent
    for name in ("lyric-align.exe", "lyric-align"):
        p = venv_bin / name
        if p.is_file():
            return str(p)
    return None


def align_available() -> bool:
    return _align_exe() is not None


async def probe_duration(path: Path, cfg: Config) -> float | None:
    """三级时长探测：mutagen → ffmpeg `-i -f null -`。fMP4 直拷 m4a mutagen 读不出。"""
    try:
        from mutagen import File

        audio = File(path)
        if audio and audio.info and audio.info.length:
            return float(audio.info.length)
    except Exception:  # noqa: BLE001, S110
        pass
    ffmpeg = find_ffmpeg(cfg)
    if not ffmpeg:
        return None
    proc = await asyncio.create_subprocess_exec(
        ffmpeg, "-hide_banner", "-i", str(path), "-f", "null", "-",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, err = await proc.communicate()
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    m = _DURATION_RE.search(err.decode(errors="replace"))
    if m:
        h, mi, s = m.groups()
        return int(h) * 3600 + int(mi) * 60 + float(s)
    return None


def calibrate_quick(text: str, duration: float, tol: float = 5.0) -> tuple[str, str, bool]:
    """廉价初筛。已同步返回原文本；失配按时长线性缩放。

    返回 (new_text, method, synced)。method: synced/scale/none。
    """
    lines = parse_lrc(text)
    if not lines:
        return text, "none", False
    times = [t for t, _ in lines]
    first, last = min(times), max(times)
    if last <= 0:
        return text, "none", False
    if abs(last - duration) <= tol and first <= 2.0:
        return text, "synced", True
    scale = duration / last
    return render_lrc([(t * scale, tx) for t, tx in lines]), "scale", False


def _linear_fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    """最小二乘拟合 y = a*x + b；退化（x 恒等）时只做平移。"""
    n = len(points)
    if n < 2:
        return 1.0, 0.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if abs(den) < 1e-9:
        return 1.0, my - mx
    a = sum((x - mx) * (y - my) for x, y in points) / den
    return a, my - a * mx


def _robust_fit(points: list[tuple[float, float]]) -> tuple[float, float]:
    """锚点拟合：偏移近一致（MAD≤3s）→ 纯平移（a=1，中位数偏移）；否则 LSQ。

    官方 MV 前留白是纯平移场景，LSQ 会被离群锚点带偏，故先判 MAD。
    """
    deltas = sorted(y - x for x, y in points)
    n = len(deltas)
    if not n:
        return 1.0, 0.0
    med = deltas[n // 2]
    mad = sorted(abs(d - med) for d in deltas)[n // 2]
    if mad <= 3.0:
        return 1.0, med
    return _linear_fit(points)


def _apply_alignment(lyric: Lyric, data: list[dict]) -> tuple[str, str | None, str]:
    """根据 lyric-align json 决定采用策略。

    返回 (method, new_text|None, warning)。method: align/align_offset/空。
    """
    lines = [(float(l["start"]), l["line"]) for l in data if l.get("start") is not None]
    if not lines:
        return "", None, "lyric-align 未产出有效时间轴（可能纯音乐或 ASR 失败）"
    src = parse_lrc(lyric.text)
    src_map: dict[str, float] = {}
    for t, tx in src:
        src_map.setdefault(tx.strip(), t)
    anchors: list[tuple[float, float]] = []
    matched = 0
    for l in data:
        if not l.get("matched"):
            continue
        matched += 1
        line = (l.get("line") or "").strip()
        t = l.get("start")
        if t is not None and line in src_map:
            anchors.append((src_map[line], float(t)))
    src_count = len(src)
    if matched >= max(2, src_count * 0.5):
        return "align", render_lrc(lines), ""
    if len(anchors) >= 3:
        a, b = _robust_fit(anchors)
        new_text = render_lrc([(max(0.0, a * t + b), tx) for t, tx in src])
        return "align_offset", new_text, f"基于 {len(anchors)} 个锚点全局对齐"
    return "", None, f"lyric-align 匹配率低（{matched}/{max(src_count, len(data))} 行），保留原歌词"


async def calibrate_align(
    audio_path: Path,
    lyric: Lyric,
    cfg: Config,
    force_model: str | None = None,
    language_hint: str = "",
    on_status: Callable[[str], Awaitable[None]] | None = None,
) -> Lyric | None:
    """lyric-align(faster-whisper) 强制对齐。

    语言自动检测：本地歌词字符 → 元数据 language → cfg.whisper_language。
    用 `-f json --interpolate` 拿每行 matched 标记；`_apply_alignment` 决定采用策略
    （高匹配用 interpolate 输出 / 中匹配锚点线性拟合 / 低匹配回退 None）。
    """
    exe = _align_exe()
    if not exe:
        lyric.warning = "未安装 lyric-align，装 `pip install -e '.[align]'` 后可用"
        return None
    model = force_model or cfg.whisper_model
    language = detect_lyric_language(lyric.text) or language_hint or cfg.whisper_language
    if on_status:
        resolved = resolve_model(cfg) if not force_model else {"used": model, "kind": "", "note": ""}
        await on_status(
            f"使用模型: {model}（{resolved['note']}），语言 {language}，正在转写..."
        )
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        lyrics_txt = tmp_dir / "lyrics.txt"
        lyrics_txt.write_text(plain_lines(lyric.text), encoding="utf-8")
        out_json = tmp_dir / "out.json"
        cmd = [
            exe, str(audio_path), str(lyrics_txt),
            "-o", str(out_json), "-f", "json",
            "--language", language,
            "--model", model,
            "--no-vad", "--interpolate",
        ]
        if cfg.vocal_separate:
            if importlib.util.find_spec("demucs"):
                cmd.append("--separate")
            else:
                print("⚠ vocal_separate 已开但未装 demucs，跳过人声分离（pip install -e '.[separate]'）")
        env = dict(os.environ)
        env.setdefault("PYTHONUTF8", "1")
        if cfg.hf_mirror:
            env.setdefault("HF_ENDPOINT", cfg.hf_mirror)
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE, env=env
        )

        tail_holder: list[str] = []

        async def _stream_stderr() -> str:
            """逐行读 stderr 步骤日志，回传 on_status；记录尾部供失败详情。"""
            tail = ""
            assert proc.stderr is not None
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                text = line.decode(errors="replace").strip()
                if text:
                    tail = (tail + "\n" + text)[-300:]
                    if on_status:
                        await on_status(text)
            tail_holder.append(tail)
            return tail

        stream_task = asyncio.create_task(_stream_stderr())
        try:
            await proc.wait()
        finally:
            stream_task.cancel()
            try:
                await stream_task
            except asyncio.CancelledError:
                pass
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
        if proc.returncode != 0 or not out_json.is_file():
            lyric.warning = f"lyric-align 失败: {(tail_holder[0] if tail_holder else '无输出')[-300:]}"
            return None
        try:
            data = json.loads(out_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            lyric.warning = "lyric-align 输出解析失败"
            return None

    method, new_text, warning = _apply_alignment(lyric, data)
    if new_text is None:
        lyric.warning = warning
        return None
    lyric.text = new_text
    lyric.calibrated = True
    lyric.calib_method = method
    lyric.warning = warning
    return lyric


async def calibrate(
    path: Path,
    lyric: Lyric,
    cfg: Config,
    force_align: bool = False,
    meta_language: str = "",
    on_status: Callable[[str], Awaitable[None]] | None = None,
) -> Lyric:
    """校准编排：已同步则直接返回；否则 lyric-align（可用时）；失败保留原歌词。"""
    duration = await probe_duration(path, cfg)

    if duration is None:
        if cfg.align_enabled and align_available():
            aligned = await calibrate_align(path, lyric, cfg, language_hint=meta_language, on_status=on_status)
            if aligned is not None:
                return aligned
        lyric.warning = "无法获取音频时长且歌词未校准（装 ffmpeg 或 [align] 可改善）"
        return lyric

    _, _, synced = calibrate_quick(lyric.text, duration)
    if synced:
        lyric.calibrated = True
        lyric.calib_method = "synced"
        lyric.warning = ""
        return lyric

    if cfg.align_enabled and align_available() and (force_align or not synced):
        aligned = await calibrate_align(path, lyric, cfg, language_hint=meta_language, on_status=on_status)
        if aligned is not None:
            return aligned

    lyric.calib_method = "source"
    lyric.warning = "歌词时间轴未校准，按原样保存（装 [align] 或用 --align 可对齐）"
    return lyric
