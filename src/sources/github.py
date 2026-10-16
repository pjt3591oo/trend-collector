"""Site-specific collection and parsing."""
from __future__ import annotations

from collections.abc import Iterator
from .base import BaseSource, CollectionRequest

import os

import re
from urllib.parse import quote, urlencode
from src.models import CollectionError, Item
from src.parsing import Node, number, text


def parse_github(root: Node, limit: int, since: str) -> list[Item]:
    cards = list(root.all('article', cls='Box-row'))
    if not cards:
        raise CollectionError('GitHub HTML changed: repository cards not found')
    result = []
    for rank, card in enumerate(cards[:limit], 1):
        heading = card.first('h2')
        link = heading.first('a') if heading else None
        if not link:
            continue
        path = link.attrs.get('href', '')
        if not re.fullmatch(r'/[^/]+/[^/]+', path):
            continue
        name = path.lstrip('/')
        stars = next((a for a in card.all('a') if a.attrs.get('href') == path + '/stargazers'), None)
        forks = next((a for a in card.all('a') if a.attrs.get('href') == path + '/forks'), None)
        growth = next((n for n in card.all('span') if re.search(r'stars? (today|this week|this month)', text(n))), None)
        language = text(card.first('span', itemprop='programmingLanguage'))
        result.append(Item('github', name, name, 'https://github.com/' + name,
                           summary=text(card.first('p')), tags=[language] if language else [],
                           metrics={'stars_total': number(text(stars)), 'forks_total': number(text(forks)),
                                    'stars_in_period': number(text(growth))},
                           rank=rank, collection_method='public_html',
                           metadata={'period': since, 'url_kind': 'repository'}))
    if not result:
        raise CollectionError('GitHub repository links could not be parsed')
    return result

class GitHubSource(BaseSource):
    name = 'github'

    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        http, cfg = self.http, self.config
        limit, days = request.limit, request.days
        since = cfg.get('since', 'daily')
        if since not in ('daily', 'weekly', 'monthly'):
            raise CollectionError('GitHub since must be daily/weekly/monthly')
        language = cfg.get('language', '')
        path = '/' + quote(language, safe='') if language else ''
        yield from parse_github(http.page('https://github.com/trending' + path + '?' + urlencode({'since': since})), limit, since)

def collect(http, cfg, limit, days):
    """Compatibility wrapper; use GitHubSource for dependency injection."""
    return GitHubSource(http, cfg, credentials=os.environ).collect(CollectionRequest(limit, days))
