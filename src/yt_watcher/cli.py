"""Entry point: argument parsing, signal handling, and the poll/download loop."""

from __future__ import annotations

import argparse
import logging
import signal
import threading
import urllib.request
from pathlib import Path

from yt_watcher import __version__, downloader, naming, nfo, poller
from yt_watcher.config import Config, ConfigError
from yt_watcher.db import Database
from yt_watcher.poller import PlaylistSnapshot

log = logging.getLogger("yt_watcher")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="yt-watcher",
        description=(
            "Watch one or more YouTube playlists, download new videos with yt-dlp, and "
            "write Plex-compatible NFO metadata. Each playlist gets its own folder under "
            "/media, named after the playlist. Configuration is via environment variables "
            "(POLL_INTERVAL, MAX_HEIGHT, OUTPUT_CONTAINER, FILENAME_TEMPLATE, "
            "COOKIES_FILE, SLEEP_BETWEEN_DOWNLOADS, LOG_LEVEL)."
        ),
    )
    parser.add_argument("playlist_urls", nargs="+", help="YouTube playlist URL(s) to watch")
    parser.add_argument("--once", action="store_true", help="run a single poll cycle and exit")
    parser.add_argument("--version", action="version", version=f"yt-watcher {__version__}")
    return parser.parse_args(argv)


def _ensure_poster(lib_dir: Path, thumbnail_url: str | None) -> None:
    poster = lib_dir / "poster.jpg"
    if poster.exists() or not thumbnail_url:
        return
    try:
        tmp = poster.with_name("poster.jpg.tmp")
        with urllib.request.urlopen(thumbnail_url, timeout=30) as resp:
            tmp.write_bytes(resp.read())
        tmp.replace(poster)
        log.info("wrote %s", poster)
    except Exception as exc:
        log.warning("could not fetch playlist poster: %s", exc)


def _process_video(
    cfg: Config,
    db: Database,
    snapshot: PlaylistSnapshot,
    lib_dir: Path,
    yt_id: str,
    taken: set[str],
) -> bool:
    try:
        result = downloader.download_video(cfg, yt_id, lib_dir, log)
    except Exception as exc:
        message = str(exc)
        status = downloader.classify_error(message)
        db.mark_failed(yt_id, message, unavailable=status == "unavailable")
        log.warning("%s failed (%s): %s", yt_id, status, message)
        return False

    fields = naming.video_fields(result.info)
    base = naming.render_basename(cfg.filename_template, fields)
    base = naming.unique_basename(base, taken, yt_id)
    taken.add(base)

    final_video = lib_dir / f"{base}{result.video_path.suffix}"
    result.video_path.replace(final_video)
    thumb_name = None
    if result.thumb_path is not None:
        thumb_name = f"{base}-thumb.jpg"
        result.thumb_path.replace(lib_dir / thumb_name)

    content = nfo.render_musicvideo(result.info, album=snapshot.title, thumb=thumb_name)
    nfo.write_if_changed(lib_dir / f"{base}.nfo", content)

    db.mark_downloaded(
        yt_id,
        file_path=str(final_video.relative_to(cfg.media_dir)),
        height=result.height,
        vcodec=result.vcodec,
        acodec=result.acodec,
        filesize=result.filesize,
        title=result.info.get("title"),
        upload_date=result.info.get("upload_date"),
        duration_s=int(result.info["duration"]) if result.info.get("duration") else None,
    )
    log.info("downloaded %s -> %s (%sp)", yt_id, final_video.name, result.height or "?")
    return True


def _poll_playlist(cfg: Config, db: Database, stop: threading.Event, url: str) -> None:
    snapshot = poller.fetch_playlist(url, cfg.cookies_file)
    db.upsert_playlist(snapshot)
    new_ids = db.record_seen(snapshot.yt_id, snapshot.entries)
    log.info("playlist %r: %d entries, %d new", snapshot.title, len(snapshot.entries), len(new_ids))

    lib_dir = cfg.media_dir / (naming.sanitize(snapshot.title) or "YouTube")
    lib_dir.mkdir(parents=True, exist_ok=True)
    _ensure_poster(lib_dir, snapshot.thumbnail_url)

    pending = db.videos_to_download(snapshot.yt_id)
    if not pending:
        log.info("0 new videos to download")
        return

    log.info("%d video(s) to download", len(pending))
    taken = db.used_basenames(snapshot.yt_id)
    for index, row in enumerate(pending):
        if stop.is_set():
            log.info("shutdown requested, stopping download queue")
            break
        _process_video(cfg, db, snapshot, lib_dir, row["yt_id"], taken)
        if index < len(pending) - 1:
            stop.wait(cfg.sleep_between_downloads)


def run_once(cfg: Config, db: Database, stop: threading.Event) -> None:
    for url in cfg.playlist_urls:
        if stop.is_set():
            break
        try:
            _poll_playlist(cfg, db, stop, url)
        except Exception:
            log.exception("poll failed for %s; other playlists continue", url)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        cfg = Config.from_env(args.playlist_urls)
    except ConfigError as exc:
        print(f"configuration error: {exc}")
        return 2

    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    stop = threading.Event()

    def _handle_signal(signum: int, _frame: object) -> None:
        log.info("received %s, shutting down", signal.Signals(signum).name)
        stop.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    cfg.config_dir.mkdir(parents=True, exist_ok=True)
    cfg.media_dir.mkdir(parents=True, exist_ok=True)
    db = Database(cfg.db_path)

    from yt_dlp.version import __version__ as ytdlp_version

    log.info(
        "yt-watcher %s (yt-dlp %s) watching %d playlist(s) every %ss, cap %sp",
        __version__,
        ytdlp_version,
        len(cfg.playlist_urls),
        cfg.poll_interval,
        cfg.max_height,
    )
    for url in cfg.playlist_urls:
        log.info("  %s", url)

    try:
        while not stop.is_set():
            try:
                run_once(cfg, db, stop)
            except Exception:
                log.exception("poll cycle failed; will retry next interval")
            if args.once or stop.is_set():
                break
            stop.wait(cfg.poll_interval)
    finally:
        db.close()
    log.info("exiting")
    return 0
