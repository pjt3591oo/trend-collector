"""Common official RSS collection for security news and advisories."""
from collections.abc import Iterator
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

from src.models import CollectionError, Item
from src.parsing import plain, xml_text
from src.security import cve_ids
from .base import BaseSource, CollectionRequest


def parse_security_rss(body: bytes, source: str, feed_url: str,
                       limit: int) -> Iterator[Item]:
    root = ET.fromstring(body)
    channel = root.find('channel')
    if root.tag != 'rss' or channel is None:
        raise CollectionError(f'{source}: expected RSS channel')
    seen = set()
    for entry in channel.findall('item'):
        title = plain(xml_text(entry, 'title'))
        link = xml_text(entry, 'link')
        if not title or not link:
            raise CollectionError(f'{source}: RSS item has no title or link')
        url = urljoin(feed_url, link)
        external_id = xml_text(entry, 'guid') or url
        if external_id in seen:
            continue
        seen.add(external_id)
        summary = plain(xml_text(entry, 'description'))
        yield Item(source, external_id, title, url,
                   published_at=xml_text(entry, 'pubDate'), summary=summary,
                   tags=['security'] + [plain(''.join(e.itertext())) for e in entry.findall('category')],
                   rank=len(seen), collection_method='official_rss',
                   metadata={'cve_ids': cve_ids(title, summary), 'feed_url': feed_url})
        if len(seen) >= limit:
            break


class SecurityRSSSource(BaseSource):
    feed_url: str

    def collect(self, request: CollectionRequest) -> Iterator[Item]:
        yield from parse_security_rss(self.http.get(self.feed_url), self.name,
                                     self.feed_url, request.limit)
