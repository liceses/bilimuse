"""SQLite 下载历史与去重。"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .config import default_config_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bvid TEXT NOT NULL,
    cid INTEGER NOT NULL,
    title TEXT,
    artist TEXT,
    album TEXT,
    format TEXT,
    file_path TEXT,
    status TEXT DEFAULT 'ok',
    created_at REAL,
    UNIQUE(bvid, cid)
);
"""


class DownloadDB:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_config_dir() / "downloads.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute(SCHEMA)
        self._conn.commit()

    def already_downloaded(self, bvid: str, cid: int) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM downloads WHERE bvid=? AND cid=? AND status='ok'", (bvid, cid)
        ).fetchone()
        return row is not None

    def add(
        self,
        bvid: str,
        cid: int,
        title: str,
        artist: str = "",
        album: str = "",
        format: str = "",
        file_path: str = "",
        status: str = "ok",
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO downloads "
            "(bvid, cid, title, artist, album, format, file_path, status, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (bvid, cid, title, artist, album, format, file_path, status, time.time()),
        )
        self._conn.commit()

    def list(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT bvid, cid, title, artist, format, file_path, created_at "
            "FROM downloads ORDER BY created_at DESC"
        ).fetchall()
        return [
            {
                "bvid": r[0],
                "cid": r[1],
                "title": r[2],
                "artist": r[3],
                "format": r[4],
                "file_path": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()
