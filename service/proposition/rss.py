from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any
from urllib import error as urlerror
from urllib import request


@dataclass
class FeedItem:
    external_id: str
    title: str
    link: str
    summary: str
    published_raw: str | None
    raw: dict[str, Any]


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return " ".join(el.itertext()).strip()


def _first_child(parent: ET.Element, *local_names: str) -> ET.Element | None:
    for child in parent:
        if _strip_ns(child.tag) in local_names:
            return child
    return None


def parse_feed_xml(xml_bytes: bytes) -> list[FeedItem]:
    root = ET.fromstring(xml_bytes)
    tag = _strip_ns(root.tag).lower()
    items: list[FeedItem] = []

    if tag == "rss" or tag == "rdf:rdf":
        channel = root.find("channel")
        if channel is None:
            channel = root
        for node in channel:
            if _strip_ns(node.tag).lower() != "item":
                continue
            title = _text(_first_child(node, "title")) or "(no title)"
            link = _text(_first_child(node, "link"))
            guid_el = _first_child(node, "guid")
            guid = _text(guid_el) or link
            ext = guid or link or title
            desc = _text(_first_child(node, "description"))
            pub = _text(_first_child(node, "pubDate")) or None
            items.append(
                FeedItem(
                    external_id=ext[:512],
                    title=title[:2000],
                    link=link[:2000],
                    summary=desc[:8000],
                    published_raw=pub,
                    raw={"title": title, "link": link, "guid": guid},
                )
            )
        return items

    if tag == "feed":
        for entry in root:
            if _strip_ns(entry.tag).lower() != "entry":
                continue
            title = _text(_first_child(entry, "title")) or "(no title)"
            link_el = _first_child(entry, "link")
            link = ""
            if link_el is not None and link_el.get("href"):
                link = (link_el.get("href") or "").strip()
            if not link:
                alt = _first_child(entry, "id")
                link = _text(alt)
            id_el = _first_child(entry, "id")
            ext = _text(id_el) or link or title
            summary = _text(_first_child(entry, "summary")) or _text(
                _first_child(entry, "content")
            )
            pub = _text(_first_child(entry, "updated")) or _text(
                _first_child(entry, "published")
            )
            items.append(
                FeedItem(
                    external_id=ext[:512],
                    title=title[:2000],
                    link=link[:2000],
                    summary=summary[:8000],
                    published_raw=pub or None,
                    raw={"title": title, "link": link, "id": ext},
                )
            )
        return items

    return items


def fetch_rss_items(url: str, timeout: int = 25) -> list[FeedItem]:
    req = request.Request(url, headers={"User-Agent": "ParamutuelPropositionService/1.0"})
    with request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return parse_feed_xml(data)


def published_ts(pub: str | None) -> int | None:
    if not pub:
        return None
    # Best-effort: digits-only epoch
    if re.fullmatch(r"\d+", pub.strip()):
        try:
            v = int(pub.strip())
            if v > 1_000_000_000_000:  # milliseconds since epoch
                return v // 1000
            if v > 1_000_000_000:  # seconds since epoch
                return v
        except ValueError:
            return None
    return None
