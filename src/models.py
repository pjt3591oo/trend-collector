"""Shared item model, normalization, and collection errors."""
from __future__ import annotations

import hashlib
import html
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


UTC = timezone.utc


class CollectionError(Exception):
    pass


class Skipped(CollectionError):
    pass


def now() -> str:
    return datetime.now(UTC).isoformat(timespec='microseconds')


def digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def iso_date(value: Any) -> str | None:
    if value is None or value == '':
        return None
    try:
        if isinstance(value, (int, float)):
            date = datetime.fromtimestamp(value, UTC)
        else:
            try:
                date = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            except ValueError:
                date = parsedate_to_datetime(str(value))
        # Do not silently invent a timezone for an ambiguous timestamp.
        return date.astimezone(UTC).isoformat() if date.tzinfo else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def canonical_url(url: str) -> str:
    """Conservative grouping: remove tracking parameters, preserve meaningful queries."""
    parts = urlsplit(html.unescape(url.strip()))
    if parts.scheme.lower() not in ('http', 'https') or not parts.netloc:
        raise CollectionError('Invalid HTTP(S) item URL')
    if parts.username or parts.password:
        raise CollectionError('Item URLs must not contain credentials')
    params = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
              if not k.lower().startswith('utm_')
              and k.lower() not in ('fbclid', 'gclid', 'msclkid')]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or '/',
                       urlencode(sorted(params)), ''))


@dataclass
class Item:
    source: str
    external_id: str
    title: str
    url: str
    discussion_url: str | None = None
    published_at: str | None = None
    summary: str = ''
    tags: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    rank: int | None = None
    collection_method: str = ''
    metadata: dict[str, Any] = field(default_factory=dict)
    observed_at: str = field(default_factory=now)

    def record(self) -> dict:
        row = asdict(self)
        row['canonical_url'] = canonical_url(self.url)
        row['group_id'] = digest(row['canonical_url'])
        row['title'] = html.unescape(self.title).strip()
        row['published_at'] = iso_date(self.published_at)
        if not row['title'] or not row['external_id']:
            raise CollectionError('Item has no title or stable identifier')
        return row
