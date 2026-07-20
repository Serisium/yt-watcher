import threading

from conftest import make_snapshot

from yt_watcher import cli
from yt_watcher.config import Config
from yt_watcher.db import Database


def make_cfg(tmp_path, urls) -> Config:
    cfg = Config(
        playlist_urls=tuple(urls),
        media_dir=tmp_path / "media",
        config_dir=tmp_path / "config",
    )
    cfg.media_dir.mkdir()
    cfg.config_dir.mkdir()
    return cfg


def test_each_playlist_gets_its_own_folder(tmp_path, monkeypatch):
    snapshots = {
        "u1": make_snapshot(yt_id="PL1", title="Music Videos"),
        "u2": make_snapshot(yt_id="PL2", title="Live: Sets?"),
    }
    monkeypatch.setattr(cli.poller, "fetch_playlist", lambda url, cookies=None: snapshots[url])

    cfg = make_cfg(tmp_path, ["u1", "u2"])
    db = Database(cfg.db_path)
    cli.run_once(cfg, db, threading.Event())

    folders = sorted(p.name for p in cfg.media_dir.iterdir() if p.is_dir())
    assert folders == ["Live Sets", "Music Videos"]  # playlist titles, sanitized
    assert db._conn.execute("SELECT COUNT(*) FROM playlist").fetchone()[0] == 2
    db.close()


def test_one_failing_playlist_does_not_block_others(tmp_path, monkeypatch):
    def fetch(url, cookies=None):
        if url == "bad":
            raise RuntimeError("playlist does not exist")
        return make_snapshot(yt_id="PLok", title="Good List")

    monkeypatch.setattr(cli.poller, "fetch_playlist", fetch)

    cfg = make_cfg(tmp_path, ["bad", "good"])
    db = Database(cfg.db_path)
    cli.run_once(cfg, db, threading.Event())

    assert (cfg.media_dir / "Good List").is_dir()
    db.close()
