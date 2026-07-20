# yt-watcher

A podman-first, docker-compatible container that watches YouTube playlists and mirrors
them into a Plex-compatible media library.

Give it one or more playlist URLs as container arguments and it will:

- **Poll each playlist periodically** (cheap flat extraction — no video pages fetched) and
  download anything new with an embedded [yt-dlp](https://github.com/yt-dlp/yt-dlp).
  Each playlist gets its own folder under `/media`, named after the playlist.
- **Pick the best quality up to a cap** (default 1440p/2K, configurable via `MAX_HEIGHT`),
  merged into `.mkv` by the embedded ffmpeg.
- **Write Plex/Jellyfin/Kodi-compatible metadata**: a `<musicvideo>` NFO sidecar and
  `-thumb.jpg` per video, plus a `poster.jpg` for the library folder.
- **Keep its own SQLite mirror of the playlists** in `/config` — nothing is ever downloaded
  twice, and downloaded files are **never deleted**, even if a video is removed from the
  playlist or from YouTube.

The image embeds yt-dlp (plus ffmpeg and the deno JS runtime yt-dlp needs for YouTube),
and **image tags follow yt-dlp's versioning**: `:latest` always carries the newest yt-dlp
release, and each release is also published as its own tag (e.g. `:2026.7.4`).

## Quickstart (podman)

```bash
mkdir -p ~/ytw/media ~/ytw/config

podman run -d --name yt-watcher \
  --userns=keep-id:uid=1000,gid=1000 \
  -v ~/ytw/media:/media \
  -v ~/ytw/config:/config \
  -e MAX_HEIGHT=1440 \
  ghcr.io/serisium/yt-watcher:latest \
  "https://www.youtube.com/playlist?list=PLXeIIajkQOe_3PXThVaP0dxMLYv6gcdyz" \
  "https://www.youtube.com/playlist?list=ANOTHER_PLAYLIST_ID"
```

Notes:

- The container runs as UID 1000; `--userns=keep-id:uid=1000,gid=1000` maps that to your
  own user so downloaded files are owned by you (works rootless, including podman machine
  on macOS).
- On SELinux hosts (Fedora/RHEL) append `:Z` to the volume mounts: `-v ~/ytw/media:/media:Z`.
- Docker works identically — drop the `--userns` flag and make sure the mounted
  directories are writable by UID 1000 (`chown 1000:1000 ~/ytw/media ~/ytw/config`).
- Stop with a grace period so an in-flight video can finish or checkpoint:
  `podman stop -t 30 yt-watcher`. Interrupted downloads resume from `.part` files on the
  next start.

Or use the included [compose.yaml](compose.yaml) with `podman-compose up -d` /
`docker compose up -d`.

## Configuration

Playlist URLs are the only arguments (pass as many as you like). Everything else is an
environment variable:

| Variable | Default | Meaning |
|---|---|---|
| `POLL_INTERVAL` | `3600` | Seconds between playlist polls (min 60). |
| `MAX_HEIGHT` | `1440` | Quality cap in pixels of video height. Highest available quality up to this is chosen; never more. |
| `OUTPUT_CONTAINER` | `mkv` | `mkv` or `mp4`. mkv accepts YouTube's VP9/AV1 + Opus without re-encoding. |
| `FILENAME_TEMPLATE` | `{artist} - {title}` | Filename pattern. Fields: `{artist}`, `{title}`, `{upload_date}`, `{channel}`, `{id}`. `{artist}` falls back artist → creator → uploader → channel; `{title}` prefers the track name when YouTube provides one. |
| `COOKIES_FILE` | unset | Path to a Netscape-format cookies file (e.g. `/config/cookies.txt`) for age-restricted/members content and bot-check mitigation. |
| `SLEEP_BETWEEN_DOWNLOADS` | `10` | Politeness delay in seconds between video downloads. |
| `TZ` | UTC | Container timezone. |
| `LOG_LEVEL` | `INFO` | Python logging level. |

Volumes:

- `/media` — the library. One folder per playlist, named after the playlist:
  `Music Videos/Artist - Title.mkv` with `.nfo` and `-thumb.jpg` sidecars plus
  `poster.jpg`.
- `/config` — persistent state: `yt-watcher.sqlite3` (the playlist mirror) and optionally
  `cookies.txt`.

## How state works

The SQLite database in `/config` is the source of truth:

- Every playlist entry gets a row (`pending` → `downloaded` / `error` / `unavailable`).
- Already-`downloaded` videos are never fetched again — restarting the container or
  pointing a fresh container at existing `/config` picks up exactly where it left off.
- Videos that disappear from the playlist are flagged `in_playlist = 0`; their rows and
  files are kept forever (data preservation).
- Transient failures (403s, network resets) are retried on later polls, up to 5 times.
  Permanently unavailable videos (private, removed, members-only) are marked and skipped.

## Plex setup

Files are named `Artist - Title.ext` with Kodi-style `<musicvideo>` NFO sidecars —
the layout Plex expects for a **Music Videos / Other Videos** library:

- **Plex**: create an *Other Videos* library pointed at the media folder, with the
  *Personal Media* agent and *Local Media Assets* enabled (reads the `-thumb.jpg`), or use
  an NFO-importer agent to pick up full metadata (plot, air date, artist).
- **Jellyfin / Kodi**: create a *Music Videos* library — NFO sidecars are read natively.

## Image versioning

`ghcr.io/serisium/yt-watcher:latest` tracks yt-dlp releases, not this repo's commits.
A scheduled GitHub Actions workflow ([release-image.yaml](.github/workflows/release-image.yaml))
checks PyPI daily; when a new yt-dlp version appears it builds and pushes
`:<ytdlp-version>` + `:latest` (linux/amd64 + linux/arm64). Versions use PyPI's normalized
form (`2026.7.4` for release `2026.07.04`).

To ship a change to the watcher itself under the same yt-dlp version, run the workflow
manually with **force** enabled. To roll back a broken yt-dlp release, run it manually
with an older **version** — it re-publishes that version as `:latest`.

Local build:

```bash
podman build \
  --build-arg YTDLP_VERSION=$(curl -fsS https://pypi.org/pypi/yt-dlp/json | jq -r .info.version) \
  -t yt-watcher:dev .
```

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest            # unit tests, no network
.venv/bin/ruff check .
```

Run the watcher directly (no container) with `MEDIA_DIR`/`CONFIG_DIR` overrides:

```bash
MEDIA_DIR=./media CONFIG_DIR=./config MAX_HEIGHT=360 \
  .venv/bin/yt-watcher --once "https://www.youtube.com/playlist?list=PLXeIIajkQOe_3PXThVaP0dxMLYv6gcdyz"
```

An opt-in live smoke test against the sample playlist exists but is excluded from CI
(YouTube bot-checks CI runner IPs): `YTW_LIVE=1 .venv/bin/pytest tests/integration -s`.

## Known limitations

- YouTube increasingly challenges datacenter IPs ("Sign in to confirm you're not a bot").
  Running from a home IP usually just works; otherwise mount cookies via `COOKIES_FILE`,
  or look at the [PO token provider plugin](https://github.com/Brainicism/bgutil-ytdlp-pot-provider).
- Quality is chosen once at download time. If a video is later re-uploaded or unlocked at
  a higher resolution, it is not re-fetched (files are never replaced).

## License

MIT
