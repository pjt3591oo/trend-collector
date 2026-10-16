import contextlib
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import tempfile
from threading import Barrier, Event
import unittest
from unittest.mock import patch

from src.http_client import HTTP
from src.models import CollectionError, Item
from trend_collector import main


class ParallelCollectionTests(unittest.TestCase):
    def test_sources_overlap_and_partial_results_are_saved_in_source_order(self):
        barrier = Barrier(2)

        class FakeSource:
            def __init__(self, name, fails=False):
                self.name, self.fails = name, fails

            def collect(self, request):
                barrier.wait(timeout=3)
                yield Item(self.name, '1', self.name, 'https://example.com/' + self.name)
                if self.fails:
                    raise CollectionError('Later page failed')

        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            code = main(['--out', tmp, '--strict'],
                        sources={'first': FakeSource('first', True), 'second': FakeSource('second')})
            folder = next((Path(tmp) / 'runs').iterdir())
            manifest = json.loads((folder / 'manifest.json').read_text())
            rows = [json.loads(line) for line in (folder / 'items.jsonl').read_text().splitlines()]
        self.assertEqual(code, 1)
        self.assertEqual(manifest['sources']['first']['status'], 'partial')
        self.assertEqual(manifest['sources']['second']['status'], 'ok')
        self.assertEqual([row['source'] for row in rows], ['first', 'second'])

    def test_worker_limit_one_runs_sequentially(self):
        order = []

        class FakeSource:
            def __init__(self, name):
                self.name = name

            def collect(self, request):
                order.append(self.name)
                yield Item(self.name, '1', self.name, 'https://example.com/')

        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            config = Path(tmp) / 'config.toml'
            config.write_text('[collector]\nmax_workers=1\n[sources.a]\n[sources.b]\n')
            code = main(['--config', str(config), '--out', tmp],
                        sources={'a': FakeSource('a'), 'b': FakeSource('b')})
        self.assertEqual(code, 0)
        self.assertEqual(order, ['a', 'b'])

    def test_shared_http_allows_different_hosts_to_overlap(self):
        barrier = Barrier(2)
        client = HTTP({'request_interval': 0})

        class FakeOpener:
            def open(self, request, timeout):
                barrier.wait(timeout=3)
                return contextlib.nullcontext(io.BytesIO(b'page'))

        with patch('src.http_client.build_opener', side_effect=lambda *args: FakeOpener()):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(client.get, url) for url in ('https://a.test/', 'https://b.test/')]
                self.assertEqual([future.result(timeout=5) for future in futures], [b'page', b'page'])

    def test_shared_http_serializes_same_host_requests(self):
        client = HTTP({'request_interval': 0})
        first_entered, release_first, second_started = Event(), Event(), Event()
        entries = []

        def fake_get(url, *args):
            entries.append(url)
            if url.endswith('/first'):
                first_entered.set()
                if not release_first.wait(timeout=3):
                    raise AssertionError('First request not released')
            return b'page'

        def second_request():
            second_started.set()
            return client.get('https://a.test/second')

        with patch.object(client, '_get', side_effect=fake_get), ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(client.get, 'https://a.test/first')
            try:
                self.assertTrue(first_entered.wait(timeout=3))
                second = executor.submit(second_request)
                self.assertTrue(second_started.wait(timeout=3))
                self.assertEqual(entries, ['https://a.test/first'])
            finally:
                release_first.set()
            self.assertEqual(first.result(timeout=3), b'page')
            self.assertEqual(second.result(timeout=3), b'page')
        self.assertEqual(entries, ['https://a.test/first', 'https://a.test/second'])


if __name__ == '__main__':
    unittest.main()
