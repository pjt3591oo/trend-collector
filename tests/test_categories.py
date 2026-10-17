import unittest
from unittest.mock import Mock

from src.categories import CategorySource
from src.collection import collect_source
from src.models import CollectionError, Item
from src.sources import CollectionRequest, create_sources


class FakeSource:
    name = 'fake'

    def __init__(self, titles):
        self.titles = titles

    def collect(self, request):
        self.request = request
        for rank, title in enumerate(self.titles[:request.limit], 1):
            yield Item(self.name, str(rank), title, f'https://example.com/{rank}', rank=rank)


class CategoryTests(unittest.TestCase):
    def test_filter_scans_before_applying_output_limit_and_preserves_rank(self):
        source = FakeSource(['축구 경기 결과', '배우 결혼 소식', 'OpenAI model release', 'Python release'])
        filtered = CategorySource(source, {'category': 'technology', 'scan_limit': 10})
        rows, status = collect_source(filtered, CollectionRequest(limit=1))
        self.assertEqual([row['title'] for row in rows], ['OpenAI model release'])
        self.assertEqual(rows[0]['rank'], 3)
        self.assertEqual(source.request.limit, 10)
        self.assertEqual(status['filter'], {'scanned': 3, 'filtered': 2, 'accepted': 1})

    def test_keyword_boundaries_and_korean_suffixes(self):
        source = FakeSource(['A happy day', 'He said hello', 'AI가 바꾸는 개발자 업무', '반도체 신제품 발표'])
        rows = list(CategorySource(source, {'category': 'technology'}).collect(CollectionRequest()))
        self.assertEqual([row.title for row in rows], ['AI가 바꾸는 개발자 업무', '반도체 신제품 발표'])

    def test_custom_keywords_and_exclusion(self):
        source = FakeSource(['New wasm release', 'AI celebrity wedding', 'Football scores'])
        rows = list(CategorySource(source, {'category': 'technology', 'include_keywords': ['wasm'],
                                           'exclude_keywords': ['celebrity']}).collect(CollectionRequest()))
        self.assertEqual([row.title for row in rows], ['New wasm release'])

    def test_all_preserves_unrelated_items(self):
        rows = list(CategorySource(FakeSource(['Sports']), {'category': 'all'}).collect(CollectionRequest()))
        self.assertEqual(len(rows), 1)

    def test_empty_matches_have_explicit_reason(self):
        rows, status = collect_source(CategorySource(FakeSource(['Sports']), {'category': 'technology'}), CollectionRequest())
        self.assertEqual(rows, [])
        self.assertEqual(status['status'], 'empty')
        self.assertIn('category', status['message'])

    def test_partial_failure_preserves_accepted_items(self):
        class PartialSource:
            name = 'fake'

            def collect(self, request):
                yield Item(self.name, '1', 'Python news', 'https://example.com/1')
                raise CollectionError('Later page failed')

        rows, status = collect_source(CategorySource(PartialSource(), {'category': 'technology'}), CollectionRequest())
        self.assertEqual(len(rows), 1)
        self.assertEqual(status['status'], 'partial')

    def test_google_matches_related_news_and_looks_past_initial_non_it_entries(self):
        http = Mock()
        http.get.return_value = '''<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
          <item><title>축구 결승</title></item><item><title>연예인 결혼</title></item>
          <item><title>새 제품 발표</title><ht:news_item>
            <ht:news_item_title>엔비디아 GPU 신제품 공개</ht:news_item_title>
            <ht:news_item_url>https://news.test/gpu</ht:news_item_url>
          </ht:news_item></item></channel></rss>'''.encode()
        source = create_sources(http, {'google_trends': {'category': 'technology', 'scan_limit': 500}},
                                credentials={})['google_trends']
        rows = list(source.collect(CollectionRequest(limit=1)))
        self.assertEqual([row.title for row in rows], ['새 제품 발표'])
        self.assertEqual(rows[0].metadata['category_filter']['method'], 'local_keywords')
        self.assertNotIn('category=', http.get.call_args.args[0])

    def test_invalid_filter_config_is_rejected(self):
        for config in ({'category': 'unknown'}, {'category': 'technology', 'scan_limit': 0},
                       {'category': 'technology', 'include_keywords': 'ai'},
                       {'exclude_keywords': ['']}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                CategorySource(FakeSource([]), config)


if __name__ == '__main__':
    unittest.main()
