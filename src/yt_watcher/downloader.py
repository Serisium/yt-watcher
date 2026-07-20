"""Full metadata extraction + download of a single video."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from yt_watcher.config import Config

# Failure messages that mean the video cannot be fetched no matter how often we retry.
_UNAVAILABLE_MARKERS = (
    "private video",
    "video unavailable",
    "members-only",
    "members only",
    "removed by the uploader",
    "account associated with this video has been terminated",
    "confirm your age",
    "age-restricted",
)


@dataclass(frozen=True)
class DownloadResult:
    info: dict
    video_path: Path
    thumb_path: Path | None
    height: int | None
    vcodec: str | None
    acodec: str | None
    filesize: int | None


def classify_error(message: str) -> str:
    """'unavailable' for permanent failures (not retried), 'error' for transient ones."""
    lowered = message.lower()
    if any(marker in lowered for marker in _UNAVAILABLE_MARKERS):
        return "unavailable"
    return "error"


def build_ydl_opts(cfg: Config, out_dir: Path, logger: logging.Logger) -> dict:
    cap = cfg.max_height
    opts: dict = {
        "format": f"bestvideo[height<={cap}]+bestaudio/best[height<={cap}]",
        "merge_output_format": cfg.output_container,
        # Download under a stable id-based name (safe for .part resume); the final
        # human-readable name is applied by the caller after metadata is known.
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "writethumbnail": True,
        "postprocessors": [
            {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
        ],
        "retries": 5,
        "fragment_retries": 5,
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "logger": logger,
    }
    if cfg.cookies_file:
        opts["cookiefile"] = cfg.cookies_file
    return opts


def download_video(
    cfg: Config,
    yt_id: str,
    out_dir: Path,
    logger: logging.Logger,
    ydl_cls: type | None = None,
) -> DownloadResult:
    if ydl_cls is None:
        from yt_dlp import YoutubeDL as ydl_cls

    opts = build_ydl_opts(cfg, out_dir, logger)
    with ydl_cls(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={yt_id}", download=True)

    requested = info.get("requested_downloads") or []
    if requested and requested[0].get("filepath"):
        video_path = Path(requested[0]["filepath"])
    else:
        matches = [p for p in out_dir.glob(f"{yt_id}.*") if p.suffix != ".jpg"]
        if not matches:
            raise RuntimeError(f"download finished but no file found for {yt_id}")
        video_path = matches[0]

    fmt = requested[0] if requested else info
    thumb = out_dir / f"{yt_id}.jpg"
    return DownloadResult(
        info=info,
        video_path=video_path,
        thumb_path=thumb if thumb.exists() else None,
        height=fmt.get("height") or info.get("height"),
        vcodec=fmt.get("vcodec") or info.get("vcodec"),
        acodec=fmt.get("acodec") or info.get("acodec"),
        filesize=video_path.stat().st_size if video_path.exists() else None,
    )
