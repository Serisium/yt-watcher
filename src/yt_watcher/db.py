"""Local SQLite mirror of the playlist — the single source of truth for download state."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yt_watcher.poller import PlaylistEntry, PlaylistSnapshot

MAX_RETRIES = 5

_SCHEMA_V1 = """
CREATE TABLE playlist (
    yt_id TEXT PRIMARY KEY,
    title TEXT,
    channel TEXT,
    channel_id TEXT,
    description TEXT,
    last_polled_at TEXT,
    created_at TEXT
);
CREATE TABLE videos (
    yt_id TEXT PRIMARY KEY,
    playlist_id TEXT REFERENCES playlist(yt_id),
    title TEXT,
    upload_date TEXT,
    duration_s INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    error_msg TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    height INTEGER,
    vcodec TEXT,
    acodec TEXT,
    filesize INTEGER,
    file_path TEXT,
    in_playlist INTEGER NOT NULL DEFAULT 1,
    first_seen_at TEXT,
    downloaded_at TEXT,
    updated_at TEXT
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str):
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version < 1:
            with self._conn:
                self._conn.executescript(_SCHEMA_V1)
                self._conn.execute("PRAGMA user_version = 1")

    def upsert_playlist(self, snapshot: PlaylistSnapshot) -> None:
        now = _now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO playlist (yt_id, title, channel, channel_id, description,
                                      last_polled_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(yt_id) DO UPDATE SET
                    title = excluded.title,
                    channel = excluded.channel,
                    channel_id = excluded.channel_id,
                    description = excluded.description,
                    last_polled_at = excluded.last_polled_at
                """,
                (
                    snapshot.yt_id,
                    snapshot.title,
                    snapshot.channel,
                    snapshot.channel_id,
                    snapshot.description,
                    now,
                    now,
                ),
            )

    def record_seen(self, playlist_id: str, entries: Iterable[PlaylistEntry]) -> list[str]:
        """Sync playlist membership into the videos table.

        Returns the ids of videos never seen before. Videos that dropped out of the
        playlist are flagged in_playlist=0; their rows and files are kept forever.
        """
        entries = list(entries)
        now = _now()
        new_ids: list[str] = []
        with self._conn:
            for entry in entries:
                cur = self._conn.execute(
                    """
                    UPDATE videos SET title = ?, in_playlist = 1, updated_at = ?
                    WHERE yt_id = ?
                    """,
                    (entry.title, now, entry.yt_id),
                )
                if cur.rowcount == 0:
                    self._conn.execute(
                        """
                        INSERT INTO videos (yt_id, playlist_id, title, status, in_playlist,
                                            first_seen_at, updated_at)
                        VALUES (?, ?, ?, 'pending', 1, ?, ?)
                        """,
                        (entry.yt_id, playlist_id, entry.title, now, now),
                    )
                    new_ids.append(entry.yt_id)
            current_ids = [e.yt_id for e in entries]
            placeholders = ",".join("?" for _ in current_ids) or "''"
            self._conn.execute(
                f"""
                UPDATE videos SET in_playlist = 0, updated_at = ?
                WHERE playlist_id = ? AND in_playlist = 1
                  AND yt_id NOT IN ({placeholders})
                """,
                (now, playlist_id, *current_ids),
            )
        return new_ids

    def videos_to_download(self, playlist_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT * FROM videos
            WHERE playlist_id = ?
              AND (status = 'pending' OR (status = 'error' AND retry_count < ?))
            ORDER BY first_seen_at, yt_id
            """,
            (playlist_id, MAX_RETRIES),
        ).fetchall()

    def mark_downloaded(
        self,
        yt_id: str,
        *,
        file_path: str,
        height: int | None,
        vcodec: str | None,
        acodec: str | None,
        filesize: int | None,
        title: str | None = None,
        upload_date: str | None = None,
        duration_s: int | None = None,
    ) -> None:
        now = _now()
        with self._conn:
            self._conn.execute(
                """
                UPDATE videos SET
                    status = 'downloaded', error_msg = NULL,
                    file_path = ?, height = ?, vcodec = ?, acodec = ?, filesize = ?,
                    title = COALESCE(?, title),
                    upload_date = COALESCE(?, upload_date),
                    duration_s = COALESCE(?, duration_s),
                    downloaded_at = ?, updated_at = ?
                WHERE yt_id = ?
                """,
                (
                    file_path,
                    height,
                    vcodec,
                    acodec,
                    filesize,
                    title,
                    upload_date,
                    duration_s,
                    now,
                    now,
                    yt_id,
                ),
            )

    def mark_failed(self, yt_id: str, message: str, *, unavailable: bool) -> None:
        now = _now()
        status = "unavailable" if unavailable else "error"
        with self._conn:
            self._conn.execute(
                """
                UPDATE videos SET
                    status = ?, error_msg = ?, retry_count = retry_count + 1, updated_at = ?
                WHERE yt_id = ?
                """,
                (status, message[:1000], now, yt_id),
            )

    def used_basenames(self, playlist_id: str) -> set[str]:
        """Basenames already used within one playlist's folder (collision scope)."""
        rows = self._conn.execute(
            "SELECT file_path FROM videos WHERE playlist_id = ? AND file_path IS NOT NULL",
            (playlist_id,),
        ).fetchall()
        return {Path(row["file_path"]).stem for row in rows}

    def video(self, yt_id: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM videos WHERE yt_id = ?", (yt_id,)).fetchone()
