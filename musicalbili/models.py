"""领域数据模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class VideoVersion(BaseModel):
    """B 站候选版本（一个视频 = 一个版本）。"""

    bvid: str
    title: str
    author: str
    author_mid: int
    pic: str
    duration: int = Field(description="时长（秒）")
    play: int = 0
    tid: int = 0
    typename: str = ""


class VideoDetail(BaseModel):
    """视频详情（含 cid 与分 P）。"""

    bvid: str
    title: str
    author: str
    author_mid: int
    pic: str
    cid: int
    duration: int = 0
    pages: list[VideoPage] = []


class VideoPage(BaseModel):
    """分 P 信息。"""

    cid: int
    page: int
    part: str
    duration: int


class AudioStream(BaseModel):
    """一个 DASH 音频轨。"""

    id: int
    base_url: str
    bandwidth: int = 0
    codecs: str = ""
    mime_type: str = ""


class PlayInfo(BaseModel):
    """播放地址结果。"""

    dash_audio: list[AudioStream] = []
    flac: AudioStream | None = None
    dolby: AudioStream | None = None
    video_title: str = ""


class SongMeta(BaseModel):
    """真实歌曲元数据（来自网易云/咪咕等反查）。"""

    source: str = ""
    id: int | str = 0
    name: str
    artists: list[str] = []
    album: str = ""
    duration_ms: int = 0
    cover: str = ""

    @property
    def artist_str(self) -> str:
        return " / ".join(self.artists) if self.artists else "Unknown"
