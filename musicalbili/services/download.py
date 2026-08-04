"""DASH 音频下载、转码与命名。"""

from __future__ import annotations

import asyncio
import re
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from ..config import Config
from ..models import AudioStream, PlayInfo
from ..providers.bilibili import BilibiliClient

ProgressCb = Callable[[int, int], Awaitable[None]] | None

_ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]')


def sanitize_filename(name: str) -> str:
    """去除 Windows 非法文件名字符。"""
    return _ILLEGAL.sub("_", name).strip(". ") or "untitled"


def render_filename(template: str, artist: str, title: str, ext: str) -> str:
    name = template.format(artist=artist, title=title, ext=ext)
    return sanitize_filename(name)


def find_ffmpeg(cfg: Config | None = None) -> str | None:
    """三级回退查找 ffmpeg：config.ffmpeg_path → 系统 PATH → imageio-ffmpeg 内置。

    imageio-ffmpeg 为可选 extra，懒加载：未安装时不报错（仅 mp3/flac 需要时报错）。
    """
    cfg = cfg or Config.load()
    if cfg.ffmpeg_path:
        return cfg.ffmpeg_path
    if exe := shutil.which("ffmpeg"):
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return None


async def download_stream(url: str, dest: Path, ua: str, progress: ProgressCb = None) -> None:
    """流式下载到临时 .part 再原子改名，支持进度回调。"""
    headers = {"User-Agent": ua, "Referer": "https://www.bilibili.com/"}
    part = dest.with_suffix(dest.suffix + ".part")
    async with (
        httpx.AsyncClient(headers=headers, trust_env=False, timeout=httpx.Timeout(30, read=120)) as client,
        client.stream("GET", url) as r,
    ):
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with part.open("wb") as f:
            async for chunk in r.aiter_bytes():
                f.write(chunk)
                done += len(chunk)
                if progress:
                    await progress(done, total)
    part.replace(dest)


async def convert_audio(ffmpeg: str, src: Path, dst: Path, codec: str) -> None:
    """ffmpeg 转码/封装。codec: 'mp3' 或 'copy'（flac 源重封装）。"""
    args = [ffmpeg, "-y", "-loglevel", "error", "-i", str(src), "-c:a", codec, str(dst)]
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
    )
    try:
        _, stderr = await proc.communicate()
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 转码失败: {stderr.decode(errors='replace')}")


async def download_song(
    bvid: str,
    cid: int,
    *,
    cfg: Config,
    title: str = "",
    artist: str = "",
    fmt: str | None = None,
    progress: ProgressCb = None,
) -> Path:
    """一键下载单个音频文件，返回最终路径。"""
    fmt = fmt or cfg.format
    if fmt not in ("m4a", "mp3", "flac"):
        raise ValueError(f"不支持的格式: {fmt}")

    async with BilibiliClient(cfg) as bclient:
        detail = await bclient.get_detail(bvid)
        play = await bclient.get_play_info(bvid, cid)
        target_ext, stream, need_convert = _decide(play, fmt, bclient)

        artist = artist or detail.author
        title = title or detail.title
        dest_dir = cfg.download_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / render_filename(cfg.filename_template, artist, title, target_ext)

        ffmpeg = find_ffmpeg(cfg)
        if need_convert and not ffmpeg:
            raise RuntimeError(
                f"{fmt} 需要 ffmpeg 但未找到。可选安装方式："
                "① pip install -e '.[ffmpeg]'（内嵌，推荐）"
                "② 安装系统 ffmpeg ③ 在配置中设置 ffmpeg_path；或改用 m4a 格式"
            )

        raw = dest_dir / f"{bvid}_{cid}.m4s"
        try:
            await download_stream(stream.base_url, raw, cfg.ua, progress)
            if need_convert:
                await convert_audio(ffmpeg, raw, dest, "mp3" if target_ext == "mp3" else "copy")
                raw.unlink(missing_ok=True)
            else:
                raw.replace(dest)
        finally:
            raw.unlink(missing_ok=True)
        return dest


def _decide(
    play: PlayInfo, fmt: str, bclient: BilibiliClient
) -> tuple[str, AudioStream, bool]:
    """决定目标扩展名、音轨与是否转码。返回 (ext, stream, need_convert)。"""
    if fmt == "flac":
        if play.flac:
            return "flac", play.flac, True  # 真无损，ffmpeg copy 重封装
        print("⚠ 无 flac 音源（需大会员），降级为 m4a")
        return "m4a", bclient.pick_audio(play), False
    if fmt == "m4a":
        return "m4a", bclient.pick_audio(play), False
    return "mp3", bclient.pick_audio(play), True
