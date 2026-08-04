"""CLI 入口：搜索、一键下载(get)、查看、历史、登录、环境诊断、TUI。"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

import typer

from .config import Config, default_config_dir
from .db import DownloadDB
from .providers.bilibili import BilibiliClient, BilibiliError
from .providers.meta import MiguMeta, NeteaseMeta
from .services.aligner import (
    WHISPER_SIZES,
    align_available,
    detect_models,
    download_model,
    faster_whisper_installed,
    resolve_model,
)
from .services.auth import LoginError, bili_login
from .services.pipeline import download_song_pipeline
from .services.search import search_versions
from .services.tagger import auto_tag

app = typer.Typer(add_completion=False)


@app.command()
def search(
    keyword: str = typer.Argument(..., help="搜索关键词（歌名/歌手）"),
    order: str = typer.Option("click", help="排序：totalrank/click/pubdate/dm"),
    limit: int = typer.Option(10, min=1, max=50),
    config: Path = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """在 B 站搜索音乐视频版本。"""
    cfg = Config.load(config)
    result = asyncio.run(_search(cfg, keyword, order, limit))
    for i, v in enumerate(result, 1):
        typer.echo(f"[{i}] {v.bvid} | {v.typename} | {v.duration}s | 播放{v.play} | {v.author}")
        typer.echo(f"    {v.title}")
        typer.echo(f"    cover: {v.pic}")


async def _search(cfg: Config, keyword: str, order: str, limit: int) -> list:
    async with BilibiliClient(cfg) as client:
        return await client.search_video(keyword, order=order, limit=limit)


@app.command()
def info(bvid: str = typer.Argument(...)) -> None:
    """查看视频详情与分 P。"""
    cfg = Config.load()
    result = asyncio.run(_info(cfg, bvid))
    d, pages = result
    typer.echo(f"{d.bvid} | {d.title}")
    typer.echo(f"author: {d.author} | cid: {d.cid} | duration: {d.duration}s")
    for p in pages:
        typer.echo(f"  P{p.page} cid={p.cid} {p.part} ({p.duration}s)")


async def _info(cfg: Config, bvid: str) -> tuple:
    async with BilibiliClient(cfg) as client:
        detail = await client.get_detail(bvid)
        pages = detail.pages or await client.get_pagelist(bvid)
        return detail, pages


@app.command()
def download(
    bvid: str = typer.Argument(..., help="BV 号"),
    page: int = typer.Option(1, "--page", "-p", min=1, help="分 P 序号（默认 1）"),
    out_format: str = typer.Option("", "--format", "-f", help="m4a/mp3/flac（默认用配置）"),
    no_tag: bool = typer.Option(False, "--no-tag", help="下载后不自动打标签"),
    no_lyric: bool = typer.Option(False, "--no-lyric", help="下载后不自动配歌词"),
    force_align: bool = typer.Option(False, "--align", help="歌词强制 lyric-align(whisper) 校准"),
    dir: Path = typer.Option(None, "--dir", "-d", help="下载目录（覆盖配置）"),
    config: Path = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """下载单个音频：自动反查元数据打标签、自动配歌词并校准。"""
    cfg = Config.load(config)
    if dir is not None:
        cfg.download_dir = dir
    if out_format:
        cfg.format = out_format
    try:
        result = asyncio.run(
            download_song_pipeline(
                cfg, bvid, page,
                on_event=_echo_events,
                no_tag=no_tag, no_lyric=no_lyric, force_align=force_align,
            )
        )
    except (BilibiliError, RuntimeError) as e:
        typer.echo(f"下载失败: {e}", err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"\n已保存: {result['path']}")
    if result["meta"]:
        typer.echo(f"标签: {result['meta'].artist_str} - {result['meta'].name}")
    if result["lyric"]:
        typer.echo(f"歌词: {result['lyric'].source}（{result['lyric'].calib_method}）")


@app.command()
def get(
    query: str = typer.Argument(..., help="歌名/歌手/歌词片段"),
    index: int = typer.Option(0, "--index", "-i", min=0, help="直接选第 N 条（1 起）；默认交互选择"),
    auto: bool = typer.Option(False, "--auto", help="自动选第一条"),
    page: int = typer.Option(1, "--page", "-p", min=1, help="分 P 序号"),
    out_format: str = typer.Option("", "--format", "-f", help="m4a/mp3/flac（默认用配置）"),
    no_tag: bool = typer.Option(False, "--no-tag", help="下载后不自动打标签"),
    no_lyric: bool = typer.Option(False, "--no-lyric", help="下载后不自动配歌词"),
    force_align: bool = typer.Option(False, "--align", help="歌词强制 lyric-align 校准"),
    dir: Path = typer.Option(None, "--dir", "-d", help="下载目录（覆盖配置）"),
    config: Path = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """一键闭环：搜索（含歌词反查）→ 选版本 → 下载 → 打标签 → 配歌词校准。"""
    cfg = Config.load(config)
    if dir is not None:
        cfg.download_dir = dir
    if out_format:
        cfg.format = out_format
    try:
        result = asyncio.run(_get(cfg, query, index, auto, page, no_tag, no_lyric, force_align))
    except (BilibiliError, RuntimeError) as e:
        typer.echo(f"失败: {e}", err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"\n已保存: {result['path']}")
    if result["meta"]:
        typer.echo(f"标签: {result['meta'].artist_str} - {result['meta'].name}")
    if result["lyric"]:
        typer.echo(f"歌词: {result['lyric'].source}（{result['lyric'].calib_method}）")


async def _echo_events(ev: dict) -> None:
    t = ev["type"]
    if t == "info":
        typer.echo(f"标题: {ev['title']}\nUP主: {ev['author']}")
    elif t == "progress":
        typer.echo(f"\r下载 {ev['pct']:3d}%", nl=False)
        if ev["pct"] >= 100:
            typer.echo()
    elif t in ("stage", "message"):
        if ev.get("text"):
            typer.echo(ev["text"])
    elif t == "meta":
        typer.echo(f"匹配来源: {ev['meta'].source}")
    elif t == "lyric":
        typer.echo(f"歌词: {ev['lyric'].source} → .lrc 已写入")
    elif t == "warning":
        typer.echo(ev["text"], err=True)


def _ask_index(count: int) -> int:
    while True:
        s = input(f"选择序号 (1-{count}，回车默认 1): ").strip()
        if not s:
            return 0
        try:
            n = int(s)
            if 1 <= n <= count:
                return n - 1
        except ValueError:
            pass
        typer.echo(f"请输入 1-{count}")


async def _get(
    cfg: Config, query: str, index: int, auto: bool, page: int, no_tag: bool, no_lyric: bool, force_align: bool
) -> dict:
    hits = await search_versions(cfg, query)
    if not hits:
        raise RuntimeError("未搜索到结果")
    for i, h in enumerate(hits, 1):
        v = h.version
        src = "歌词反查" if h.source == "lyric" else "直接搜索"
        typer.echo(f"[{i}] [{src}] {v.bvid} | {v.duration}s | 播放{v.play} | {v.author}")
        typer.echo(f"    {v.title}")
    if auto:
        sel = 0
    elif index >= 1:
        sel = index - 1
    else:
        sel = await asyncio.to_thread(_ask_index, len(hits))
    if not (0 <= sel < len(hits)):
        raise RuntimeError("无效选择")
    hit = hits[sel]
    typer.echo(f"选择: [{hit.source}] {hit.version.title}")
    return await download_song_pipeline(
        cfg, hit.version.bvid, page,
        on_event=_echo_events,
        no_tag=no_tag, no_lyric=no_lyric, force_align=force_align,
    )


@app.command()
def tui(config: Path = typer.Option(None, "--config", "-c", help="配置文件路径")) -> None:
    """Textual 交互式界面（需 pip install -e '.[tui]'）。"""
    try:
        from .tui import MusicalbiliApp
    except ImportError as e:
        typer.echo(f"需要安装 TUI 依赖: pip install -e '.[tui]'（{e}）", err=True)
        raise typer.Exit(code=1) from e
    MusicalbiliApp(config=config).run()


@app.command()
def list_downloads() -> None:
    """查看下载历史。"""
    db = DownloadDB()
    rows = db.list()
    if not rows:
        typer.echo("暂无下载记录")
        return
    for r in rows:
        typer.echo(f"{r['bvid']} | {r['artist']} - {r['title']} [{r['format']}] -> {r['file_path']}")
    db.close()


@app.command()
def tag(
    file: Path = typer.Argument(..., help="音频文件（mp3/m4a/flac）"),
    query: str = typer.Option("", "--query", "-q", help="反查关键词（默认用文件名）"),
    config: Path = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """按网易云反查为已有音频打标签。"""
    cfg = Config.load(config)
    if not file.is_file():
        raise typer.Exit(f"文件不存在: {file}")
    q = query or file.stem
    result = asyncio.run(_tag(cfg, file, q))
    new_path, meta = result
    if not meta:
        typer.echo("未匹配到网易云曲目", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"已打标签: {meta.name} - {meta.artist_str}")
    if new_path != file:
        typer.echo(f"已重命名: {new_path}")


async def _tag(cfg: Config, file: Path, query: str) -> tuple:
    async with MiguMeta(cfg) as migu, NeteaseMeta(cfg) as netease:
        return await auto_tag(file, query, [migu, netease], cfg)


@app.command()
def login(config: Path = typer.Option(None, "--config", "-c", help="配置文件路径")) -> None:
    """手机扫码登录 B 站，降低风控并解锁高音质。"""
    cfg = Config.load(config)
    typer.echo("请用 B 站手机 App 扫码...")
    try:
        sessdata = asyncio.run(bili_login(cfg))
    except LoginError as e:
        typer.echo(f"登录失败: {e}", err=True)
        raise typer.Exit(code=1) from e
    cfg.sessdata = sessdata
    cfg.save(config)
    typer.echo("登录成功，SESSDATA 已保存")


def _ask(prompt: str, default: str) -> str:
    s = input(f"{prompt}: ").strip()
    return s if s else default


def _ask_bool(prompt: str, default: bool) -> bool:
    s = input(f"{prompt} (y/n): ").strip().lower()
    if not s:
        return default
    return s in ("y", "yes", "是", "1", "true")


def _ask_list(prompt: str, default: list[str]) -> list[str]:
    s = input(f"{prompt} [{','.join(default)}]: ").strip()
    return [x.strip() for x in (s if s else ",".join(default)).split(",") if x.strip()]


model_app = typer.Typer(help="whisper 模型管理（检测/下载/设置）")
app.add_typer(model_app, name="model")


@model_app.command("list")
def model_list(config: Path = typer.Option(None, "--config", "-c", help="配置文件路径")) -> None:
    """列出检测到的模型与当前配置解析。"""
    cfg = Config.load(config)
    resolved = resolve_model(cfg)
    typer.echo(f"当前配置 whisper_model: {resolved['used'] or '(未配置)'} → {resolved['note']}")
    models = detect_models()
    if models:
        typer.echo("检测到模型:")
        for m in models:
            mark = "  <= 使用中" if resolved["used"] == m["name"] or str(Path(resolved["used"])).endswith(m["name"]) else ""
            typer.echo(f"  [{m['kind']}] {m['name']} ({m['size_mb']}MB) {m['path']}{mark}")
    else:
        typer.echo("未检测到本地/HF 缓存模型")
    typer.echo(f"可下载: {', '.join(WHISPER_SIZES)}（musicalbili model download <size>）")
    typer.echo(
        f"依赖: lyric-align={'已装' if align_available() else '未装'} | "
        f"faster-whisper={'已装' if faster_whisper_installed() else '未装'}"
    )


@model_app.command("download")
def model_download(
    size: str = typer.Argument(..., help="tiny/base/small/medium/large-v3-turbo"),
    source: str = typer.Option("modelscope", "--source", help="modelscope（国内快）或 hf"),
    no_set: bool = typer.Option(False, "--no-set", help="下载后不写入配置"),
    config: Path = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """从 ModelScope/HF 下载 whisper 模型到 models/。"""
    cfg = Config.load(config)
    dest = Path("models") / f"faster-whisper-{size}"

    async def status(text: str) -> None:
        typer.echo(text)

    try:
        asyncio.run(download_model(size, dest, source=source, hf_mirror=cfg.hf_mirror, on_status=status))
    except RuntimeError as e:
        typer.echo(f"下载失败: {e}", err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"下载完成: {dest}")
    if not no_set:
        cfg.whisper_model = str(dest)
        cfg.save(config)
        typer.echo(f"已写入配置 whisper_model = {dest}")


@model_app.command("set")
def model_set(
    model: str = typer.Argument(..., help="模型名(small/base...) 或本地路径"),
    config: Path = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """设置 whisper_model（名或本地路径）。"""
    cfg = Config.load(config)
    cfg.whisper_model = model
    cfg.save(config)
    typer.echo(f"whisper_model = {model}")


@app.command()
def config(config: Path = typer.Option(None, "--config", "-c", help="配置文件路径")) -> None:
    """交互式配置向导（免手编 config.json）。"""
    cfg = Config.load(config)
    typer.echo("=== MusicalBILI 配置向导（回车使用默认值）===")
    cfg.download_dir = Path(_ask(f"下载目录 [{cfg.download_dir}]", str(cfg.download_dir)))
    cfg.format = _ask(f"格式 (m4a/mp3/flac) [{cfg.format}]", cfg.format)
    cfg.lyric_sources = _ask_list("歌词源顺序", cfg.lyric_sources)
    cfg.align_enabled = _ask_bool(f"歌词精确校准(whisper) [{'开' if cfg.align_enabled else '关'}]", cfg.align_enabled)
    local_model = Path("models") / "faster-whisper-small"
    model_default = str(local_model) if local_model.is_dir() else cfg.whisper_model
    cfg.whisper_model = _ask(
        f"whisper 模型(名称或本地路径，检测到 {local_model} 可回车用) [{model_default}]",
        model_default,
    )
    if not cfg.sessdata and _ask_bool("扫码登录 B 站(降风控/高音质)? [n]", False):
        try:
            cfg.sessdata = asyncio.run(bili_login(cfg))
        except LoginError as e:
            typer.echo(f"登录失败，跳过: {e}", err=True)
    cfg.proxy = _ask(f"代理(留空跳过) [{cfg.proxy}]", cfg.proxy)

    cfg.save(config)
    saved = config or default_config_dir() / "config.json"
    typer.echo(f"\n已保存: {saved}")
    typer.echo(
        f"下载目录: {cfg.download_dir} | 格式: {cfg.format} | 歌词源: {','.join(cfg.lyric_sources)}"
    )
    typer.echo(
        f"校准: {'开' if cfg.align_enabled else '关'}({cfg.whisper_model}) "
        f"| 登录: {'是' if cfg.sessdata else '否'} | 代理: {cfg.proxy or '无'}"
    )


@app.command()
def logout(config: Path = typer.Option(None, "--config", "-c", help="配置文件路径")) -> None:
    """清除 B 站登录态。"""
    cfg = Config.load(config)
    cfg.sessdata = ""
    cfg.save(config)
    typer.echo("已退出登录")


@app.command()
def doctor(
    network: bool = typer.Option(False, "--network", help="联网探测各数据源连通性"),
    config: Path = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """检测运行环境：Python / ffmpeg / 登录态 / 接口连通性。"""
    cfg = Config.load(config)
    typer.echo(f"Python: {sys.version.split()[0]} (>=3.11 可用)")
    typer.echo(f"配置目录: {default_config_dir()}")
    typer.echo("B站登录态: " + ("已登录（SESSDATA 已配置）" if cfg.sessdata else "未登录（风控阈值更高，建议 musicalbili login）"))

    if cfg.ffmpeg_path:
        src = f"config.ffmpeg_path={cfg.ffmpeg_path}"
    elif shutil.which("ffmpeg"):
        src = f"系统 PATH: {shutil.which('ffmpeg')}"
    else:
        try:
            import imageio_ffmpeg

            src = f"imageio-ffmpeg 内置: {imageio_ffmpeg.get_ffmpeg_exe()}"
        except (ImportError, RuntimeError):
            src = ""
    if src:
        typer.echo(f"ffmpeg: 找到（{src}）")
    else:
        typer.echo(
            "ffmpeg: 未找到。m4a 不受影响；mp3/flac 需执行 "
            "`pip install -e '.[ffmpeg]'` 或安装系统 ffmpeg",
            err=True,
        )

    db = DownloadDB()
    count = len(db.list())
    db.close()
    typer.echo(f"下载历史: {count} 条")
    typer.echo(
        f"歌词校准: {'lyric-align 可用' if align_available() else '未装 lyric-align（pip install -e .[align]）'}"
        f" | faster-whisper: {'已装' if faster_whisper_installed() else '未装'}"
    )
    resolved = resolve_model(cfg)
    typer.echo(f"whisper 模型: {resolved['used'] or '(未配置)'}（{resolved['note']}）")
    models = detect_models()
    if models:
        typer.echo("已检测模型: " + ", ".join(f"{m['name']}({m['size_mb']}MB)" for m in models))
    else:
        typer.echo("未检测到本地/HF 缓存模型（musicalbili model download 可下载）")
    if cfg.hf_mirror:
        typer.echo(f"HF 镜像: {cfg.hf_mirror}")

    if network:
        typer.echo("-- 接口连通性探测 --")
        asyncio.run(_probe_sources(cfg))


async def _probe_sources(cfg: Config) -> None:
    async with BilibiliClient(cfg) as b:
        try:
            v = await b.search_video("晴天", limit=1)
            typer.echo(f"B站搜索: OK（{len(v)} 条）")
        except BilibiliError as e:
            typer.echo(f"B站搜索: 失败（{e}）", err=True)
    async with MiguMeta(cfg) as migu:
        try:
            m = await migu.search("周杰伦 晴天", limit=1)
            typer.echo(f"咪咕: OK（{len(m)} 条）")
        except Exception as e:  # noqa: BLE001
            typer.echo(f"咪咕: 失败（{e}）", err=True)
    async with NeteaseMeta(cfg) as netease:
        try:
            n = await netease.search("周杰伦 晴天", limit=1)
            typer.echo(f"网易云: OK（{len(n)} 条，源={n[0].source if n else '空'}）")
        except Exception as e:  # noqa: BLE001
            typer.echo(f"网易云: 失败（{e}）", err=True)
