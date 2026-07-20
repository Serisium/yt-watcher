from pathlib import Path

from conftest import make_info

from yt_watcher import nfo

GOLDEN = Path(__file__).parent / "golden"


def test_musicvideo_nfo_matches_golden():
    content = nfo.render_musicvideo(
        make_info(),
        album="Test Playlist",
        thumb="Rick Astley - Never Gonna Give You Up-thumb.jpg",
    )
    assert content == (GOLDEN / "musicvideo.nfo").read_text(encoding="utf-8")


def test_xml_escaping_matches_golden():
    info = make_info(
        track='Bed & <Breakfast> "Quotes"',
        artist="Q&A",
        description="Line one\nAT&T <tags> stay escaped",
    )
    content = nfo.render_musicvideo(info, album="R&B Hits", thumb=None)
    assert content == (GOLDEN / "musicvideo_escaping.nfo").read_text(encoding="utf-8")


def test_missing_optional_fields_omitted():
    info = make_info(description=None, upload_date=None, duration=None)
    content = nfo.render_musicvideo(info, album=None, thumb=None)
    for tag in ("plot", "premiered", "aired", "year", "runtime", "album", "thumb"):
        assert f"<{tag}>" not in content
    assert '<uniqueid type="youtube" default="true">abc123XYZ_-</uniqueid>' in content


def test_write_if_changed_idempotent(tmp_path):
    target = tmp_path / "video.nfo"
    content = nfo.render_musicvideo(make_info(), album="A", thumb=None)
    assert nfo.write_if_changed(target, content) is True
    assert nfo.write_if_changed(target, content) is False
    assert target.read_text(encoding="utf-8") == content
    assert not list(tmp_path.glob("*.tmp"))
