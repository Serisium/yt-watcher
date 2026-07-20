from yt_watcher import poller


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL in flat-extraction mode."""

    last_opts = None

    def __init__(self, opts):
        FakeYDL.last_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        assert download is False
        return {
            "id": "PLtest123",
            "title": "Test Playlist",
            "channel": "Test Channel",
            "channel_id": "UCtest",
            "description": "desc",
            "thumbnails": [
                {"url": "https://i.ytimg.com/low.jpg"},
                {"url": "https://i.ytimg.com/hi.jpg"},
            ],
            "entries": [
                {"id": "vid1", "title": "First"},
                {"id": "vid2", "title": None},
                None,
                {"title": "no id, skipped"},
            ],
        }


def test_fetch_playlist_parses_flat_entries():
    snapshot = poller.fetch_playlist("https://example.invalid/playlist", ydl_cls=FakeYDL)
    assert snapshot.yt_id == "PLtest123"
    assert snapshot.title == "Test Playlist"
    assert snapshot.thumbnail_url == "https://i.ytimg.com/hi.jpg"
    assert [e.yt_id for e in snapshot.entries] == ["vid1", "vid2"]
    assert snapshot.entries[1].title == "vid2"  # falls back to id


def test_fetch_playlist_uses_flat_extraction():
    poller.fetch_playlist("https://example.invalid/playlist", ydl_cls=FakeYDL)
    assert FakeYDL.last_opts["extract_flat"] == "in_playlist"
    assert FakeYDL.last_opts["skip_download"] is True
    assert "cookiefile" not in FakeYDL.last_opts


def test_fetch_playlist_passes_cookies():
    poller.fetch_playlist("https://example.invalid/p", cookies_file="/c.txt", ydl_cls=FakeYDL)
    assert FakeYDL.last_opts["cookiefile"] == "/c.txt"
