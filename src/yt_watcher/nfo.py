"""Kodi/Jellyfin-compatible <musicvideo> NFO rendering (stdlib XML only)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from yt_watcher import naming

XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'


def render_musicvideo(info: dict, *, album: str | None, thumb: str | None) -> str:
    fields = naming.video_fields(info)
    root = ET.Element("musicvideo")

    def add(tag: str, text: object) -> None:
        if text not in (None, ""):
            ET.SubElement(root, tag).text = str(text)

    add("title", fields["title"])
    add("artist", fields["artist"])
    add("album", album)
    add("plot", info.get("description"))
    upload_date = info.get("upload_date")
    if upload_date and len(upload_date) == 8:
        iso = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
        add("premiered", iso)
        add("aired", iso)
        add("year", upload_date[:4])
    add("studio", info.get("channel") or info.get("uploader"))
    duration = info.get("duration")
    if duration:
        add("runtime", max(1, round(duration / 60)))
    uniqueid = ET.SubElement(root, "uniqueid", type="youtube", default="true")
    uniqueid.text = str(info.get("id") or "")
    add("thumb", thumb)

    ET.indent(root, space="  ")
    return f"{XML_DECLARATION}\n{ET.tostring(root, encoding='unicode')}\n"


def write_if_changed(path: Path, content: str) -> bool:
    """Atomically write content; skip the write when the file already matches."""
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)
    return True
