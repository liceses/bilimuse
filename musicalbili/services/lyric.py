"""歌词获取（多源降级）+ LRC 解析/清理/翻译合并。"""

from __future__ import annotations

import re

import httpx

from ..config import Config
from ..models import Lyric, SongMeta
from .tagger import pick_best

LRCLIB = "https://lrclib.net/api"

_LRC_TIME_RE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_OFFSET_RE = re.compile(r"\[offset:\s*([+-]?\d+)\s*\]")
_META_HEADER_RE = re.compile(
    r"^(作词|作曲|编曲|制作人|录音师|录音室|混音工程师|混音录音室|母带|母带工程师|监制|词曲|OP|SP)\s*[:：]"
)
_LIVE_TITLE_RE = re.compile(r"[（(].*live\s*\d*[)）]", re.IGNORECASE)


def clean_lrc(text: str) -> str:
    """清理：空行、以及开头 <5s 的标题标记行（如 '搁浅(live04)'）。"""
    kept = [line for line in text.splitlines() if _LRC_TIME_RE.sub("", line).strip()]
    if kept:
        times = _LRC_TIME_RE.findall(kept[0])
        content = _LRC_TIME_RE.sub("", kept[0]).strip()
        if times and len(content) <= 15 and _LIVE_TITLE_RE.search(content):
            kept.pop(0)
    return "\n".join(kept)


def parse_lrc(text: str) -> list[tuple[float, str]]:
    """解析 LRC → [(秒, 文本)]；支持 [offset:]、多时间戳单行。"""
    offset_ms = 0
    lines: list[tuple[float, str]] = []
    for raw in text.splitlines():
        times = _LRC_TIME_RE.findall(raw)
        if not times:
            m = _OFFSET_RE.match(raw.strip())
            if m:
                offset_ms = int(m.group(1))
            continue
        content = _LRC_TIME_RE.sub("", raw).strip()
        for mm, ss, ff in times:
            ms = int(mm) * 60000 + int(ss) * 1000 + int((ff or "0")[:3].ljust(3, "0"))
            lines.append((ms / 1000.0 + offset_ms / 1000.0, content))
    return lines


def render_lrc(lines: list[tuple[float, str]]) -> str:
    out = []
    for t, text in lines:
        mm, ss = int(t) // 60, int(t) % 60
        cs = round((t - int(t)) * 100)
        out.append(f"[{mm:02d}:{ss:02d}.{cs:02d}]{text}")
    return "\n".join(out) + "\n"


def clean_netease(text: str) -> str:
    """去掉网易云 LRC 的作曲/编曲元数据头、空内容行、以及无时间戳的元数据行（[by:/[al:]/[ti:] 等）。"""
    kept = []
    for line in text.splitlines():
        content = _LRC_TIME_RE.sub("", line).strip()
        if not content:
            continue
        if not _LRC_TIME_RE.search(line) and not _OFFSET_RE.match(line.strip()):
            continue
        if _META_HEADER_RE.match(content):
            continue
        kept.append(line)
    return "\n".join(kept)


def merge_translation(text: str, tlyric: str) -> str:
    """合并原文+译文：每个时间戳的原文行后紧跟译文行。"""
    orig = parse_lrc(text)
    trans = parse_lrc(tlyric)
    if not trans:
        return text
    tmap: dict[float, str] = {}
    for t, tx in trans:
        tmap.setdefault(t, tx)
    used: set[float] = set()
    merged: list[tuple[float, str]] = []
    for t, tx in orig:
        merged.append((t, tx))
        for tt, trans_text in tmap.items():
            if tt not in used and abs(tt - t) <= 0.5:
                merged.append((tt, trans_text))
                used.add(tt)
                break
    return render_lrc(merged)


def merge_translation_after(text: str, tlyric: str) -> str:
    """校准后合并：译文按行序跟在原文行后（沿用原文行的时间戳）。

    校准可能整体变换原文时间戳，译文时间戳不再匹配，改用行序配对。
    """
    orig = parse_lrc(text)
    trans = parse_lrc(tlyric)
    if not trans:
        return text
    merged: list[tuple[float, str]] = []
    ti = 0
    for t, tx in orig:
        merged.append((t, tx))
        if ti < len(trans):
            merged.append((t, trans[ti][1]))
            ti += 1
    return render_lrc(merged)


def plain_lines(text: str) -> str:
    """提取纯文本歌词行（用于 lyric-align 输入）。"""
    return "\n".join(tx for _, tx in parse_lrc(text))


async def fetch_lyrics(cfg: Config, meta: SongMeta | None, query: str, bvid: str, cid: int) -> Lyric | None:
    """按配置源顺序降级获取歌词；外文歌追加网易云双语增强。"""
    lyric: Lyric | None = None
    for source in cfg.lyric_sources:
        try:
            if source == "lrclib":
                lyric = await _from_lrclib(cfg, meta, query)
            elif source == "netease":
                lyric = await _from_netease(cfg, meta, query)
            elif source == "bilibili":
                lyric = await _from_bilibili(cfg, bvid, cid)
            else:
                continue
        except Exception:  # noqa: BLE001, S112 - 单源失败继续降级
            continue
        if lyric:
            break
    if lyric and cfg.translation_enabled and lyric.source != "netease":
        lang = detect_lyric_language(lyric.text)
        if lang and lang != "zh":
            try:
                bilingual = await _from_netease_bilingual(cfg, meta, query)
            except Exception:  # noqa: BLE001 - 译文增强失败不阻断
                bilingual = None
            if bilingual:
                return bilingual
    return lyric


async def _from_lrclib(cfg: Config, meta: SongMeta | None, query: str) -> Lyric | None:
    async with httpx.AsyncClient(
        headers={"User-Agent": cfg.ua},
        timeout=httpx.Timeout(20.0, connect=10.0),
        trust_env=False,
        proxy=cfg.proxy or None,
    ) as client:
        if meta:
            params: dict = {"track_name": meta.name}
            if meta.artists:
                params["artist_name"] = meta.artists[0]
            if meta.duration_ms:
                params["duration"] = round(meta.duration_ms / 1000, 1)
            r = await client.get(f"{LRCLIB}/get", params=params)
            if r.status_code == 200:
                return _from_lrclib_data(r.json())
        r = await client.get(f"{LRCLIB}/search", params={"q": query})
        if r.status_code == 200:
            for item in r.json()[:5]:
                lyric = _from_lrclib_data(item)
                if lyric:
                    return lyric
    return None


def _from_lrclib_data(data: dict) -> Lyric | None:
    text = data.get("syncedLyrics") or data.get("plainLyrics") or ""
    if not text:
        return None
    return Lyric(source="lrclib", text=clean_lrc(text))


async def _netease_song_id(netease, meta: SongMeta | None, query: str):
    """反查网易云歌曲 id：meta 已带则直接用，否则搜索+匹配。"""
    if meta and meta.source == "netease" and meta.id:
        return meta.id
    songs = await netease.search(query, limit=10)
    song = pick_best(songs, query) if songs else None
    return song.id if song else None


async def _from_netease(cfg: Config, meta: SongMeta | None, query: str) -> Lyric | None:
    from ..providers.meta import NeteaseMeta

    async with NeteaseMeta(cfg) as netease:
        song_id = await _netease_song_id(netease, meta, query)
        if not song_id:
            return None
        lrc_text, tlyric = await netease.get_lyric(song_id)
    lrc_text = clean_netease(lrc_text)
    if not lrc_text.strip():
        return None
    return Lyric(source="netease", text=lrc_text, tlyric=clean_netease(tlyric))


async def _from_netease_bilingual(cfg: Config, meta: SongMeta | None, query: str) -> Lyric | None:
    """网易云双语对：返回原始 lrc + tlyric（合并由调用方统一 merge_translation）。"""
    from ..providers.meta import NeteaseMeta

    async with NeteaseMeta(cfg) as netease:
        song_id = await _netease_song_id(netease, meta, query)
        if not song_id:
            return None
        lrc_text, tlyric = await netease.get_lyric(song_id)
    lrc_text = clean_netease(lrc_text)
    tlyric = clean_netease(tlyric)
    if not lrc_text.strip() or not tlyric.strip():
        return None
    return Lyric(source="netease", text=lrc_text, tlyric=tlyric)


async def _from_bilibili(cfg: Config, bvid: str, cid: int) -> Lyric | None:
    if not cfg.sessdata:
        return None
    from ..providers.bilibili import BilibiliClient

    async with BilibiliClient(cfg) as client:
        lines = await client.get_subtitles(bvid, cid)
    if not lines:
        return None
    return Lyric(source="bilibili", text=render_lrc(lines))


def placeholder_lyric() -> Lyric:
    """纯音乐/无歌词占位。"""
    return Lyric(source="placeholder", text="[00:00.00]纯音乐，请欣赏\n")


_KANA = re.compile(r"[\u3040-\u30ff]")
_HANGUL = re.compile(r"[\uac00-\ud7af]")
_HANZI = re.compile(r"[\u4e00-\u9fff]")
_CYRILLIC = re.compile(r"[\u0400-\u04ff]")
_LATIN = re.compile(r"[A-Za-z]")


def detect_lyric_language(text: str) -> str:
    """从歌词文本检测 whisper 语言码：ja/zh/ko/ru/en，未知返回空串。

    假名只存在于日语（决定性地优先），其次谚文/汉字/西里尔/拉丁。
    """
    if _KANA.search(text):
        return "ja"
    if _HANGUL.search(text):
        return "ko"
    if _HANZI.search(text):
        return "zh"
    if _CYRILLIC.search(text):
        return "ru"
    if len(_LATIN.findall(text)) > 20:
        return "en"
    return ""
