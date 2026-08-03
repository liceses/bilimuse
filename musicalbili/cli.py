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
from .services.download import download_song

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
    dir: Path = typer.Option(None, "--dir", "-d", help="下载目录（覆盖配置）"),
    config: Path = typer.Option(None, "--config", "-c", help="配置文件路径"),
) -> None:
    """下载单个音频并记录到历史库。"""
    cfg = Config.load(config)
    if dir is not None:
        cfg.download_dir = dir
    if out_format:
        cfg.format = out_format
    db = DownloadDB()
    try:
        path = asyncio.run(_download(cfg, db, bvid, page))
    except (BilibiliError, RuntimeError) as e:
        typer.echo(f"下载失败: {e}", err=True)
        raise typer.Exit(code=1) from e
    typer.echo(f"\n已保存: {path}")
    db.close()


async def _download(cfg: Config, db: DownloadDB, bvid: str, page: int) -> Path:
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
    db.add(bvid=bvid, cid=cid, title=title, artist=detail.author, format=path.suffix.lstrip("."), file_path=str(path))
    return path


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
def doctor() -> None:
    """检测运行环境：Python / ffmpeg / 配置目录。"""
    cfg = Config.load()
    typer.echo(f"Python: {sys.version.split()[0]} (>=3.11 可用)")
    typer.echo(f"配置目录: {default_config_dir()}")

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
