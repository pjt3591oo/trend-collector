"""Product Hunt public homepage HTML; no API or token required."""
from collections.abc import Iterator
import re
from urllib.parse import urljoin

from src.models import CollectionError, Item
from src.parsing import Node, number, text
from .base import BaseSource, CollectionRequest


def parse_producthunt(root: Node, limit: int) -> list[Item]:
    section = root.first(**{'data-test': 'homepage-section-today'})
    if section is None:
        raise CollectionError('Product Hunt HTML changed or requires JavaScript: today section missing')
    result = []
    seen = set()
    for card in section.all('section'):
        link = next((a for a in card.all('a')
                     if re.fullmatch(r'/(?:products|posts)/[^/?#]+', a.attrs.get('href', ''))), None)
        if link is None:
            continue
        path = link.attrs['href']
        if path in seen:
            continue
        title = re.sub(r'^\d+\.\s*', '', text(link))
        if not title:
            raise CollectionError('Product Hunt product title missing')
        seen.add(path)
        summary = text(card.first('span', cls='text-secondary'))
        vote = card.first('button', **{'data-test': 'vote-button'})
        date = card.first('time')
        url = urljoin('https://www.producthunt.com/', path)
        result.append(Item('producthunt', path, title, url, discussion_url=url,
                           summary=summary, published_at=date.attrs.get('datetime') if date else None,
                           tags=[text(a) for a in card.all('a') if a.attrs.get('href', '').startswith('/topics/')],
                           metrics={'votes': number(text(vote))}, rank=len(result) + 1,
                           collection_method='public_html',
                           metadata={'feed': 'today', 'url_kind': 'producthunt',
                                     'original_url': None, 'rank_scope': 'today'}))
        if len(result) >= limit:
            break
    if not result:
        raise CollectionError('Product Hunt HTML changed: product cards missing')
    return result


class ProductHuntSource(BaseSource):
    name = 'producthunt'

    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        yield from parse_producthunt(self.http.page('https://www.producthunt.com/'), request.limit)


def collect(http, cfg, limit, days):
    """Compatibility wrapper; days is retained but not used by the HTML feed."""
    return ProductHuntSource(http, cfg).collect(CollectionRequest(limit, days))
