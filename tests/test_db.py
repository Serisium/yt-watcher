from conftest import make_entry, make_snapshot

from yt_watcher.db import MAX_RETRIES


def test_record_seen_inserts_new_as_pending(db):
    new = db.record_seen("PL1", [make_entry("a"), make_entry("b")])
    assert new == ["a", "b"]
    row = db.video("a")
    assert row["status"] == "pending"
    assert row["in_playlist"] == 1
    assert row["playlist_id"] == "PL1"


def test_record_seen_is_idempotent(db):
    db.record_seen("PL1", [make_entry("a")])
    assert db.record_seen("PL1", [make_entry("a")]) == []


def test_record_seen_updates_title(db):
    db.record_seen("PL1", [make_entry("a", "Old title")])
    db.record_seen("PL1", [make_entry("a", "New title")])
    assert db.video("a")["title"] == "New title"


def test_removed_video_flagged_not_deleted(db):
    db.record_seen("PL1", [make_entry("a"), make_entry("b")])
    db.mark_downloaded(
        "a", file_path="Lib/a.mkv", height=1080, vcodec="vp9", acodec="opus", filesize=1
    )
    db.record_seen("PL1", [make_entry("b")])
    row = db.video("a")
    assert row["in_playlist"] == 0
    assert row["status"] == "downloaded"
    assert row["file_path"] == "Lib/a.mkv"


def test_removed_video_reappearing_is_not_new(db):
    db.record_seen("PL1", [make_entry("a")])
    db.record_seen("PL1", [])
    assert db.record_seen("PL1", [make_entry("a")]) == []
    assert db.video("a")["in_playlist"] == 1


def test_downloaded_videos_not_requeued(db):
    db.record_seen("PL1", [make_entry("a")])
    db.mark_downloaded(
        "a", file_path="Lib/a.mkv", height=720, vcodec="vp9", acodec="opus", filesize=9
    )
    assert db.videos_to_download("PL1") == []


def test_errors_retry_until_capped(db):
    db.record_seen("PL1", [make_entry("a")])
    for _ in range(MAX_RETRIES):
        assert [r["yt_id"] for r in db.videos_to_download("PL1")] == ["a"]
        db.mark_failed("a", "boom", unavailable=False)
    assert db.videos_to_download("PL1") == []
    assert db.video("a")["retry_count"] == MAX_RETRIES


def test_unavailable_never_requeued(db):
    db.record_seen("PL1", [make_entry("a")])
    db.mark_failed("a", "Private video", unavailable=True)
    assert db.videos_to_download("PL1") == []
    assert db.video("a")["status"] == "unavailable"


def test_used_basenames(db):
    db.record_seen("PL1", [make_entry("a"), make_entry("b")])
    db.mark_downloaded(
        "a",
        file_path="Lib/Artist - Song.mkv",
        height=1080,
        vcodec="vp9",
        acodec="opus",
        filesize=1,
    )
    assert db.used_basenames("PL1") == {"Artist - Song"}
    assert db.used_basenames("PLother") == set()


def test_upsert_playlist_idempotent(db):
    db.upsert_playlist(make_snapshot())
    db.upsert_playlist(make_snapshot(title="Renamed"))


def test_migration_sets_user_version(db):
    version = db._conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 1
