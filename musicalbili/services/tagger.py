"""mutagen 打标签 + 网易云自动打标签闭环。"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, USLT, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover

from ..config import Config
from ..models import SongMeta
from .download import render_filename

_BRACKETS = re.compile(r"[【\[][^】\]]*[】\]]")
_PARENS = re.compile(r"[（(][^）)]*[)）]")
_STRIP_CHARS = " \t，,。！!：: -–"
_TRAILING_TOKENS = (
    "高清修复版", "修复版", "完整版", "剪辑版", "现场版", "LIVE版", "live版",
    "MV", "PV", "mv", "pv", "翻唱", "现场", "Live", "live", "修复", "高清修复",
    "4K", "2160P", "1080P", "720P", "超清", "高清", "动态歌词", "歌词", "字幕",
    "纯音乐", "音效", "伴奏", "合唱",
)


def clean_title(title: str) -> str:
    """清洗 B 站视频标题为可搜索关键词。"""
    t = _BRACKETS.sub(" ", title)
    t = _PARENS.sub(" ", t)
    changed = True
    while changed:
        changed = False
        for tok in sorted(_TRAILING_TOKENS, key=len, reverse=True):
            if t.endswith(tok):
                t = t[: -len(tok)]
                changed = True
        t = t.rstrip(" -–·　")
    return t.strip(" -–·　")


def split_query(query: str) -> tuple[str, str]:
    """把查询拆成 (歌手, 歌名)。

    优先提取《》/「」内歌名（周杰伦《七里香》/宇多田ヒカル「One Last Kiss」），
    其次 '歌手 - 歌名'，最后纯歌名。
    """
    q = clean_title(query)
    m = re.search(r"[《「]([^》」]+)[》」]", q)
    if m:
        title = m.group(1)
        artist = q[: m.start()].strip(_STRIP_CHARS)
        return artist, title
    parts = re.split(r"\s*[-–—]\s*", q, maxsplit=1)
    if len(parts) == 2 and parts[1]:
        return parts[0].strip(_STRIP_CHARS), parts[1].strip(_STRIP_CHARS)
    return "", q


def _norm_artist(a: str) -> str:
    return re.sub(r"[\s.\-、，'`_~]+$", "", a)


def pick_best(songs: list[SongMeta], query: str) -> SongMeta | None:
    """按歌名相似度 + 歌手命中评分，低于阈值返回 None。"""
    artist, title = split_query(query)
    if not title:
        return None
    best, best_score = None, 0.0
    for s in songs:
        name = clean_title(s.name)
        score = SequenceMatcher(None, name, title).ratio()
        if name and name in title:
            score = max(score, len(name) / max(len(title), 1) * 0.95)
        elif title and title in name:
            score = max(score, len(title) / max(len(name), 1) * 0.95)
        if artist and s.artists:
            hits = any(
                _norm_artist(a) == _norm_artist(artist)
                or (_norm_artist(a) and _norm_artist(a) in _norm_artist(artist))
                for a in s.artists
            )
            score += 0.3 if hits else -0.4
        if score > best_score:
            best, best_score = s, score
    return best if best_score >= 0.5 else None


def _image_format(data: bytes) -> tuple[str, object]:
    """返回 (mime, mutagen 格式标志)。"""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", "png"
    return "image/jpeg", "jpg"


def _tag_mp3(path: Path, meta: SongMeta, cover: bytes | None, lyrics: str | None) -> None:
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.add(TIT2(encoding=3, text=meta.name))
    tags.add(TPE1(encoding=3, text=meta.artist_str))
    tags.add(TALB(encoding=3, text=meta.album))
    if lyrics:
        tags.add(USLT(encoding=3, text=lyrics))
    if cover:
        mime, _ = _image_format(cover)
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=cover))
    tags.save(path)


def _tag_m4a(path: Path, meta: SongMeta, cover: bytes | None, lyrics: str | None) -> None:
    audio = MP4(path)
    audio["\xa9nam"] = [meta.name]
    audio["\xa9ART"] = [meta.artist_str]
    audio["\xa9alb"] = [meta.album]
    if lyrics:
        audio["\xa9lyr"] = [lyrics]
    if cover:
        _, fmt = _image_format(cover)
        kind = MP4Cover.FORMAT_PNG if fmt == "png" else MP4Cover.FORMAT_JPEG
        audio["covr"] = [MP4Cover(cover, imageformat=kind)]
    audio.save()


def _tag_flac(path: Path, meta: SongMeta, cover: bytes | None, lyrics: str | None) -> None:
    audio = FLAC(path)
    audio["title"] = meta.name
    audio["artist"] = meta.artist_str
    audio["album"] = meta.album
    if lyrics:
        audio["lyrics"] = lyrics
    if cover:
        mime, fmt = _image_format(cover)
        pic = Picture()
        pic.type = 3
        pic.mime = mime
        pic.desc = "Cover"
        pic.data = cover
        if fmt == "png":
            pic.width = pic.height = 0
        audio.add_picture(pic)
    audio.save()


def tag_file(path: Path, meta: SongMeta, cover: bytes | None = None, lyrics: str | None = None) -> None:
    """按扩展名写入标签。"""
    ext = path.suffix.lower()
    if ext == ".mp3":
        _tag_mp3(path, meta, cover, lyrics)
    elif ext in (".m4a", ".m4b", ".mp4"):
        _tag_m4a(path, meta, cover, lyrics)
    elif ext == ".flac":
        _tag_flac(path, meta, cover, lyrics)
    else:
        raise ValueError(f"不支持的标签格式: {ext}")


async def search_metadata(query: str, providers: list) -> tuple[object | None, SongMeta | None]:
    """按源顺序反查，返回首个命中阈值的数据源及其候选。"""
    for provider in providers:
        try:
            songs = await provider.search(query)
        except Exception:  # noqa: BLE001, S112 - 单源失败不阻断其他源
            continue
        song = pick_best(songs, query)
        if song:
            return provider, song
    return None, None


async def auto_tag(path: Path, query: str, providers: list, cfg: Config, fallback_artist: str = "") -> tuple[Path | None, SongMeta | None]:
    """多源反查 → 打标签 → 重命名。返回 (新路径, 元数据)；无匹配返回 (None, None)。"""
    provider, song = await search_metadata(query, providers)
    if not song:
        return None, None
    cover = await provider.fetch_cover_bytes(song)
    tag_file(path, song, cover)
    artist = song.artist_str if song.artists else fallback_artist
    new = path.with_name(render_filename(cfg.filename_template, artist, song.name, path.suffix.lstrip(".")))
    if new != path:
        path.replace(new)
    return new, song
