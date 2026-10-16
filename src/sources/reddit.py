"""Reddit public old-layout HTML; access is subject to robots policy."""
from collections.abc import Iterator
import re
from urllib.parse import urlencode, urljoin, urlsplit

from src.models import CollectionError, Item
from src.parsing import Node, number, text
from .base import BaseSource, CollectionRequest


def parse_reddit(root: Node, limit: int, subreddit: str, sort: str) -> list[Item]:
    listing = root.first(**{'id': 'siteTable'})
    if listing is None:
        raise CollectionError('Reddit HTML changed or requires login: listing missing')
    cards = list(listing.all(cls='thing'))
    if not cards and listing.first(cls='noresults') is None and 'no posts' not in text(listing).lower():
        raise CollectionError('Reddit HTML changed: post cards missing')
    result = []
    seen = set()
    for card in cards:
        if 'promoted' in card.attrs.get('class', '').split():
            continue
        identifier = card.attrs.get('data-fullname', '')
        title = card.first('a', cls='title')
        if not identifier.startswith('t3_') or title is None or not text(title):
            raise CollectionError('Reddit post identity or title missing')
        if identifier in seen:
            continue
        seen.add(identifier)
        comments = card.first('a', cls='comments')
        permalink = card.attrs.get('data-permalink') or (comments.attrs.get('href') if comments else None)
        if not permalink:
            raise CollectionError('Reddit post permalink missing')
        discussion = urljoin('https://old.reddit.com/', permalink)
        url = urljoin('https://old.reddit.com/', title.attrs.get('href') or permalink)
        score = card.first(cls='score', **{'title': card.attrs.get('data-score', '')}) or card.first(cls='score')
        score_value = card.attrs.get('data-score')
        if score_value is None and score:
            score_value = score.attrs.get('title') or text(score)
        parsed_score = (int(score_value) if score_value and re.fullmatch(r'-?\d+', score_value)
                        else number(score_value or ''))
        date = card.first('time')
        result.append(Item('reddit', identifier, text(title), url, discussion_url=discussion,
                           published_at=date.attrs.get('datetime') if date else None,
                           tags=[subreddit], metrics={'score': parsed_score,
                                                     'comments': number(text(comments))},
                           rank=len(result) + 1, collection_method='public_html',
                           metadata={'subreddit': subreddit, 'sort': sort, 'rank_scope': 'subreddit',
                                     'url_kind': 'original' if url != discussion else 'discussion'}))
        if len(result) >= limit:
            break
    return result


class RedditSource(BaseSource):
    name = 'reddit'

    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        subreddits = self.config.get('subreddits', ['SaaS', 'smallbusiness', 'SideProject'])
        sort = self.config.get('sort', 'new')
        if not isinstance(subreddits, list) or not subreddits or sort not in ('new', 'hot', 'top'):
            raise CollectionError('Reddit requires subreddits and sort=new/hot/top')
        if any(not isinstance(s, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,50}', s) for s in subreddits):
            raise CollectionError('Invalid subreddit name')
        subreddits = list(dict.fromkeys(subreddits))
        seen = set()
        for index, subreddit in enumerate(subreddits):
            allocation = request.limit // len(subreddits) + (index < request.limit % len(subreddits))
            if not allocation:
                continue
            params = {'limit': min(100, allocation)}
            if sort == 'top':
                params['t'] = self.config.get('time_filter', 'week')
            url = f'https://old.reddit.com/r/{subreddit}/{sort}/?' + urlencode(params)
            visited = set()
            fetched = 0
            while url and fetched < allocation:
                if url in visited:
                    raise CollectionError('Reddit returned a non-advancing pagination link')
                visited.add(url)
                root = self.http.page(url)
                items = parse_reddit(root, allocation - fetched, subreddit, sort)
                added = 0
                for item in items:
                    if item.external_id in seen:
                        continue
                    seen.add(item.external_id)
                    fetched += 1
                    added += 1
                    item.rank = fetched
                    yield item
                next_button = root.first(cls='next-button')
                link = next_button.first('a') if next_button else None
                if link is None or fetched >= allocation:
                    break
                if not added:
                    raise CollectionError('Reddit pagination produced no new items')
                url = urljoin(url, link.attrs.get('href', ''))
                parts = urlsplit(url)
                if parts.scheme != 'https' or parts.netloc != 'old.reddit.com' or parts.path != f'/r/{subreddit}/{sort}/':
                    raise CollectionError('Reddit returned an unexpected pagination URL')


def collect(http, cfg, limit, days):
    return RedditSource(http, cfg).collect(CollectionRequest(limit, days))
