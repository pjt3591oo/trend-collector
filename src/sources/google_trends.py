"""Site-specific collection and parsing."""
from __future__ import annotations

from collections.abc import Iterator
from .base import BaseSource, CollectionRequest

import os

import re
from urllib.parse import urlencode
import xml.etree.ElementTree as ET
from src.models import CollectionError, Item
from src.parsing import number, xml_text


def parse_google(body: bytes, limit: int, geo: str) -> list[Item]:
    root = ET.fromstring(body)
    entries = root.findall('./channel/item')
    if not entries:
        raise CollectionError('Google Trends RSS has no entries; region may be unsupported')
    result = []
    for rank, entry in enumerate(entries[:limit], 1):
        title = xml_text(entry, 'title')
        related = [{'title': xml_text(n, 'news_item_title'), 'url': xml_text(n, 'news_item_url')}
                   for n in entry.findall('{*}news_item')]
        # Feed item links all point to the RSS feed. Build a distinct explore URL per query.
        url = 'https://trends.google.com/trends/explore?' + urlencode({'geo': geo, 'q': title})
        traffic = xml_text(entry, 'approx_traffic')
        result.append(Item('google_trends', geo + ':' + title.casefold(), title, url,
                           published_at=xml_text(entry, 'pubDate'),
                           summary=' | '.join(n['title'] for n in related),
                           metrics={'approx_traffic_label': traffic,
                                    'approx_traffic_lower_bound': number(traffic)},
                           rank=rank, collection_method='official_rss',
                           metadata={'geo': geo, 'related_news': related, 'mode': 'trending_now',
                                     'not_keyword_interest_timeseries': True}))
    return result

class GoogleTrendsSource(BaseSource):
    name = 'google_trends'

    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        http, cfg = self.http, self.config
        limit, days = request.limit, request.days
        geo = cfg.get('geo', 'KR').upper()
        if not re.fullmatch(r'[A-Z]{2}(?:-[A-Z0-9]{1,3})?', geo):
            raise CollectionError('Invalid Google Trends geo code')
        yield from parse_google(http.get('https://trends.google.com/trending/rss?' + urlencode({'geo': geo})), limit, geo)

def collect(http, cfg, limit, days):
    """Compatibility wrapper; use GoogleTrendsSource for dependency injection."""
    return GoogleTrendsSource(http, cfg, credentials=os.environ).collect(CollectionRequest(limit, days))
