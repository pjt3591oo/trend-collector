"""Site-specific collection and parsing."""
from __future__ import annotations

from collections.abc import Iterator
from .base import BaseSource, CollectionRequest

import os

from src.models import CollectionError, Item, iso_date
from src.parsing import plain

class HackerNewsSource(BaseSource):
    name = 'hackernews'

    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        http, cfg = self.http, self.config
        limit, days = request.limit, request.days
        feed = cfg.get('feed', 'top')
        if feed not in ('top', 'new', 'best', 'ask', 'show'):
            raise CollectionError('HN feed must be top/new/best/ask/show')
        base = 'https://hacker-news.firebaseio.com/v0/'
        ids = http.json(base + feed + 'stories.json')
        if not isinstance(ids, list):
            raise CollectionError('Unexpected HN story list')
        for rank, item_id in enumerate(ids[:limit], 1):
            data = http.json(base + f'item/{item_id}.json')
            if not data or data.get('dead') or data.get('deleted') or data.get('type') != 'story':
                continue
            discussion = f'https://news.ycombinator.com/item?id={item_id}'
            yield Item('hackernews', str(item_id), data['title'], data.get('url') or discussion,
                       discussion_url=discussion, published_at=iso_date(data.get('time')),
                       summary=plain(data.get('text')), rank=rank, collection_method='official_api',
                       metrics={'points': data.get('score'), 'comments': data.get('descendants')},
                       metadata={'feed': feed, 'url_kind': 'original' if data.get('url') else 'discussion'})

def collect(http, cfg, limit, days):
    """Compatibility wrapper; use HackerNewsSource for dependency injection."""
    return HackerNewsSource(http, cfg, credentials=os.environ).collect(CollectionRequest(limit, days))
