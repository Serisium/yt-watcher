from conftest import make_info

from yt_watcher import naming


def test_default_template_renders_artist_and_track():
    fields = naming.video_fields(make_info())
    assert naming.render_basename("{artist} - {title}", fields) == (
        "Rick Astley - Never Gonna Give You Up"
    )


def test_artist_falls_back_to_uploader():
    info = make_info(artist=None, creator=None, uploader="Some Channel")
    assert naming.video_fields(info)["artist"] == "Some Channel"


def test_title_falls_back_to_video_title():
    info = make_info(track=None)
    fields = naming.video_fields(info)
    assert fields["title"] == "Rick Astley - Never Gonna Give You Up (Official Video)"


def test_unknown_template_field_renders_empty():
    fields = naming.video_fields(make_info())
    assert naming.render_basename("{nope}{title}", fields) == "Never Gonna Give You Up"


def test_sanitize_strips_invalid_chars():
    assert naming.sanitize('a/b\\c:d*e?f"g<h>i|j') == "abcdefghij"


def test_sanitize_keeps_unicode():
    assert naming.sanitize("Sigur Rós — Svefn-g-englar 🎵") == "Sigur Rós — Svefn-g-englar 🎵"


def test_sanitize_trailing_dots_and_spaces():
    assert naming.sanitize("ending badly .. ") == "ending badly"


def test_sanitize_collapses_whitespace():
    assert naming.sanitize("a\tb\n  c") == "a b c"


def test_long_title_truncated_to_byte_cap():
    fields = {"artist": "A", "title": "б" * 300, "id": "x"}
    base = naming.render_basename("{artist} - {title}", fields)
    assert len(base.encode("utf-8")) <= naming.MAX_BASENAME_BYTES
    assert base.startswith("A - б")


def test_empty_render_falls_back_to_id():
    fields = {"artist": "", "title": "", "id": "abc123"}
    assert naming.render_basename("{artist}{title}", fields) == "abc123"


def test_unique_basename_appends_id_on_collision():
    taken = {"Artist - Song"}
    assert naming.unique_basename("Artist - Song", taken, "vid1") == "Artist - Song [vid1]"
    assert naming.unique_basename("Other - Song", taken, "vid1") == "Other - Song"
