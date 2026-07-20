import logging

import pytest
from conftest import make_info

from yt_watcher import downloader
from yt_watcher.config import Config

log = logging.getLogger("test")


def cfg(**overrides) -> Config:
    return Config(playlist_urls=("https://example.invalid/p",), **overrides)


def test_format_selector_caps_height(tmp_path):
    opts = downloader.build_ydl_opts(cfg(max_height=720), tmp_path, log)
    assert opts["format"] == "bestvideo[height<=720]+bestaudio/best[height<=720]"
    assert opts["merge_output_format"] == "mkv"


def test_outtmpl_is_id_based(tmp_path):
    opts = downloader.build_ydl_opts(cfg(), tmp_path, log)
    assert opts["outtmpl"] == str(tmp_path / "%(id)s.%(ext)s")
    assert opts["writethumbnail"] is True


def test_cookies_only_when_configured(tmp_path):
    assert "cookiefile" not in downloader.build_ydl_opts(cfg(), tmp_path, log)
    cookie = tmp_path / "cookies.txt"
    cookie.write_text("")
    opts = downloader.build_ydl_opts(cfg(cookies_file=str(cookie)), tmp_path, log)
    assert opts["cookiefile"] == str(cookie)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("ERROR: [youtube] abc: Private video. Sign in if you have access", "unavailable"),
        ("ERROR: [youtube] abc: Video unavailable", "unavailable"),
        ("This video is available to this channel's members only", "unavailable"),
        ("Sign in to confirm your age", "unavailable"),
        ("HTTP Error 503: Service Temporarily Unavailable", "error"),
        ("Connection reset by peer", "error"),
        ("HTTP Error 429: Too Many Requests", "error"),
    ],
)
def test_classify_error(message, expected):
    assert downloader.classify_error(message) == expected


class FakeYDL:
    """Simulates a successful yt-dlp download by writing the output files."""

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        assert download is True
        assert "watch?v=abc123XYZ_-" in url
        out = self.opts["outtmpl"]
        video = out.replace("%(id)s", "abc123XYZ_-").replace("%(ext)s", "mkv")
        with open(video, "wb") as fh:
            fh.write(b"\x00" * 42)
        with open(video.replace(".mkv", ".jpg"), "wb") as fh:
            fh.write(b"jpg")
        info = make_info()
        info["requested_downloads"] = [
            {"filepath": video, "height": 1080, "vcodec": "vp9", "acodec": "opus"}
        ]
        return info


def test_download_video_maps_result(tmp_path):
    result = downloader.download_video(cfg(), "abc123XYZ_-", tmp_path, log, ydl_cls=FakeYDL)
    assert result.video_path == tmp_path / "abc123XYZ_-.mkv"
    assert result.thumb_path == tmp_path / "abc123XYZ_-.jpg"
    assert result.height == 1080
    assert result.vcodec == "vp9"
    assert result.acodec == "opus"
    assert result.filesize == 42
    assert result.info["track"] == "Never Gonna Give You Up"
