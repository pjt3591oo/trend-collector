import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from src.models import Item
from src.storage import save_database
from src.viewer.repository import TrendRepository


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'trends.sqlite3'
        self.repo = TrendRepository(self.path)

    def populate(self):
        a = Item('github', '1', 'First title', 'https://example.com/1', metrics={'stars': 1}).record()
        b = Item('kisa', '2', 'CVE-2026-12345', 'https://example.com/2').record()
        a['observed_at'] = '2026-10-16T00:00:00+00:00'
        save_database(self.path, 'run1', [a, b], {'github': {'status': 'ok', 'count': 1}, 'kisa': {'status': 'ok', 'count': 1}}, '2026-10-16T00:00:00+00:00')
        a['title'] = 'Updated title'
        a['metrics'] = {'stars': 2}
        a['observed_at'] = '2026-10-17T00:00:00+00:00'
        save_database(self.path, 'run2', [a], {'github': {'status': 'ok', 'count': 1}}, '2026-10-17T00:00:00+00:00')

    def test_missing_database_is_empty_and_not_created(self):
        self.assertFalse(self.repo.summary()['ready'])
        self.assertEqual(self.repo.items()['rows'], [])
        self.assertEqual(self.repo.runs()['total'], 0)
        self.assertIsNone(self.repo.item('github', '1'))
        self.assertFalse(self.path.exists())

    def test_summary_counts_latest_items_separately_from_observations(self):
        self.populate()
        summary = self.repo.summary()
        self.assertEqual((summary['items'], summary['runs'], summary['observations']), (2, 2, 3))
        self.assertEqual(summary['latest_run']['run_id'], 'run2')

    def test_source_search_and_pagination(self):
        self.populate()
        self.assertEqual(self.repo.items(source='kisa')['rows'][0]['title'], 'CVE-2026-12345')
        self.assertEqual(self.repo.items(query='updated')['total'], 1)
        self.assertEqual(self.repo.items(query="' OR 1=1 --")['total'], 0)
        self.assertEqual(self.repo.items(query='%')['total'], 0)
        self.assertEqual(len(self.repo.items(page=2, page_size=1)['rows']), 1)

    def test_run_filter_returns_historical_record_not_latest(self):
        self.populate()
        old = self.repo.items(source='github', run_id='run1')['rows'][0]
        self.assertEqual(old['title'], 'First title')
        self.assertEqual(old['metrics']['stars'], 1)
        self.assertEqual(self.repo.item('github', '1', 'run1')['item']['title'], 'First title')
        self.assertEqual(self.repo.item('github', '1')['item']['title'], 'Updated title')
        self.assertEqual(len(self.repo.item('github', '1')['history']), 2)

    def test_runs_are_paginated_and_statuses_decoded(self):
        self.populate()
        runs = self.repo.runs(page_size=1)
        self.assertEqual(runs['total'], 2)
        self.assertEqual(runs['rows'][0]['run_id'], 'run2')
        self.assertEqual(runs['rows'][0]['sources']['github']['status'], 'ok')

    def test_connections_reject_writes(self):
        self.populate()
        with self.repo.connect() as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute('DELETE FROM items')
        self.assertEqual(self.repo.summary()['items'], 2)


if __name__ == '__main__':
    unittest.main()
