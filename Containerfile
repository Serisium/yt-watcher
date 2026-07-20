# Podman-first, docker-compatible. Build with:
#   podman build --build-arg YTDLP_VERSION=<version> -t yt-watcher .
FROM docker.io/library/python:3.12-slim-bookworm

ARG YTDLP_VERSION
RUN test -n "$YTDLP_VERSION" || (echo "YTDLP_VERSION build arg is required" && false)

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates tzdata curl unzip \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp needs a JavaScript runtime (deno) to solve YouTube's player challenges;
# without one, extraction is deprecated and higher-quality formats go missing.
ARG TARGETARCH
RUN case "${TARGETARCH:-amd64}" in \
      amd64) DENO_ARCH=x86_64-unknown-linux-gnu ;; \
      arm64) DENO_ARCH=aarch64-unknown-linux-gnu ;; \
      *) echo "unsupported arch: ${TARGETARCH}" && exit 1 ;; \
    esac \
    && curl -fsSL "https://github.com/denoland/deno/releases/latest/download/deno-${DENO_ARCH}.zip" -o /tmp/deno.zip \
    && unzip -q /tmp/deno.zip -d /usr/local/bin \
    && rm /tmp/deno.zip \
    && deno --version

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir "yt-dlp==${YTDLP_VERSION}" .

RUN useradd --uid 1000 --create-home app \
    && mkdir -p /media /config \
    && chown app:app /media /config
USER app
VOLUME ["/media", "/config"]

# Playlist URLs are the container arguments (one folder per playlist under /media):
#   podman run ... yt-watcher "https://www.youtube.com/playlist?list=..." [more URLs...]
ENTRYPOINT ["python", "-m", "yt_watcher"]

LABEL org.opencontainers.image.title="yt-watcher" \
      org.opencontainers.image.description="Watches a YouTube playlist, downloads new videos with yt-dlp, writes Plex-compatible NFO metadata" \
      org.opencontainers.image.source="https://github.com/Serisium/yt-watcher" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${YTDLP_VERSION}"
