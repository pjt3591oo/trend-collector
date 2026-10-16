import unittest
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

from src.models import CollectionError
from src.parsing import Document
from src.sources import (CollectionRequest, GitHubAdvisoriesSource, GitHubSource,
                     ProductHuntSource, RedditSource)
from src.sources.producthunt import parse_producthunt
from src.sources.reddit import parse_reddit
from src.sources.github_advisories import parse_github_advisories


def reddit_page(identifier='a', next_url=None, score='-3'):
    next_link = f'<span class="next-button"><a href="{next_url}">next</a></span>' if next_url else ''
    return Document(f'''<div id="siteTable"><div class="thing link" data-fullname="t3_{identifier}"
        data-permalink="/r/SideProject/comments/{identifier}/story/" data-score="{score}">
        <a class="title" href="https://tool.test/{identifier}">A founder story</a>
        <a class="comments" href="/r/SideProject/comments/{identifier}/story/">12 comments</a>
        <time datetime="2026-10-17T00:00:00Z"></time></div></div>{next_link}''').root


def advisory_page(identifier='abcd-abcd-abcd', next_url=None):
    next_link = f'<a class="next_page" href="{next_url}">Next</a>' if next_url else ''
    return Document(f'''<div class="Box-row"><a href="/advisories/GHSA-{identifier}">Security issue</a>
        High CVE-2026-12345 was published for a-package (pip)
        <relative-time datetime="2026-10-16T00:00:00Z"></relative-time></div>{next_link}''').root


class HTMLSourceTests(unittest.TestCase):
    def test_producthunt_today_excludes_other_sections_and_duplicate_links(self):
        root = Document('''<div data-test="homepage-section-today"><section>
          <a href="/products/tool">1. Tool</a><a href="/products/tool">duplicate</a>
          <span class="text-secondary">A useful product</span><a href="/topics/ai">AI</a>
          <button data-test="vote-button">123</button></section></div>
          <section><a href="/products/old">Yesterday</a></section>''').root
        http = Mock()
        http.page.return_value = root
        source = ProductHuntSource(http, credentials={})
        rows = list(source.collect(CollectionRequest(limit=10)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].title, 'Tool')
        self.assertEqual(rows[0].summary, 'A useful product')
        self.assertEqual(rows[0].metrics, {'votes': 123})
        self.assertEqual(rows[0].tags, ['AI'])
        self.assertIsNone(rows[0].published_at)
        self.assertEqual(rows[0].collection_method, 'public_html')
        http.page.assert_called_once_with('https://www.producthunt.com/')
        http.json.assert_not_called()

    def test_reddit_pagination_and_metrics_need_no_token(self):
        http = Mock()
        next_url = 'https://old.reddit.com/r/SideProject/new/?after=t3_a'
        http.page.side_effect = [reddit_page(next_url=next_url), reddit_page('b', score='[hidden]')]
        rows = list(RedditSource(http, {'subreddits': ['SideProject']}).collect(CollectionRequest(limit=2)))
        self.assertEqual([r.external_id for r in rows], ['t3_a', 't3_b'])
        self.assertEqual([r.rank for r in rows], [1, 2])
        self.assertEqual(rows[0].metrics, {'score': -3, 'comments': 12})
        self.assertIsNone(rows[1].metrics['score'])
        self.assertEqual(rows[0].record()['published_at'], '2026-10-17T00:00:00+00:00')
        http.json.assert_not_called()

    def test_reddit_distributes_budget_across_communities(self):
        http = Mock()
        http.page.side_effect = [reddit_page('a'), reddit_page('b')]
        rows = list(RedditSource(http, {'subreddits': ['SaaS', 'smallbusiness', 'SideProject']})
                    .collect(CollectionRequest(limit=2)))
        self.assertEqual([r.tags for r in rows], [['SaaS'], ['smallbusiness']])
        self.assertEqual(http.page.call_count, 2)

    def test_reddit_preserves_first_page_when_later_request_fails(self):
        http = Mock()
        http.page.side_effect = [reddit_page(next_url='?after=t3_a'), CollectionError('HTTP 403')]
        items = RedditSource(http, {'subreddits': ['SideProject']}).collect(CollectionRequest(limit=2))
        self.assertEqual(next(items).external_id, 't3_a')
        with self.assertRaises(CollectionError):
            next(items)

    def test_reddit_rejects_foreign_pagination_links(self):
        http = Mock()
        http.page.return_value = reddit_page(next_url='https://example.com/')
        iterator = RedditSource(http, {'subreddits': ['SideProject']}).collect(CollectionRequest(limit=2))
        next(iterator)
        with self.assertRaises(CollectionError):
            next(iterator)
        self.assertEqual(http.page.call_count, 1)

    def test_page_errors_are_not_replaced_with_api_fallback(self):
        for cls in (RedditSource, ProductHuntSource, GitHubSource, GitHubAdvisoriesSource):
            with self.subTest(source=cls.name):
                http = Mock()
                http.page.side_effect = CollectionError('HTTP 403')
                with self.assertRaises(CollectionError):
                    list(cls(http).collect(CollectionRequest()))
                http.json.assert_not_called()

    def test_github_advisories_use_html_filters_and_pagination(self):
        http = Mock()
        http.page.side_effect = [advisory_page(next_url='?page=2'), advisory_page('efgh-efgh-efgh')]
        rows = list(GitHubAdvisoriesSource(http, {'ecosystem': 'pip', 'severity': 'high'})
                    .collect(CollectionRequest(limit=2)))
        query = parse_qs(urlsplit(http.page.call_args_list[0].args[0]).query)['query'][0]
        self.assertIn('ecosystem:pip', query)
        self.assertIn('severity:high', query)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].metadata['cve_ids'], ['CVE-2026-12345'])
        self.assertEqual(rows[0].metadata['severity'], 'high')
        self.assertEqual(rows[0].metrics, {})
        self.assertEqual(rows[0].collection_method, 'public_html')
        http.json.assert_not_called()

    def test_missing_layout_is_an_error(self):
        root = Document('<html><h1>Sign in</h1></html>').root
        for parser, args in ((parse_producthunt, (root, 10)),
                             (parse_reddit, (root, 10, 'SideProject', 'new')),
                             (parse_github_advisories, (root, 10))):
            with self.subTest(parser=parser.__name__), self.assertRaises(CollectionError):
                parser(*args)


if __name__ == '__main__':
    unittest.main()
