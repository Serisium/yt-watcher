"""All runtime configuration, read from the environment in one place."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

VALID_CONTAINERS = ("mkv", "mp4")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    playlist_urls: tuple[str, ...]
    poll_interval: int = 3600
    max_height: int = 1440
    output_container: str = "mkv"
    filename_template: str = "{artist} - {title}"
    cookies_file: str | None = None
    sleep_between_downloads: int = 10
    log_level: str = "INFO"
    media_dir: Path = Path("/media")
    config_dir: Path = Path("/config")

    @property
    def db_path(self) -> Path:
        return self.config_dir / "yt-watcher.sqlite3"

    @classmethod
    def from_env(cls, playlist_urls: Sequence[str], env: Mapping[str, str] | None = None) -> Config:
        if env is None:
            env = os.environ

        def _int(name: str, default: int, minimum: int = 0) -> int:
            raw = env.get(name)
            if raw is None or raw == "":
                return default
            try:
                value = int(raw)
            except ValueError:
                raise ConfigError(f"{name} must be an integer, got {raw!r}") from None
            if value < minimum:
                raise ConfigError(f"{name} must be >= {minimum}, got {value}")
            return value

        container = env.get("OUTPUT_CONTAINER", "mkv").lower()
        if container not in VALID_CONTAINERS:
            raise ConfigError(
                f"OUTPUT_CONTAINER must be one of {', '.join(VALID_CONTAINERS)}, got {container!r}"
            )

        cookies_file = env.get("COOKIES_FILE") or None
        if cookies_file and not Path(cookies_file).is_file():
            raise ConfigError(f"COOKIES_FILE {cookies_file!r} does not exist")

        return cls(
            playlist_urls=tuple(playlist_urls),
            poll_interval=_int("POLL_INTERVAL", 3600, minimum=60),
            max_height=_int("MAX_HEIGHT", 1440, minimum=144),
            output_container=container,
            filename_template=env.get("FILENAME_TEMPLATE") or "{artist} - {title}",
            cookies_file=cookies_file,
            sleep_between_downloads=_int("SLEEP_BETWEEN_DOWNLOADS", 10),
            log_level=env.get("LOG_LEVEL", "INFO").upper(),
            media_dir=Path(env.get("MEDIA_DIR", "/media")),
            config_dir=Path(env.get("CONFIG_DIR", "/config")),
        )
