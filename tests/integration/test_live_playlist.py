"""Opt-in live smoke test against the sample playlist.

Requires network access to YouTube and is deliberately excluded from CI
(GitHub runner IPs trip YouTube's bot checks). Run with:

    YTW_LIVE=1 pytest tests/integration -s
"""

import logging
import os
import threading

import pytest

from yt_watcher import cli
from yt_watcher.config import Config
from yt_watcher.db import Database

SAMPLE_PLAYLIST = "https://www.youtube.com/playlist?list=PLXeIIajkQOe_3PXThVaP0dxMLYv6gcdyz"

pytestmark = pytest.mark.skipif(
    not os.environ.get("YTW_LIVE"), reason="live YouTube test; set YTW_LIVE=1 to run"
)


def test_poll_download_and_no_redownload(tmp_path):
    logging.basicConfig(level=logging.INFO)
    cfg = Config(
        playlist_urls=(SAMPLE_PLAYLIST,),
        max_height=360,  # keep the smoke test fast and small
        sleep_between_downloads=2,
        media_dir=tmp_path / "media",
        config_dir=tmp_path / "config",
    )
    cfg.media_dir.mkdir()
    cfg.config_dir.mkdir()

    db = Database(cfg.db_path)
    cli.run_once(cfg, db, threading.Event())

    libs = [p for p in cfg.media_dir.iterdir() if p.is_dir()]
    assert len(libs) == 1
    videos = list(libs[0].glob("*.mkv"))
    assert videos, "expected at least one downloaded video"
    for video in videos:
        assert video.with_name(f"{video.stem}.nfo").exists()

    downloaded = db._conn.execute(
        "SELECT COUNT(*) FROM videos WHERE status = 'downloaded'"
    ).fetchone()[0]
    assert downloaded == len(videos)

    # Second poll must download nothing.
    before = {p.name: p.stat().st_mtime for p in libs[0].iterdir()}
    cli.run_once(cfg, db, threading.Event())
    after = {p.name: p.stat().st_mtime for p in libs[0].iterdir()}
    assert before == after
    db.close()
