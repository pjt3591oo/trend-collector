"""Site-specific collection and parsing."""
from __future__ import annotations

from collections.abc import Iterator
from .base import BaseSource, CollectionRequest

import os

import xml.etree.ElementTree as ET
from src.models import CollectionError, Item
from src.parsing import plain, xml_text


def parse_geeknews(body: bytes, limit: int) -> list[Item]:
    root = ET.fromstring(body)
    entries = root.findall('{*}entry')
    if not entries:
        raise CollectionError('GeekNews feed has no Atom entries')
    result = []
    for rank, entry in enumerate(entries[:limit], 1):
        links = entry.findall('{*}link')
        url = next((e.get('href') for e in links if e.get('rel', 'alternate') == 'alternate'), None)
        if not url:
            continue
        result.append(Item('geeknews', xml_text(entry, 'id') or url,
                           xml_text(entry, 'title'), url, discussion_url=url,
                           published_at=xml_text(entry, 'published') or xml_text(entry, 'updated'),
                           summary=plain(xml_text(entry, 'content') or xml_text(entry, 'summary')),
                           rank=rank, collection_method='atom',
                           metadata={'url_kind': 'discussion', 'original_url': None,
                                     'author': xml_text(entry, 'author')}))
    return result

class GeekNewsSource(BaseSource):
    name = 'geeknews'

    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        http, cfg = self.http, self.config
        limit, days = request.limit, request.days
        yield from parse_geeknews(http.get('https://news.hada.io/rss/news'), limit)

def collect(http, cfg, limit, days):
    """Compatibility wrapper; use GeekNewsSource for dependency injection."""
    return GeekNewsSource(http, cfg, credentials=os.environ).collect(CollectionRequest(limit, days))
