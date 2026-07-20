"""Cheap playlist polling via yt-dlp flat extraction.

Flat entries carry only id/title — full metadata (upload date, description, artist)
is fetched per-video at download time, never from here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlaylistEntry:
    yt_id: str
    title: str


@dataclass(frozen=True)
class PlaylistSnapshot:
    yt_id: str
    title: str
    channel: str | None
    channel_id: str | None
    description: str | None
    thumbnail_url: str | None
    entries: tuple[PlaylistEntry, ...]


def fetch_playlist(
    url: str, cookies_file: str | None = None, ydl_cls: type | None = None
) -> PlaylistSnapshot:
    if ydl_cls is None:
        from yt_dlp import YoutubeDL as ydl_cls

    opts: dict = {
        "extract_flat": "in_playlist",
        "skip_download": True,
        "quiet": True,
        "noprogress": True,
    }
    if cookies_file:
        opts["cookiefile"] = cookies_file

    with ydl_cls(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    entries = tuple(
        PlaylistEntry(yt_id=entry["id"], title=entry.get("title") or entry["id"])
        for entry in (info.get("entries") or [])
        if entry and entry.get("id")
    )
    thumbnails = info.get("thumbnails") or []
    return PlaylistSnapshot(
        yt_id=info.get("id") or url,
        title=info.get("title") or "YouTube Playlist",
        channel=info.get("channel") or info.get("uploader"),
        channel_id=info.get("channel_id"),
        description=info.get("description"),
        thumbnail_url=thumbnails[-1]["url"] if thumbnails else None,
        entries=entries,
    )
