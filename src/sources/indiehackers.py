"""Site-specific collection and parsing."""
from __future__ import annotations

from collections.abc import Iterator
from .base import BaseSource, CollectionRequest

import os

from urllib.parse import urljoin
from src.models import CollectionError, Item, canonical_url
from src.parsing import Node, number, text


def parse_indiehackers(root: Node, limit: int) -> list[Item]:
    result = []
    seen = set()
    for card in root.all(cls='story'):
        link = card.first('a', cls='story__text-link')
        if not link:
            continue
        url = urljoin('https://www.indiehackers.com/', link.attrs.get('href', ''))
        title = text(card.first(cls='story__title'))
        if not title or url in seen:
            continue
        seen.add(url)
        date = card.first('time')
        result.append(Item('indiehackers', canonical_url(url), title, url, discussion_url=url,
                           published_at=date.attrs.get('datetime') if date else None,
                           summary=text(card.first(cls='story__summary')),
                           metrics={'votes': number(text(card.first(cls='story__count--likes'))),
                                    'comments': number(text(card.first(cls='story__count--comments')))},
                           rank=len(result) + 1, collection_method='public_html',
                           metadata={'scope': 'homepage_visible_cards'}))
        if len(result) >= limit:
            break
    if not result:
        raise CollectionError('Indie Hackers HTML changed or requires JavaScript: no story cards')
    return result

class IndieHackersSource(BaseSource):
    name = 'indiehackers'

    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        http, cfg = self.http, self.config
        limit, days = request.limit, request.days
        yield from parse_indiehackers(http.page('https://www.indiehackers.com/'), limit)

def collect(http, cfg, limit, days):
    """Compatibility wrapper; use IndieHackersSource for dependency injection."""
    return IndieHackersSource(http, cfg, credentials=os.environ).collect(CollectionRequest(limit, days))
