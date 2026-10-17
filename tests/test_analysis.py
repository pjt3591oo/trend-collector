from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from src.analysis.classification import classify
from src.analysis.engine import analyze
from src.analysis.grouping import groups
from src.analysis.reporting import save_analysis
from src.models import Item
from src.storage import save_database
from src.viewer.repository import TrendRepository


END = datetime(2026, 10, 17, tzinfo=timezone.utc)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'trends.sqlite3'

    def save(self, run, time, rows):
        for row in rows:
            row['observed_at'] = time
        statuses = {source: {'status': 'ok', 'count': sum(r['source'] == source for r in rows)}
                    for source in {r['source'] for r in rows}}
        save_database(self.path, run, rows, statuses, time)

    def item(self, source='hackernews', id='1', title='Claude SDK', url='https://example.com/tool', **kwargs):
        return Item(source, id, title, url, **kwargs).record()

    def test_repeated_observations_are_not_extra_mentions_and_deltas_are_per_item(self):
        self.save('old', '2026-10-14T00:00:00+00:00', [self.item(metrics={'points': 1})])
        self.save('base', '2026-10-15T12:00:00+00:00', [self.item(metrics={'points': 5})])
        self.save('current1', '2026-10-16T12:00:00+00:00', [self.item(metrics={'points': 10})])
        self.save('current2', '2026-10-16T18:00:00+00:00', [self.item(metrics={'points': 15}),
                                                             self.item(id='2', url='https://example.com/tool2')])
        report = analyze(self.path, end=END)
        self.assertEqual(report['summary']['items'], 2)
        self.assertEqual(report['summary']['observations'], 3)
        self.assertEqual(report['summary']['new_items'], 1)
        trend = next(t for t in report['trends'] if t['name'] == 'Claude')
        self.assertEqual(trend['comparable_item_delta'], 1)
        self.assertTrue(trend['increasing'])
        self.assertEqual(report['metric_changes'][0]['metrics']['points']['delta'], 10)

    def test_cve_links_sources_and_does_not_sum_incompatible_metrics(self):
        self.save('current', '2026-10-16T12:00:00+00:00', [
            self.item(source='cisa_kev', title='CVE-2026-12345', metrics={'known_exploited': True}),
            self.item(source='github_advisories', title='Fix', url='https://other.test/',
                      metadata={'cve_ids': ['CVE-2026-12345']}, metrics={'epss': {'CVE-2026-12345': {'probability': .5}}})])
        report = analyze(self.path, end=END)
        self.assertEqual(len(report['trends']), 1)
        trend = report['trends'][0]
        self.assertTrue(trend['multi_source'])
        self.assertEqual(trend['name'], 'CVE-2026-12345')
        self.assertEqual(trend['items'], 2)
        self.assertTrue(trend['evidence'][0]['metrics']['known_exploited'])
        self.assertIsNone(trend['comparable_item_delta'])

    def test_insufficient_history_never_claims_growth(self):
        self.save('base', '2026-10-15T20:00:00+00:00', [self.item()])
        self.save('current', '2026-10-16T20:00:00+00:00', [self.item(), self.item(id='2')])
        report = analyze(self.path, end=END)
        self.assertFalse(report['coverage']['comparable'])
        self.assertTrue(all(not t['increasing'] for t in report['trends']))

    def test_half_open_window_and_no_future_latest_record_leak(self):
        self.save('start', '2026-10-16T00:00:00+00:00', [self.item(title='Python old title')])
        self.save('future', '2026-10-17T00:00:00+00:00', [self.item(title='Future title')])
        report = analyze(self.path, end=END)
        self.assertEqual(report['summary']['items'], 1)
        self.assertEqual(report['trends'][0]['evidence'][0]['title'], 'Python old title')

    def test_classification_and_groups_are_explainable(self):
        row = self.item(title='Python AI SDK')
        topics = classify(row)
        self.assertIn('AI', topics)
        self.assertIn('개발 도구', topics)
        self.assertIn('python', topics['개발 도구'])
        row['url'] = 'https://github.com/Org/Repo'
        self.assertEqual(groups(row, {})[0][0], 'repo:org/repo')

    def test_store_separately_and_viewer_can_read_previous_versions(self):
        self.save('current', '2026-10-16T20:00:00+00:00', [self.item()])
        repo = TrendRepository(self.path)
        self.assertEqual(repo.analyses()['rows'], [])
        before = repo.summary()['observations']
        report = analyze(self.path, end=END)
        folder = save_analysis(self.path, report, 'analysis1', Path(self.tmp.name) / 'reports')
        self.assertTrue((folder / 'report.md').is_file())
        self.assertEqual(json.loads((folder / 'report.json').read_text(encoding='utf-8'))['version'], 'rules-v1')
        saved = repo.analyses('analysis1')['report']
        self.assertEqual(saved['analysis_id'], 'analysis1')
        self.assertEqual(repo.summary()['observations'], before)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM analysis_members').fetchone()[0], 1)

    def test_empty_window_is_valid_report(self):
        self.save('old', '2026-10-01T20:00:00+00:00', [self.item()])
        report = analyze(self.path, end=END)
        self.assertEqual(report['summary']['items'], 0)
        self.assertEqual(report['trends'], [])


if __name__ == '__main__':
    unittest.main()
