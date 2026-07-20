"""Filename construction: template rendering plus filesystem sanitization."""

from __future__ import annotations

_INVALID_CHARS = set('/\\:*?"<>|')
MAX_BASENAME_BYTES = 180


def sanitize(name: str) -> str:
    """Strip characters that break SMB/Windows/ext4 paths; collapse whitespace."""
    cleaned = " ".join(name.split())
    cleaned = "".join(c for c in cleaned if c not in _INVALID_CHARS and ord(c) >= 32)
    return cleaned.rstrip(" .")


def truncate_bytes(name: str, max_bytes: int = MAX_BASENAME_BYTES) -> str:
    raw = name.encode("utf-8")
    if len(raw) <= max_bytes:
        return name
    return raw[:max_bytes].decode("utf-8", errors="ignore").rstrip(" .")


def video_fields(info: dict) -> dict[str, str]:
    """Template fields from a full yt-dlp info dict, with music-metadata fallbacks."""
    artist = (
        info.get("artist")
        or info.get("creator")
        or info.get("uploader")
        or info.get("channel")
        or ""
    )
    title = info.get("track") or info.get("title") or info.get("id") or ""
    return {
        "artist": str(artist),
        "title": str(title),
        "upload_date": str(info.get("upload_date") or ""),
        "channel": str(info.get("channel") or info.get("uploader") or ""),
        "id": str(info.get("id") or ""),
    }


class _Fields(dict):
    def __missing__(self, key: str) -> str:
        return ""


def render_basename(template: str, fields: dict[str, str]) -> str:
    name = template.format_map(_Fields(fields))
    name = truncate_bytes(sanitize(name))
    return name or fields.get("id", "video")


def unique_basename(base: str, taken: set[str], yt_id: str) -> str:
    if base not in taken:
        return base
    return f"{base} [{yt_id}]"
