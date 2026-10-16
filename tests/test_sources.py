import contextlib
import io
import json
import os
from collections.abc import Iterator
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.models import Item, Skipped
from src.sources import CollectionRequest, GeekNewsSource, HuggingFaceSource, create_sources
from trend_collector import main


class SourceInjectionTests(unittest.TestCase):
    def test_every_source_is_lazy_and_returns_an_iterator(self):
        # Missing HTTP is safe until iteration, including HTML/feed sources.
        for name, source in create_sources(None, credentials={}).items():
            with self.subTest(source=name):
                self.assertEqual(source.name, name)
                self.assertIsInstance(source.collect(CollectionRequest()), Iterator)

    def test_feed_uses_injected_http_and_request_limit(self):
        body = b'''<feed xmlns="http://www.w3.org/2005/Atom">
          <entry><id>1</id><title>First</title><link href="https://x.test/1"/></entry>
          <entry><id>2</id><title>Second</title><link href="https://x.test/2"/></entry>
        </feed>'''

        class FakeHTTP:
            def get(self, url):
                self.url = url
                return body

        http = FakeHTTP()
        rows = list(GeekNewsSource(http).collect(CollectionRequest(limit=1)))
        self.assertEqual([row.title for row in rows], ['First'])
        self.assertEqual(http.url, 'https://news.hada.io/rss/news')

    def test_credentials_are_injected_without_reading_environment(self):
        class FakeHTTP:
            def json(self, url, headers=None):
                self.headers = headers
                return [{'id': 'org/model'}]

        http = FakeHTTP()
        with patch.dict(os.environ, {'HF_TOKEN': 'environment-token'}):
            list(HuggingFaceSource(http, credentials={'HF_TOKEN': 'injected-token'})
                 .collect(CollectionRequest()))
            self.assertEqual(http.headers, {'Authorization': 'Bearer injected-token'})
            list(HuggingFaceSource(http, credentials={}).collect(CollectionRequest()))
            self.assertIsNone(http.headers)
    def test_custom_source_runs_without_constructing_default_http(self):
        class CustomSource:
            name = 'custom'

            def collect(self, request):
                self.request = request
                yield Item(self.name, '1', 'Injected item', 'https://x.test/1')

        source = CustomSource()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            with patch('trend_collector.HTTP', side_effect=AssertionError('Unexpected HTTP creation')):
                code = main(['--out', tmp, '--limit', '3'], sources={'custom': source})
            manifest = json.loads(next((Path(tmp) / 'runs').glob('*/manifest.json')).read_text())
        self.assertEqual(code, 0)
        self.assertEqual(source.request, CollectionRequest(limit=3))
        self.assertEqual(manifest['sources']['custom']['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
