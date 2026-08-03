"""CLI 入口：搜索、查看、下载、历史、环境诊断。"""

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
from .services.auth import LoginError, bili_login
from .services.download import download_song
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
    dir: Path = typer.Option(None, "--dir", "-d", help="下载目录（覆盖配置）"),
    config: Path = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """下载单个音频，自动反查元数据打标签并记录历史。"""
    cfg = Config.load(config)
    if dir is not None:
        cfg.download_dir = dir
    if out_format:
        cfg.format = out_format
    db = DownloadDB()
    try:
        path, meta = asyncio.run(_download(cfg, db, bvid, page, no_tag))
    except (BilibiliError, RuntimeError) as e:
        typer.echo(f"下载失败: {e}", err=True)
        raise typer.Exit(code=1) from e
    label = f"{meta.artist_str} - {meta.name}" if meta else str(path)
    typer.echo(f"\n已保存: {path}")
    if meta:
        typer.echo(f"标签: {label}")
    db.close()


async def _download(cfg: Config, db: DownloadDB, bvid: str, page: int, no_tag: bool) -> tuple:
    async with BilibiliClient(cfg) as client:
        detail = await client.get_detail(bvid)
        pages = detail.pages or await client.get_pagelist(bvid)
        if pages:
            selected = pages[page - 1]
            cid = selected.cid
            title = selected.part if len(pages) > 1 else detail.title
        else:
            cid = detail.cid
            title = detail.title

    if db.already_downloaded(bvid, cid):
        raise RuntimeError(f"{bvid} 的 P{page}(cid={cid}) 已下载过，跳过（去重）")

    typer.echo(f"标题: {title}\nUP主: {detail.author}")
    state = {"last": -1}

    async def progress(done: int, total: int) -> None:
        if total <= 0:
            return
        pct = done * 100 // total
        if pct != state["last"]:
            state["last"] = pct
            typer.echo(f"\r下载 {pct:3d}%", nl=False)
        if done >= total:
            typer.echo()

    path = await download_song(
        bvid, cid, cfg=cfg, title=title, artist=detail.author, fmt=cfg.format, progress=progress
    )
    meta = None
    if not no_tag:
        typer.echo("反查元数据并打标签...")
        async with MiguMeta(cfg) as migu, NeteaseMeta(cfg) as netease:
            new_path, meta = await auto_tag(path, title, [migu, netease], cfg, fallback_artist=detail.author)
        if meta:
            path = new_path
            typer.echo(f"匹配来源: {meta.source}")
        else:
            typer.echo("未匹配到曲目，保留原始命名", err=True)
    db.add(
        bvid=bvid,
        cid=cid,
        title=meta.name if meta else title,
        artist=meta.artist_str if meta else detail.author,
        format=path.suffix.lstrip("."),
        file_path=str(path),
    )
    return path, meta


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
