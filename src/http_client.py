"""HTTP transport, retries, pacing, and HTML parsing."""
from __future__ import annotations

import json
import time
from threading import Lock, local
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from src.models import CollectionError, UTC, iso_date
from src.parsing import Document, Node


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old_origin = (urlsplit(req.full_url).scheme, urlsplit(req.full_url).netloc)
        new_origin = (urlsplit(newurl).scheme, urlsplit(newurl).netloc)
        if req.has_header('Authorization') and old_origin != new_origin:
            raise CollectionError('Cross-origin redirect rejected for authenticated request')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HTTP:
    """Timeouts, per-host pacing, bounded retries, and HTML page requests."""
    def __init__(self, settings: dict):
        self.user_agent = settings.get('user_agent', 'TrendCollector/1.0 (personal trend research)')
        self.timeout = float(settings.get('timeout', 20))
        self.retries = int(settings.get('retries', 2))
        self.interval = float(settings.get('request_interval', 1.0))
        if self.timeout <= 0 or self.retries < 0 or self.interval < 0:
            raise ValueError('Invalid HTTP timeout, retries, or request interval')
        self._local = local()
        self._hosts_guard = Lock()
        self._host_locks = {}
        self.last: dict[str, float] = {}

    @property
    def opener(self):
        if not hasattr(self._local, 'opener'):
            self._local.opener = build_opener(SafeRedirect())
        return self._local.opener

    def get(self, url: str, headers: dict | None = None, payload: dict | None = None) -> bytes:
        host = urlsplit(url).netloc
        with self._hosts_guard:
            host_lock = self._host_locks.setdefault(host, Lock())
        # Same-host requests (including retries) are serialized; other hosts proceed independently.
        with host_lock:
            return self._get(url, headers, payload)

    def _get(self, url: str, headers: dict | None = None, payload: dict | None = None) -> bytes:
        host = urlsplit(url).hostname or 'unknown host'
        for attempt in range(self.retries + 1):
            time.sleep(max(0, self.interval - (time.monotonic() - self.last.get(host, 0))))
            self.last[host] = time.monotonic()
            request_headers = {'User-Agent': self.user_agent, 'Accept': '*/*'}
            request_headers.update(headers or {})
            if any('\r' in str(value) or '\n' in str(value) for value in request_headers.values()):
                raise CollectionError('Invalid HTTP header configuration')
            data = None
            if payload is not None:
                data = json.dumps(payload).encode('utf-8')
                request_headers['Content-Type'] = 'application/json'
            try:
                with self.opener.open(Request(url, data=data, headers=request_headers),
                                      timeout=self.timeout) as response:
                    body = response.read(8_000_001)
                    if len(body) > 8_000_000:
                        raise CollectionError('Response exceeds 8 MB limit')
                    return body
            except HTTPError as exc:
                status = exc.code
                retry_after = exc.headers.get('Retry-After', '')
                exc.close()
                if status not in (429, 500, 502, 503, 504) or attempt == self.retries:
                    raise CollectionError(f'HTTP {status} from {host}') from None
                wait = 2 ** attempt
                if retry_after:
                    try:
                        wait = max(wait, float(retry_after))
                    except ValueError:
                        retry_time = iso_date(retry_after)
                        if retry_time:
                            wait = max(wait, (datetime.fromisoformat(retry_time) - datetime.now(UTC)).total_seconds())
                if wait > 60:
                    raise CollectionError(f'HTTP {status}: server requests a longer wait; rerun later')
                time.sleep(wait)
            except (ValueError, UnicodeError):
                raise CollectionError('Invalid HTTP request configuration') from None
            except (URLError, TimeoutError, OSError):
                if attempt == self.retries:
                    raise CollectionError(f'Network or TLS connection failed for {host}') from None
                time.sleep(2 ** attempt)
        raise CollectionError('Request failed')

    def json(self, url, headers=None, payload=None):
        return json.loads(self.get(url, headers, payload))

    def page(self, url: str) -> Node:
        return Document(self.get(url).decode('utf-8', 'replace')).root
