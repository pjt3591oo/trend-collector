"""Site-specific collection and parsing."""
from __future__ import annotations

from collections.abc import Iterator
from .base import BaseSource, CollectionRequest

import os

from urllib.parse import urljoin
from src.models import CollectionError, Item
from src.parsing import Node, number, text


def parse_disquiet(root: Node, limit: int) -> list[Item]:
    result = []
    for card in root.all('article'):
        path = card.attrs.get('data-disquiet--post-card-url-value', '')
        if not path.startswith('/posts/'):
            continue
        body = next((n for n in card.all('div') if n.attrs.get('id', '').startswith('body_disquiet_post_')), None)
        summary = text(body)
        if not summary:
            continue
        product = next((a for a in card.all('a') if a.attrs.get('href', '').startswith('/products/')), None)
        comments = next((a for a in card.all('a') if a.attrs.get('href') == path and '댓글' in a.attrs.get('aria-label', '')), None)
        votes = next((n for n in card.all('span') if n.attrs.get('aria-label', '').startswith('추천 ')), None)
        date = card.first('time')
        url = urljoin('https://disquiet.io/', path)
        result.append(Item('disquiet', path.removeprefix('/posts/'), summary[:160], url,
                           discussion_url=url, published_at=date.attrs.get('datetime') if date else None,
                           summary=summary[:5000],
                           metrics={'votes': number(votes.attrs.get('aria-label', '')) if votes else None,
                                    'comments': number(text(comments))},
                           rank=len(result) + 1, collection_method='public_html',
                           metadata={'title_derived_from_body': True,
                                     'product_url': urljoin('https://disquiet.io/', product.attrs['href']) if product else None,
                                     'product_name': text(product.first('p')) if product else None,
                                     'scope': 'homepage_visible_posts'}))
        if len(result) >= limit:
            break
    if not result:
        raise CollectionError('Disquiet HTML changed or requires JavaScript: no public post cards')
    return result

class DisquietSource(BaseSource):
    name = 'disquiet'

    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        http, cfg = self.http, self.config
        limit, days = request.limit, request.days
        yield from parse_disquiet(http.page('https://disquiet.io/'), limit)

def collect(http, cfg, limit, days):
    """Compatibility wrapper; use DisquietSource for dependency injection."""
    return DisquietSource(http, cfg, credentials=os.environ).collect(CollectionRequest(limit, days))
