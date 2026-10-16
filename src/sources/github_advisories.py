"""GitHub Advisory Database public HTML listings; no API or token."""
from collections.abc import Iterator
import re
from urllib.parse import urlencode, urljoin, urlsplit

from src.models import CollectionError, Item
from src.parsing import Node, text
from src.security import cve_ids
from .base import BaseSource, CollectionRequest


def parse_github_advisories(root: Node, limit: int) -> list[Item]:
    result = []
    seen = set()
    for card in root.all('div', cls='Box-row'):
        link = next((a for a in card.all('a')
                     if re.fullmatch(r'/advisories/GHSA-[a-z0-9-]+', a.attrs.get('href', ''))), None)
        if link is None:
            continue
        content = text(card)
        if re.search(r'\bwithdrawn\b', content, re.I):
            continue
        path = link.attrs['href']
        if path in seen:
            continue
        seen.add(path)
        if not text(link):
            raise CollectionError('GitHub advisory title missing')
        severity = re.search(r'\b(Critical|High|Moderate|Medium|Low)\b', content[len(text(link)):], re.I)
        date = card.first('relative-time') or card.first('time')
        result.append(Item('github_advisories', path.rsplit('/', 1)[1], text(link),
                           urljoin('https://github.com', path), summary='',
                           published_at=date.attrs.get('datetime') if date else None,
                           tags=['security'], rank=len(result) + 1, collection_method='public_html',
                           metadata={'cve_ids': cve_ids(content),
                                     'severity': severity[1].lower().replace('moderate', 'medium') if severity else None,
                                     'scope': 'reviewed_listing', 'listing_text': content}))
        if len(result) >= limit:
            break
    if not result and not any('no advisories' in text(n).lower() for n in root.all(cls='blankslate')):
        raise CollectionError('GitHub Advisories HTML changed: advisory cards missing')
    return result


class GitHubAdvisoriesSource(BaseSource):
    name = 'github_advisories'

    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        query = 'type:reviewed -is:withdrawn sort:published-desc'
        for key in ('ecosystem', 'severity'):
            value = self.config.get(key)
            if value:
                if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9_-]+', value):
                    raise CollectionError(f'Invalid GitHub advisory {key}')
                query += f' {key}:{value}'
        url = 'https://github.com/advisories?' + urlencode({'query': query})
        seen = set()
        visited = set()
        while url:
            if url in visited:
                raise CollectionError('GitHub advisory pagination did not advance')
            visited.add(url)
            root = self.http.page(url)
            added = 0
            for item in parse_github_advisories(root, request.limit - len(seen)):
                if item.external_id in seen:
                    continue
                seen.add(item.external_id)
                added += 1
                item.rank = len(seen)
                yield item
                if len(seen) >= request.limit:
                    return
            link = root.first('a', cls='next_page') or root.first('a', rel='next')
            if link is None:
                return
            if not added:
                raise CollectionError('GitHub advisory pagination produced no new items')
            url = urljoin(url, link.attrs.get('href', ''))
            parts = urlsplit(url)
            if parts.scheme != 'https' or parts.netloc != 'github.com' or parts.path != '/advisories':
                raise CollectionError('Unexpected GitHub advisory pagination URL')
