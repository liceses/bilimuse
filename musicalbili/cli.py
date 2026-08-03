"""CLI 入口：搜索 B 站音乐版本并展示。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from .config import Config
from .providers.bilibili import BilibiliClient

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
