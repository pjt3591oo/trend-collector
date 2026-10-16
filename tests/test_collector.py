import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import trend_collector as tc


class NormalizationTests(unittest.TestCase):
    def test_tracking_removed_but_meaningful_query_preserved(self):
        self.assertEqual(tc.canonical_url('https://EXAMPLE.com/topic?id=42&utm_source=hn#comments'),
                         'https://example.com/topic?id=42')
        self.assertNotEqual(tc.canonical_url('https://x.test/?id=1'), tc.canonical_url('https://x.test/?id=2'))

    def test_same_article_keeps_two_source_observations(self):
        a = tc.Item('geeknews', 'a', 'A', 'https://x.test/a?utm_source=gn').record()
        b = tc.Item('hackernews', 'b', 'B', 'https://x.test/a').record()
        self.assertEqual(a['group_id'], b['group_id'])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.sqlite3'
            tc.save_database(path, 'run1', [a, b], {}, tc.now())
            a['metrics'] = {'points': 100}
            a['observed_at'] = tc.now()
            tc.save_database(path, 'run2', [a], {}, tc.now())
            with contextlib.closing(sqlite3.connect(path)) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM items').fetchone()[0], 2)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0], 3)
                latest = json.loads(db.execute("SELECT record_json FROM items WHERE source='geeknews'").fetchone()[0])
                self.assertEqual(latest['metrics']['points'], 100)

    def test_datetime_offsets_and_unknown_dates(self):
        self.assertEqual(tc.iso_date('2026-10-17T09:00:00+09:00'), '2026-10-17T00:00:00+00:00')
        self.assertEqual(tc.iso_date('Sat, 17 Oct 2026 09:00:00 +0900'), '2026-10-17T00:00:00+00:00')
        self.assertIsNone(tc.iso_date('2026-10-17T09:00:00'))
        self.assertIsNone(tc.iso_date('not a date'))

    def test_csv_formula_injection_is_neutralized(self):
        self.assertEqual(tc.csv_safe('  =HYPERLINK("evil")'), '\'  =HYPERLINK("evil")')
        self.assertEqual(tc.csv_safe('@SUM(1,2)'), "'@SUM(1,2)")
        self.assertEqual(tc.csv_safe(42), 42)


class ParserTests(unittest.TestCase):
    def test_atom_keeps_discussion_identity_and_unknown_original(self):
        body = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <title>A &amp; B</title><id>gn:42</id>
          <link rel="alternate" href="https://news.hada.io/topic?id=42"/>
          <published>2026-10-17T09:00:00+09:00</published>
          <content type="html">&lt;p&gt;Summary&lt;/p&gt;</content>
        </entry></feed>'''
        row = tc.parse_geeknews(body, 2)[0].record()
        self.assertEqual(row['title'], 'A & B')
        self.assertEqual(row['summary'], 'Summary')
        self.assertIsNone(row['metadata']['original_url'])
        self.assertIn('id=42', row['canonical_url'])

    def test_google_shared_feed_links_do_not_collapse_distinct_queries(self):
        body = b'''<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
          <item><title>term one</title><link>https://trends.google.com/trending/rss?geo=KR</link>
          <ht:approx_traffic>20K+</ht:approx_traffic>
          <ht:news_item><ht:news_item_title>Related news</ht:news_item_title>
          <ht:news_item_url>https://news.test/a</ht:news_item_url></ht:news_item></item>
          <item><title>term two</title><link>https://trends.google.com/trending/rss?geo=KR</link></item>
        </channel></rss>'''
        rows = [i.record() for i in tc.parse_google(body, 10, 'KR')]
        self.assertNotEqual(rows[0]['group_id'], rows[1]['group_id'])
        self.assertEqual(rows[0]['metrics']['approx_traffic_lower_bound'], 20000)
        self.assertEqual(rows[0]['metadata']['related_news'][0]['url'], 'https://news.test/a')

    def test_github_total_stars_and_period_growth_are_separate(self):
        root = tc.Document('''<article class="Box-row"><h2><a href="/org/repo">org / repo</a></h2>
          <p>A tool</p><span itemprop="programmingLanguage">Python</span>
          <a href="/org/repo/stargazers">12,345</a><a href="/org/repo/forks">100</a>
          <span class="float-sm-right">456 stars today</span></article>''').root
        row = tc.parse_github(root, 5, 'daily')[0].record()
        self.assertEqual(row['metrics']['stars_total'], 12345)
        self.assertEqual(row['metrics']['stars_in_period'], 456)
        self.assertEqual(row['tags'], ['Python'])

    def test_indiehackers_ignores_avatar_duplicates(self):
        root = tc.Document('''<div class="story"><a class="story__text-link" href="/post/test-42">
          <h3 class="story__title">A founder story</h3></a>
          <a class="story__avatar-link" href="/post/test-42"><img></a>
          <a class="story__count--likes">7 upvotes</a>
          <a class="story__count--comments">28 comments</a></div>''').root
        rows = tc.parse_indiehackers(root, 20)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].metrics['comments'], 28)
        self.assertIsNone(rows[0].published_at)

    def test_disquiet_keeps_post_and_linked_product_separate(self):
        root = tc.Document('''<article data-disquiet--post-card-url-value="/posts/ABC">
          <div id="body_disquiet_post_42">A new product\nfor founders</div>
          <a href="/products/my-tool"><p>My Tool</p></a>
          <span aria-label="추천 12">12</span>
          <a href="/posts/ABC" aria-label="댓글 3개">3</a>
          <time datetime="2026-10-17T00:00:00Z"></time></article>''').root
        row = tc.parse_disquiet(root, 5)[0].record()
        self.assertEqual(row['url'], 'https://disquiet.io/posts/ABC')
        self.assertEqual(row['metadata']['product_url'], 'https://disquiet.io/products/my-tool')
        self.assertEqual(row['metrics'], {'votes': 12, 'comments': 3})

    def test_layout_changes_are_errors_not_silent_success(self):
        root = tc.Document('<html><body>Sign in</body></html>').root
        for parser, args in [(tc.parse_github, (root, 10, 'daily')),
                             (tc.parse_indiehackers, (root, 10)),
                             (tc.parse_disquiet, (root, 10))]:
            with self.subTest(parser=parser.__name__), self.assertRaises(tc.CollectionError):
                parser(*args)


class HTTPTests(unittest.TestCase):
    def test_forbidden_is_not_retried(self):
        client = tc.HTTP({'request_interval': 0})
        error = HTTPError('https://x.test', 403, 'Forbidden', {}, io.BytesIO())
        with patch.object(client.opener, 'open', side_effect=error) as opened:
            with self.assertRaisesRegex(tc.CollectionError, 'HTTP 403'):
                client.get('https://x.test/')
            self.assertEqual(opened.call_count, 1)

    def test_retry_after_is_respected(self):
        client = tc.HTTP({'request_interval': 0})
        error = HTTPError('https://x.test', 429, 'Rate limit', {'Retry-After': '5'}, io.BytesIO())
        response = contextlib.nullcontext(io.BytesIO(b'{"ok":true}'))
        with patch.object(client.opener, 'open', side_effect=[error, response]), patch.object(tc.time, 'sleep') as sleep:
            self.assertEqual(client.json('https://x.test/'), {'ok': True})
            self.assertTrue(any(call.args[0] >= 5 for call in sleep.call_args_list))

    def test_page_requests_only_target_url_and_parses_html(self):
        client = tc.HTTP({})
        with patch.object(client, 'get', return_value=b'<html><h1>Page title</h1></html>') as get:
            root = client.page('https://x.test/page')
            self.assertEqual(tc.text(root.first('h1')), 'Page title')
            get.assert_called_once_with('https://x.test/page')


class PipelineTests(unittest.TestCase):
    def test_partial_source_keeps_completed_items_and_other_sources_continue(self):
        def partial(*args):
            yield tc.Item('hackernews', '42', 'A story', 'https://x.test/42')
            raise tc.CollectionError('HTTP 503 from test')

        def good(*args):
            return [tc.Item('geeknews', '43', 'Another story', 'https://x.test/43')]

        class PartialSource:
            name = 'hackernews'

            def collect(self, request):
                return partial()

        class GoodSource:
            name = 'geeknews'

            def collect(self, request):
                return iter(good())

        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            code = tc.main(['--out', tmp, '--strict'],
                           sources={'hackernews': PartialSource(), 'geeknews': GoodSource()})
            self.assertEqual(code, 1)
            manifest_path = next((Path(tmp) / 'runs').glob('*/manifest.json'))
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            self.assertEqual(manifest['count'], 2)
            self.assertEqual(manifest['sources']['hackernews']['status'], 'partial')
            self.assertEqual(manifest['sources']['geeknews']['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
