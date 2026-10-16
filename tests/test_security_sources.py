import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

from src.enrichment import EPSSEnricher
from src.models import CollectionError, Item
from src.sources import (BleepingComputerSource, CISAKEVSource, CollectionRequest,
                     GitHubAdvisoriesSource, KISASource)
from trend_collector import main


RSS = b'''<rss version="2.0"><channel><title>Security</title><item>
<guid>article-1</guid><title>Fix CVE-2026-12345</title>
<link>https://news.test/1</link><pubDate>Fri, 16 Oct 2026 09:00:00 +0900</pubDate>
<description>&lt;p&gt;Patch cve-2026-12345 and CVE-2026-99999&lt;/p&gt;</description>
<category>Vulnerabilities</category></item></channel></rss>'''


class SecuritySourceTests(unittest.TestCase):
    def test_both_rss_sources_preserve_cves_dates_and_source_identity(self):
        for cls in (BleepingComputerSource, KISASource):
            with self.subTest(source=cls.name):
                http = Mock()
                http.get.return_value = RSS
                rows = [item.record() for item in cls(http).collect(CollectionRequest(limit=1))]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['source'], cls.name)
                self.assertEqual(rows[0]['metadata']['cve_ids'], ['CVE-2026-12345', 'CVE-2026-99999'])
                self.assertEqual(rows[0]['published_at'], '2026-10-16T00:00:00+00:00')
                self.assertNotIn('<p>', rows[0]['summary'])
                http.get.assert_called_once_with(cls.feed_url)

    def test_rss_rejects_html_and_treats_valid_empty_feed_as_empty(self):
        http = Mock()
        http.get.return_value = b'<html>Access denied</html>'
        with self.assertRaises(CollectionError):
            list(KISASource(http).collect(CollectionRequest()))
        http.get.return_value = b'<rss><channel/></rss>'
        self.assertEqual(list(KISASource(http).collect(CollectionRequest())), [])

    def test_kev_sorts_by_date_added_and_preserves_exploitation_evidence(self):
        http = Mock()
        http.json.return_value = {'catalogVersion': 'v1', 'vulnerabilities': [
            {'cveID': 'CVE-2026-12345', 'vulnerabilityName': 'Old', 'dateAdded': '2026-10-01'},
            {'cveID': 'CVE-2026-99999', 'vulnerabilityName': 'New', 'dateAdded': '2026-10-16',
             'knownRansomwareCampaignUse': 'Known', 'requiredAction': 'Patch'}]}
        row = next(CISAKEVSource(http).collect(CollectionRequest(limit=1))).record()
        self.assertEqual(row['external_id'], 'CVE-2026-99999')
        self.assertIsNone(row['published_at'])
        self.assertTrue(row['metrics']['known_exploited'])
        self.assertEqual(row['metadata']['date_added'], '2026-10-16')
        self.assertEqual(row['metadata']['required_action'], 'Patch')

    def test_kev_invalid_schema_is_an_error(self):
        http = Mock()
        http.json.return_value = {'message': 'blocked'}
        with self.assertRaises(CollectionError):
            list(CISAKEVSource(http).collect(CollectionRequest()))

class EPSSTests(unittest.TestCase):
    def row(self, *cves):
        return Item('test', '1', 'Test', 'https://x.test/1', metadata={'cve_ids': list(cves)}).record()

    def test_batch_lookup_deduplicates_and_preserves_missing_as_unknown(self):
        http = Mock()
        http.json.return_value = {'status': 'OK', 'data': [
            {'cve': 'CVE-2026-12345', 'epss': '0.25', 'percentile': '0.9', 'date': '2026-10-16'}]}
        rows = [self.row('CVE-2026-12345'), self.row('CVE-2026-12345', 'CVE-2026-99999')]
        status = EPSSEnricher(http).enrich(rows)
        self.assertEqual(status['requested_cves'], 2)
        self.assertEqual(status['missing_cves'], ['CVE-2026-99999'])
        self.assertEqual(rows[0]['metrics']['epss']['CVE-2026-12345']['probability'], 0.25)
        self.assertNotIn('CVE-2026-99999', rows[1]['metrics']['epss'])
        http.json.assert_called_once()

    def test_no_cves_makes_no_request(self):
        http = Mock()
        self.assertEqual(EPSSEnricher(http).enrich([self.row()])['status'], 'empty')
        http.json.assert_not_called()

    def test_failed_batch_does_not_drop_successful_batches(self):
        http = Mock()
        cves = [f'CVE-2026-{i:05}' for i in range(101)]
        http.json.side_effect = [
            {'status': 'OK', 'data': [{'cve': cves[0], 'epss': '0.1', 'percentile': '0.5', 'date': '2026-10-16'}]},
            CollectionError('EPSS unavailable')]
        rows = [self.row(*cves)]
        status = EPSSEnricher(http).enrich(rows)
        self.assertEqual(status['status'], 'partial')
        self.assertEqual(status['matched_cves'], 1)
        self.assertIn(cves[0], rows[0]['metrics']['epss'])

    def test_invalid_scores_do_not_become_metrics(self):
        http = Mock()
        http.json.return_value = {'status': 'OK', 'data': [
            {'cve': 'CVE-2026-12345', 'epss': 'nan', 'percentile': '0.5', 'date': '2026-10-16'}]}
        rows = [self.row('CVE-2026-12345')]
        self.assertEqual(EPSSEnricher(http).enrich(rows)['status'], 'error')
        self.assertNotIn('epss', rows[0]['metrics'])

    def test_enrichment_failure_still_saves_sources_and_fails_strict(self):
        class CustomSource:
            name = 'custom'

            def collect(self, request):
                yield Item(self.name, '1', 'Security', 'https://x.test/1',
                           metadata={'cve_ids': ['CVE-2026-12345']})

        http = Mock()
        http.json.side_effect = CollectionError('Unavailable')
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            code = main(['--out', tmp, '--strict'], sources={'custom': CustomSource()}, enricher=EPSSEnricher(http))
            folder = next((Path(tmp) / 'runs').iterdir())
            manifest = json.loads((folder / 'manifest.json').read_text())
            saved = json.loads((folder / 'items.jsonl').read_text())
        self.assertEqual(code, 1)
        self.assertEqual(manifest['sources']['custom']['status'], 'ok')
        self.assertEqual(manifest['enrichment']['epss']['status'], 'error')
        self.assertEqual(saved['external_id'], '1')


if __name__ == '__main__':
    unittest.main()
