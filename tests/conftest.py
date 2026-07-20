import pytest

from yt_watcher.db import Database
from yt_watcher.poller import PlaylistEntry, PlaylistSnapshot


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    # Satisfy the videos.playlist_id foreign key for tests that use "PL1" directly.
    database.upsert_playlist(make_snapshot(yt_id="PL1"))
    yield database
    database.close()


@pytest.fixture
def snapshot():
    return make_snapshot()


def make_snapshot(entries=(), **overrides) -> PlaylistSnapshot:
    values = {
        "yt_id": "PLtest123",
        "title": "Test Playlist",
        "channel": "Test Channel",
        "channel_id": "UCtest",
        "description": "A playlist for tests",
        "thumbnail_url": None,
        "entries": tuple(entries),
    }
    values.update(overrides)
    return PlaylistSnapshot(**values)


def make_entry(yt_id: str, title: str | None = None) -> PlaylistEntry:
    return PlaylistEntry(yt_id=yt_id, title=title or f"Video {yt_id}")


def make_info(**overrides) -> dict:
    info = {
        "id": "abc123XYZ_-",
        "title": "Rick Astley - Never Gonna Give You Up (Official Video)",
        "track": "Never Gonna Give You Up",
        "artist": "Rick Astley",
        "creator": "Rick Astley",
        "uploader": "Rick Astley",
        "channel": "Rick Astley",
        "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "description": "The official video for “Never Gonna Give You Up”",
        "upload_date": "20091025",
        "duration": 213,
    }
    info.update(overrides)
    return info
