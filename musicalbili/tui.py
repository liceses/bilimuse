"""Textual TUI：搜索 → 结果表 → 选中下载 → 日志面板。"""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Footer, Header, Input, Static

from .config import Config
from .services.pipeline import download_song_pipeline
from .services.search import SearchHit, search_versions


class MusicalbiliApp(App):
    TITLE = "MusicalBILI"

    def __init__(self, config: Path | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.cfg = Config.load(config)
        self.hits: list[SearchHit] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder="输入歌名/歌手/歌词片段，回车搜索")
        yield DataTable(id="results")
        yield Static(id="log", expand=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("来源", "BV号", "时长", "播放", "UP主", "标题")
        table.cursor_type = "row"

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        self.query_one(Input).disabled = True
        self.notify("搜索中...")
        self.run_worker(self.do_search(event.value))

    async def do_search(self, query: str) -> None:
        log = self.query_one("#log", Static)
        try:
            self.hits = await search_versions(self.cfg, query)
        except Exception as e:  # noqa: BLE001
            log.update(f"搜索失败: {e}")
            self.query_one(Input).disabled = False
            return
        table = self.query_one(DataTable)
        table.clear()
        for h in self.hits:
            v = h.version
            table.add_row(
                "歌词反查" if h.source == "lyric" else "直接",
                v.bvid, f"{v.duration}s", str(v.play), v.author, v.title,
            )
        log.update(f"共 {len(self.hits)} 条，↑↓ 选择后回车下载")
        self.query_one(Input).disabled = False

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        try:
            idx = int(event.row_key.value) - 1
        except (TypeError, ValueError):
            return
        if not (0 <= idx < len(self.hits)):
            return
        hit = self.hits[idx]
        self.query_one(DataTable).disabled = True
        self.notify(f"开始下载: {hit.version.title}")
        self.run_worker(self.do_download(hit))

    async def do_download(self, hit: SearchHit) -> None:
        log = self.query_one("#log", Static)
        log.update(f"下载: {hit.version.title}\n{hit.version.bvid}")
        try:
            result = await download_song_pipeline(self.cfg, hit.version.bvid, on_event=self._log_event)
        except Exception as e:  # noqa: BLE001
            log.update(f"失败: {e}")
            self.query_one(DataTable).disabled = False
            return
        meta = result["meta"]
        lyric = result["lyric"]
        parts = [f"完成: {result['path']}"]
        if meta:
            parts.append(f"标签: {meta.artist_str} - {meta.name}")
        if lyric:
            parts.append(f"歌词: {lyric.source}（{lyric.calib_method}）")
        log.update("\n".join(parts))
        self.query_one(DataTable).disabled = False

    async def _log_event(self, ev: dict) -> None:
        log = self.query_one("#log", Static)
        t = ev["type"]
        if t == "info":
            log.update(f"标题: {ev['title']}\nUP主: {ev['author']}")
        elif t == "progress":
            log.update(f"下载 {ev['pct']}%")
        elif t == "message":
            log.update(ev["text"])
        elif t == "meta":
            m = ev["meta"]
            log.update(f"匹配来源: {m.source} → {m.artist_str} - {m.name}")
        elif t == "lyric":
            log.update(f"歌词: {ev['lyric'].source} → .lrc 已写入")
        elif t == "warning":
            log.update(ev["text"])
